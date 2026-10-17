"""GPU recognition worker.

The FastAPI process never imports torch. Recognition runs in a child process
(``spawn`` start method) that loads the wav2vec2 phoneme model on CUDA, serves
requests over a ``multiprocessing`` pipe and exits after an idle timeout so the
CUDA context is released and the NVIDIA dGPU can runtime-suspend again.
"""

from __future__ import annotations

import logging
import multiprocessing as mp
import threading
import time
from dataclasses import dataclass

from . import config

log = logging.getLogger("pronunciation_coach.worker")

_SPECIAL = {"<pad>", "<s>", "</s>", "<unk>", "|"}


def ctc_collapse(ids: list[int], token_of, frame_seconds: float) -> tuple[list[str], list[list[float]]]:
    """Greedy CTC decoding that keeps time: each token with the [start, end] seconds of its run.

    Runs of the same id collapse into one token; special tokens (pad/blank, word
    separator) are dropped. Torch-free, so it can be unit-tested.
    """
    tokens: list[str] = []
    spans: list[list[float]] = []
    i, n = 0, len(ids)
    while i < n:
        j = i
        while j + 1 < n and ids[j + 1] == ids[i]:
            j += 1
        tok = token_of(ids[i])
        if tok not in _SPECIAL:
            tokens.append(tok)
            spans.append([round(i * frame_seconds, 3), round((j + 1) * frame_seconds, 3)])
        i = j + 1
    return tokens, spans


# --------------------------------------------------------------------------- child


