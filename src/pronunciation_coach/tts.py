"""Server-side text-to-speech: Piper (CPU, onnxruntime) with an espeak-ng fallback.

Piper is imported lazily, and its voice is downloaded on first use into
``DATA_DIR/voices``. Nothing here imports torch or touches the NVIDIA GPU.
"""

from __future__ import annotations

import hashlib
import io
import logging
import shutil
import subprocess
import tempfile
import threading
import urllib.request
import wave
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import config
from .phoneme_audio import recording_for
from .phoneme_guide import Phoneme, SoundSpec, fallback_word, lookup

log = logging.getLogger("pronunciation_coach.tts")

MAX_TEXT_CHARS = 600
MIN_RATE, MAX_RATE = 0.5, 1.5
CACHE_MAX_ITEMS = 256
VOICES_REPO_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/main"
ESPEAK_BASE_WPM = 175
# Isolated phonemes: slowest espeak speed, a gap between parts, gentle loudness boost.
PHONEME_ESPEAK_WPM = 80
PHONEME_GAP_SECONDS = 0.35
PHONEME_PAD_SECONDS = 0.05
PHONEME_PEAK = 0.7
PHONEME_MAX_GAIN = 8.0
PHONEME_FALLBACK_RATE = 0.6


class TTSError(RuntimeError):
    """No engine could synthesize the text."""


class TTSInputError(ValueError):
    """The text is empty or too long."""


class UnknownPhoneme(KeyError):
    """The symbol has no entry in the phoneme guide."""


@dataclass(frozen=True)
class Speech:
    audio: bytes
    engine: str  # "piper", "espeak-ng" or "recording"
    method: str = ""  # isolated phonemes: "recording", "word" (Piper) or a SoundSpec.method
    media_type: str = "audio/wav"

    @property
    def source(self) -> str:
        """Isolated phonemes: recording | piper | espeak (see phoneme_audio)."""
        return {"recording": "recording", "piper": "piper"}.get(self.engine, "espeak")


def clamp_rate(rate: float) -> float:
    return max(MIN_RATE, min(MAX_RATE, rate))


def voice_paths(voice: str = config.TTS_VOICE) -> tuple[Path, Path]:
    model = config.VOICES_DIR / f"{voice}.onnx"
    return model, model.with_name(model.name + ".json")


def _download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    log.info("downloading %s", url)
    with urllib.request.urlopen(url, timeout=60) as resp, open(tmp, "wb") as out:
        shutil.copyfileobj(resp, out)
    tmp.replace(dest)


def voice_url(voice: str, filename: str) -> str:
    """URL of a voice file, e.g. en_US-lessac-medium -> en/en_US/lessac/medium/<filename>."""
    lang_code, name, quality = voice.split("-", 2)
    family = lang_code.split("_", 1)[0]
    return f"{VOICES_REPO_URL}/{family}/{lang_code}/{name}/{quality}/{filename}?download=true"


def ensure_voice(voice: str = config.TTS_VOICE) -> tuple[Path, Path]:
    """Download the Piper voice (.onnx + .onnx.json) if it is not cached yet."""
    model, cfg = voice_paths(voice)
    for path in (cfg, model):
        if not path.exists():
            _download(voice_url(voice, path.name), path)
    return model, cfg


class Synthesizer:
    """Thread-safe synthesizer with an in-memory LRU cache keyed by sha256(text, rate)."""

    def __init__(self, voice: str = config.TTS_VOICE, cache_size: int = CACHE_MAX_ITEMS):
        self.voice_name = voice
        self.cache_size = cache_size
        self._cache: OrderedDict[str, Speech] = OrderedDict()
        self._lock = threading.Lock()
        self._piper = None
        self._piper_failed = False

    @staticmethod
    def cache_key(text: str, rate: float) -> str:
        return hashlib.sha256(f"{rate:.2f}\0{text}".encode()).hexdigest()

    def synthesize(self, text: str, rate: float = 1.0) -> Speech:
        text = " ".join(text.split())
        if not text:
            raise TTSInputError("empty text")
        if len(text) > MAX_TEXT_CHARS:
            raise TTSInputError(f"text longer than {MAX_TEXT_CHARS} characters")
        rate = round(clamp_rate(rate), 2)
        return self._cached(self.cache_key(text, rate), lambda: self._synthesize_uncached(text, rate))

    def synthesize_phoneme(self, symbol: str) -> Speech:
        """A guide sound: human recording, else its example word slowly (Piper), else espeak-ng."""
        entry = lookup(symbol)
        if entry is None:
            raise UnknownPhoneme(symbol)
        return self._cached(self.cache_key(f"phoneme:{entry.symbol}", 0.0),
                            lambda: self._phoneme_uncached(entry))

    def _cached(self, key: str, make) -> Speech:
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
                return self._cache[key]
            speech = make()
            self._cache[key] = speech
            while len(self._cache) > self.cache_size:
                self._cache.popitem(last=False)
            return speech

    def _phoneme_uncached(self, entry: Phoneme) -> Speech:
        rec = recording_for(entry)
        if rec is not None:
            try:
                return Speech(rec.path.read_bytes(), "recording", "recording", "audio/ogg")
            except OSError as exc:
                log.warning("recording for /%s/ unreadable (%s)", entry.symbol, exc)
        word = fallback_word(entry)
        if word is not None and not self._piper_failed:
            try:
                wav = self._piper_wav(word, PHONEME_FALLBACK_RATE)
                log.info("tts phoneme=%s engine=piper word=%r", entry.symbol, word)
                return Speech(wav, "piper", "word")
            except Exception as exc:  # noqa: BLE001 - any Piper failure falls back
                log.warning("piper failed for /%s/ (%s); using espeak-ng", entry.symbol, exc)
                if self._piper is None:
                    self._piper_failed = True
        wav = espeak_phoneme_wav(entry.sound)
        log.info("tts phoneme=%s engine=espeak-ng method=%s", entry.symbol, entry.sound.method)
        return Speech(wav, "espeak-ng", entry.sound.method)

    def _synthesize_uncached(self, text: str, rate: float) -> Speech:
        if not self._piper_failed:
            try:
                wav = self._piper_wav(text, rate)
                log.info("tts engine=piper rate=%.2f chars=%d", rate, len(text))
                return Speech(wav, "piper")
            except Exception as exc:  # noqa: BLE001 - any Piper failure falls back
                log.warning("piper failed (%s); falling back to espeak-ng", exc)
                if self._piper is None:
                    # Load/download failed: do not retry on every request.
                    self._piper_failed = True
        wav = espeak_wav(text, rate)
        log.info("tts engine=espeak-ng rate=%.2f chars=%d", rate, len(text))
        return Speech(wav, "espeak-ng")

    def _load_piper(self):
        if self._piper is None:
            from piper import PiperVoice  # lazy: pulls in onnxruntime

            model, cfg = ensure_voice(self.voice_name)
            self._piper = PiperVoice.load(model, config_path=cfg, use_cuda=False)
            log.info("piper voice loaded: %s (CPU)", model.name)
        return self._piper

    def _piper_wav(self, text: str, rate: float) -> bytes:
        from piper import SynthesisConfig

        voice = self._load_piper()
        # Slower speech (rate < 1) means a larger length_scale.
        length_scale = voice.config.length_scale / rate
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            voice.synthesize_wav(text, wav, syn_config=SynthesisConfig(length_scale=length_scale))
        return buf.getvalue()


