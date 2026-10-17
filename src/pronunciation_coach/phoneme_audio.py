"""Bundled human recordings of isolated sounds (Wikimedia Commons), and source planning.

The recordings live in ``static/phonemes/`` next to the frontend, so they ship with the
package, work offline and are served as plain static files. They are small (about
15 KB each, Ogg/Opus) and their licenses (CC0, public domain, CC BY-SA) allow
redistribution with attribution. ``attribution.json`` (written by
``scripts/fetch_phoneme_audio.py``) maps each guide symbol to its file, author,
license and source page.

Every guide sound is played from the best source available, in this order:

1. ``recording``: a human recording of the sound (most vowels and consonants);
2. ``piper``: the first example word, slowed down, with the Piper neural voice
   (diphthongs and unstressed /ɚ/, which have no good isolated recording);
3. ``espeak``: espeak-ng phoneme synthesis, only if both of the above fail.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .phoneme_guide import Phoneme, fallback_word

log = logging.getLogger("pronunciation_coach.phoneme_audio")

AUDIO_DIR = Path(__file__).parent / "static" / "phonemes"
MANIFEST = AUDIO_DIR / "attribution.json"
STATIC_PREFIX = "/static/phonemes/"
SOURCES = ("recording", "piper", "espeak")


@dataclass(frozen=True)
class Recording:
    symbol: str
    file: str
    author: str
    license: str
    license_url: str
    source_url: str
    title: str
    sample: str = ""  # what the clip says, e.g. "[θa aθa]"

    @property
    def path(self) -> Path:
        return AUDIO_DIR / self.file

    @property
    def url(self) -> str:
        return STATIC_PREFIX + self.file

    def to_dict(self) -> dict:
        return {
            "url": self.url, "author": self.author, "license": self.license,
            "license_url": self.license_url, "source_url": self.source_url,
            "title": self.title, "sample": self.sample,
        }


def load_manifest(path: Path = MANIFEST) -> dict[str, Recording]:
    try:
        data = json.loads(path.read_text("utf-8"))["recordings"]
    except (OSError, ValueError, KeyError) as exc:
        log.warning("no phoneme recordings (%s): %s", path, exc)
        return {}
    out = {}
    for symbol, e in data.items():
        rec = Recording(symbol, e["file"], e["author"], e["license"], e.get("license_url", ""),
                        e["source_url"], e["title"], e.get("sample", ""))
        if rec.path.is_file():
            out[symbol] = rec
        else:
            log.warning("recording for /%s/ is missing: %s", symbol, rec.path)
    return out


@lru_cache(maxsize=1)
def recordings() -> dict[str, Recording]:
    return load_manifest()


def recording_for(entry: Phoneme) -> Recording | None:
    return recordings().get(entry.symbol)


def planned_source(entry: Phoneme) -> str:
    """The source the app tries first for this sound (see the module docstring)."""
    if recording_for(entry) is not None:
        return "recording"
    if fallback_word(entry) is not None:
        return "piper"
    return "espeak"