def worker_main(conn, model_name: str, device_pref: str, idle_timeout: float) -> None:
    """Entry point of the child process. Imports torch here and only here."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s worker[%(process)d] %(levelname)s %(message)s")
    t0 = time.monotonic()
    import torch
    from transformers import Wav2Vec2FeatureExtractor, Wav2Vec2ForCTC, Wav2Vec2PhonemeCTCTokenizer

    if device_pref == "cpu":
        device = "cpu"
    elif torch.cuda.is_available():
        device = "cuda"
    else:
        device = "cpu"
        log.warning("CUDA is not available; falling back to CPU (slower).")
    device_name = torch.cuda.get_device_name(0) if device == "cuda" else "cpu"

    extractor = Wav2Vec2FeatureExtractor.from_pretrained(model_name)
    # do_phonemize=False: we only decode, so the tokenizer must not require espeak.
    tokenizer = Wav2Vec2PhonemeCTCTokenizer.from_pretrained(model_name, do_phonemize=False)
    model = Wav2Vec2ForCTC.from_pretrained(model_name).to(device).eval()
    load_seconds = time.monotonic() - t0
    log.info("model %s loaded on %s (%s) in %.1fs", model_name, device, device_name, load_seconds)
    conn.send({"type": "ready", "device": device, "device_name": device_name, "load_seconds": load_seconds})

    try:
        while True:
            if not conn.poll(idle_timeout):
                log.info("idle for %.0fs, exiting to release %s", idle_timeout, device)
                break
            try:
                msg = conn.recv()
            except EOFError:
                break
            if msg is None:
                break
            req_id, audio = msg
            t1 = time.monotonic()
            try:
                inputs = extractor(audio, sampling_rate=16000, return_tensors="pt")
                with torch.inference_mode():
                    logits = model(inputs.input_values.to(device)).logits
                ids = torch.argmax(logits, dim=-1)[0].tolist()
                frame_seconds = (len(audio) / 16000) / max(len(ids), 1)
                tokens, spans = ctc_collapse(ids, tokenizer.convert_ids_to_tokens, frame_seconds)
                conn.send({
                    "type": "result", "id": req_id, "phonemes": " ".join(tokens), "spans": spans,
                    "audio_seconds": len(audio) / 16000,
                    "device": device, "device_name": device_name,
                    "infer_seconds": time.monotonic() - t1,
                })
            except Exception as exc:  # report and keep serving
                log.exception("recognition failed")
                conn.send({"type": "error", "id": req_id, "error": repr(exc)})
    finally:
        del model
        if device == "cuda":
            torch.cuda.empty_cache()
        conn.close()


# -------------------------------------------------------------------------- parent


class RecognizerError(RuntimeError):
    pass


@dataclass
class WorkerInfo:
    alive: bool
    pid: int | None
    device: str | None
    device_name: str | None
    requests: int
    spawns: int


class RecognizerClient:
    """Lazily spawns the worker; thread-safe; respawns if the worker exited."""

    def __init__(self, model_name: str = config.MODEL_NAME, device: str = config.DEVICE,
                 idle_timeout: float = config.WORKER_IDLE_TIMEOUT,
                 request_timeout: float = config.WORKER_REQUEST_TIMEOUT) -> None:
        self.model_name = model_name
        self.device_pref = device
        self.idle_timeout = idle_timeout
        self.request_timeout = request_timeout
        self._ctx = mp.get_context("spawn")
        self._lock = threading.Lock()
        self._proc = None
        self._conn = None
        self._ready: dict | None = None
        self._next_id = 0
        self.requests = 0
        self.spawns = 0

    def _alive(self) -> bool:
        return self._proc is not None and self._proc.is_alive()

    def _spawn(self) -> None:
        self._cleanup()
        parent, child = self._ctx.Pipe()
        proc = self._ctx.Process(
            target=worker_main,
            args=(child, self.model_name, self.device_pref, self.idle_timeout),
            name="pronunciation-coach-worker",
            daemon=True,
        )
        proc.start()
        child.close()
        self._proc, self._conn = proc, parent
        self.spawns += 1
        log.info("spawned recognition worker pid=%s", proc.pid)
        if not parent.poll(self.request_timeout):
            self._cleanup()
            raise RecognizerError("worker did not become ready in time")
        try:
            ready = parent.recv()
        except EOFError as exc:
            self._cleanup()
            raise RecognizerError("worker crashed while loading the model (see logs)") from exc
        self._ready = ready
        log.info("worker ready on %s (%s)", ready.get("device"), ready.get("device_name"))

    def _cleanup(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except OSError:
                pass
        if self._proc is not None:
            self._proc.join(timeout=1)
            if self._proc.is_alive():
                self._proc.kill()
                self._proc.join(timeout=5)
        self._proc = self._conn = self._ready = None

    def _request(self, audio) -> dict:
        self._next_id += 1
        req_id = self._next_id
        self._conn.send((req_id, audio))
        if not self._conn.poll(self.request_timeout):
            self._cleanup()
            raise RecognizerError("recognition timed out")
        reply = self._conn.recv()
        if reply.get("type") == "error":
            raise RecognizerError(reply.get("error", "unknown worker error"))
        return reply

    def recognize(self, audio) -> dict:
        """Recognize 16 kHz mono float32 audio. Returns dict with 'phonemes' and device info."""
        with self._lock:
            for attempt in range(2):
                if not self._alive():
                    self._spawn()
                try:
                    reply = self._request(audio)
                    self.requests += 1
                    return reply
                except (EOFError, BrokenPipeError, ConnectionResetError, OSError):
                    # The worker exited (idle timeout race) between our check and send.
                    log.info("worker went away; respawning (attempt %d)", attempt + 1)
                    self._cleanup()
            raise RecognizerError("worker kept exiting")

    def info(self) -> WorkerInfo:
        alive = self._alive()
        ready = self._ready or {}
        return WorkerInfo(alive, self._proc.pid if alive else None,
                          ready.get("device") if alive else None,
                          ready.get("device_name") if alive else None,
                          self.requests, self.spawns)

    def shutdown(self) -> None:
        with self._lock:
            if self._alive():
                try:
                    self._conn.send(None)
                except OSError:
                    pass
            self._cleanup()