def espeak_wav(text: str, rate: float = 1.0) -> bytes:
    exe = shutil.which("espeak-ng")
    if not exe:
        raise TTSError("neither Piper nor espeak-ng is available")
    speed = str(int(ESPEAK_BASE_WPM * rate))
    # Write to a file (-w): with --stdout espeak-ng leaves the WAV length fields unset.
    with tempfile.TemporaryDirectory(prefix="pc-espeak-") as tmp:
        out = Path(tmp) / "speech.wav"
        try:
            subprocess.run(
                [exe, "-v", config.ESPEAK_LANGUAGE, "-s", speed, "-w", str(out), "--", text],
                capture_output=True, timeout=30, check=True,
            )
            return out.read_bytes()
        except (subprocess.SubprocessError, OSError) as exc:
            raise TTSError(f"espeak-ng failed: {exc}") from exc


def _espeak_part(exe: str, mnemonic: str, voice: str, tmp: Path) -> tuple[np.ndarray, int]:
    out = tmp / "part.wav"
    try:
        subprocess.run(
            [exe, "-v", voice, "-s", str(PHONEME_ESPEAK_WPM), "-w", str(out), "--", f"[[{mnemonic}]]"],
            capture_output=True, timeout=30, check=True,
        )
        with wave.open(str(out), "rb") as w:
            rate = w.getframerate()
            samples = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    except (subprocess.SubprocessError, OSError, wave.Error) as exc:
        raise TTSError(f"espeak-ng failed for [[{mnemonic}]]: {exc}") from exc
    return samples.astype(np.float32) / 32768.0, rate


def trim_and_normalize(x: np.ndarray, rate: int, frame_seconds: float = 0.005,
                       threshold: float = 0.02) -> np.ndarray:
    """Cut leading/trailing silence and raise the peak to PHONEME_PEAK (gain capped)."""
    frame = max(1, int(rate * frame_seconds))
    n = len(x) // frame
    if n == 0:
        return x[:0]
    rms = np.sqrt(np.mean(x[: n * frame].reshape(n, frame) ** 2, axis=1))
    loud = np.flatnonzero(rms > threshold * rms.max()) if rms.max() > 0 else np.array([], int)
    if loud.size == 0:
        return x[:0]
    x = x[loud[0] * frame : (loud[-1] + 1) * frame]
    peak = float(np.abs(x).max())
    return x * min(PHONEME_PEAK / peak, PHONEME_MAX_GAIN)


def espeak_phoneme_wav(spec: SoundSpec) -> bytes:
    """Render espeak-ng phoneme mnemonics (``[[...]]``), trimmed, with gaps between parts."""
    exe = shutil.which("espeak-ng")
    if not exe:
        raise TTSError("espeak-ng is not available")
    chunks: list[np.ndarray] = []
    rate = 22050
    with tempfile.TemporaryDirectory(prefix="pc-phoneme-") as tmp:
        for i, mnemonic in enumerate(spec.parts):
            x, rate = _espeak_part(exe, mnemonic, spec.voice, Path(tmp))
            x = trim_and_normalize(x, rate)
            if x.size == 0:
                raise TTSError(f"espeak-ng produced silence for [[{mnemonic}]]")
            if i:
                chunks.append(np.zeros(int(rate * PHONEME_GAP_SECONDS), np.float32))
            chunks.append(x)
    pad = np.zeros(int(rate * PHONEME_PAD_SECONDS), np.float32)
    audio = np.concatenate([pad, *chunks, pad])
    pcm = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return buf.getvalue()


def wav_duration(data: bytes) -> float:
    with wave.open(io.BytesIO(data), "rb") as wav:
        return wav.getnframes() / float(wav.getframerate())
