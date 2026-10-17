"""Audio decoding via ffmpeg (any container/codec -> 16 kHz mono float32)."""

from __future__ import annotations

import subprocess

import numpy as np

SAMPLE_RATE = 16000


class AudioError(ValueError):
    pass


def decode_to_16k_mono(data: bytes) -> np.ndarray:
    if not data:
        raise AudioError("empty audio")
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin",
        "-i", "pipe:0", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "pipe:1",
    ]
    try:
        proc = subprocess.run(cmd, input=data, capture_output=True, timeout=60, check=False)
    except FileNotFoundError as exc:
        raise AudioError("ffmpeg is not installed") from exc
    if proc.returncode != 0:
        raise AudioError(f"ffmpeg failed: {proc.stderr.decode(errors='replace').strip()[:300]}")
    audio = np.frombuffer(proc.stdout, dtype=np.float32).copy()
    if audio.size < SAMPLE_RATE // 4:
        raise AudioError("recording is too short")
    return audio
