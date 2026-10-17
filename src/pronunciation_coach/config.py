"""Runtime configuration, read from environment variables."""

from __future__ import annotations

import os
from pathlib import Path


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


HOST = os.environ.get("PC_HOST", "127.0.0.1")
PORT = int(os.environ.get("PC_PORT", "8765"))

DATA_DIR = Path(
    os.environ.get(
        "PC_DATA_DIR",
        Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
        / "pronunciation-coach",
    )
)
DB_PATH = DATA_DIR / "coach.sqlite3"
VOICES_DIR = DATA_DIR / "voices"

MODEL_NAME = os.environ.get("PC_MODEL", "facebook/wav2vec2-lv-60-espeak-cv-ft")
# "auto" (cuda if available, else cpu), "cuda" or "cpu".
DEVICE = os.environ.get("PC_DEVICE", "auto")
# Seconds of inactivity after which the GPU worker exits and frees the CUDA context.
WORKER_IDLE_TIMEOUT = _env_float("PC_WORKER_IDLE_TIMEOUT", 120.0)
# Max seconds to wait for one recognition (includes first-time model load/download).
WORKER_REQUEST_TIMEOUT = _env_float("PC_WORKER_REQUEST_TIMEOUT", 900.0)

ESPEAK_LANGUAGE = "en-us"

# Piper voice for server-side text-to-speech (downloaded on first use, runs on CPU).
TTS_VOICE = os.environ.get("PC_TTS_VOICE", "en_US-lessac-medium")

# ------------------------------------------------------------------ writing (LLM)
# Secrets live outside the repo, in a chmod 600 KEY=VALUE file. Real env vars win.
CONFIG_DIR = Path(
    os.environ.get("PC_CONFIG_DIR",
                   Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "pronunciation-coach")
)
ENV_FILE = CONFIG_DIR / "env"

WRITING_PROVIDER = os.environ.get("PC_WRITING_PROVIDER", "groq")
# Large reasoning model for careful correction; the fallback is used when the main
# model is rate-limited, over capacity or unavailable.
WRITING_MODEL = os.environ.get("PC_WRITING_MODEL", "openai/gpt-oss-120b")
WRITING_FALLBACK_MODEL = os.environ.get("PC_WRITING_FALLBACK_MODEL", "openai/gpt-oss-20b")
# "low", "medium" or "high" (only sent to models that support it, e.g. gpt-oss).
WRITING_REASONING_EFFORT = os.environ.get("PC_WRITING_REASONING_EFFORT", "medium")
WRITING_TIMEOUT = _env_float("PC_WRITING_TIMEOUT", 120.0)


def read_env_file(path: Path) -> dict[str, str]:
    """Parse a simple KEY=VALUE file (comments, blank lines, `export` and quotes allowed)."""
    values: dict[str, str] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return values
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.removeprefix("export ").partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def secret(name: str) -> str | None:
    """A secret from the environment, else from ENV_FILE. Never log the result."""
    return os.environ.get(name) or read_env_file(ENV_FILE).get(name) or None
