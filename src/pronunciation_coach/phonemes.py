"""IPA normalization and expected-phoneme generation.

Both sides of the comparison (espeak-ng expected phonemes and wav2vec2 recognized
phonemes) go through ``tokenize_ipa`` so they share one token inventory:

* stress, length and tie marks are removed,
* a few espeak-specific symbols are folded into common ones,
* strings are re-segmented greedily into known multi-character units
  (diphthongs, affricates) and single symbols.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from functools import lru_cache

from . import config

# Characters dropped everywhere: stress, length, tie bars, syllable marks, separators.
_DROP_CHARS = set("ˈˌːˑ'ˑ.‿͜͡-|_")
# Combining diacritics are dropped as well (nasalization, syllabic marks, ...).

# Single-symbol folds applied after dropping marks.
_FOLD = {
    "g": "ɡ",   # ASCII g -> IPA script g
    "r": "ɹ",
    "ɐ": "ə",   # espeak near-open central vowel ~ schwa
    "ᵻ": "ɪ",   # espeak "roses" vowel
    "ɘ": "ə",
    "ɵ": "ʊ",
    "ɫ": "l",
    "ɬ": "l",
    "ʔ": "",    # glottal stop: ignore
}

# Multi-character units kept as a single token (longest match first).
MULTI_UNITS = sorted(
    ["tʃ", "dʒ", "aɪ", "aʊ", "eɪ", "oʊ", "ɔɪ", "əʊ", "ɪə", "eə", "ʊə"],
    key=len,
    reverse=True,
)

_LANG_FLAG_RE = re.compile(r"\([a-z\-]+\)")
_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’][A-Za-z]+)*")


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFD", text)
    text = _LANG_FLAG_RE.sub("", text)
    out = []
    for ch in text:
        if ch in _DROP_CHARS or unicodedata.combining(ch):
            continue
        out.append(_FOLD.get(ch, ch))
    return unicodedata.normalize("NFC", "".join(out))


def _segment(chunk: str) -> list[str]:
    tokens: list[str] = []
    i = 0
    while i < len(chunk):
        for unit in MULTI_UNITS:
            if chunk.startswith(unit, i):
                tokens.append(unit)
                i += len(unit)
                break
        else:
            tokens.append(chunk[i])
            i += 1
    return tokens


def tokenize_ipa(ipa: str) -> list[str]:
    """Normalize an IPA string (space-separated or not) into phoneme tokens."""
    tokens: list[str] = []
    for chunk in _clean(ipa).split():
        tokens.extend(t for t in _segment(chunk) if t.strip())
    return tokens


@dataclass
class Segment:
    """A piece of the sentence: either a word (``word`` index) or the text between words."""

    text: str
    word: int | None = None


@dataclass
class ExpectedWord:
    text: str
    phonemes: list[str] = field(default_factory=list)


def split_words(sentence: str) -> list[Segment]:
    """Split a sentence into word / non-word segments, preserving all characters."""
    segments: list[Segment] = []
    pos = 0
    for n, m in enumerate(_WORD_RE.finditer(sentence)):
        if m.start() > pos:
            segments.append(Segment(sentence[pos : m.start()]))
        segments.append(Segment(m.group(0), word=n))
        pos = m.end()
    if pos < len(sentence):
        segments.append(Segment(sentence[pos:]))
    return segments


class EspeakUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _backend():
    try:
        from phonemizer.backend import EspeakBackend
    except ImportError as exc:  # pragma: no cover
        raise EspeakUnavailable(f"phonemizer not importable: {exc}") from exc
    try:
        return EspeakBackend(
            config.ESPEAK_LANGUAGE,
            with_stress=False,
            language_switch="remove-flags",
            preserve_punctuation=False,
        )
    except RuntimeError as exc:
        raise EspeakUnavailable(
            "espeak-ng is not available. Install it (e.g. `sudo pacman -S espeak-ng`)."
        ) from exc


def espeak_available() -> bool:
    try:
        _backend()
        return True
    except EspeakUnavailable:
        return False


def phonemize_words(words: list[str]) -> list[str]:
    """Return raw espeak IPA for each word.

    The words are first phonemized together as one sentence, so function words get
    their natural weak forms ("a" -> /ə/, "to" -> /tə/) and stress follows the
    sentence. If espeak's word count differs (numbers, abbreviations expand into
    several words), fall back to phonemizing each word on its own.
    """
    if not words:
        return []
    from phonemizer.separator import Separator

    sep = Separator(phone=" ", word="|", syllable="")
    clean = [w.replace("’", "'") for w in words]
    [joined] = _backend().phonemize([" ".join(clean)], separator=sep, strip=True, njobs=1)
    parts = [p.strip() for p in joined.split("|")]
    if len(parts) == len(words):
        return parts
    out = _backend().phonemize(clean, separator=sep, strip=True, njobs=1)
    # A single input token may expand to several words (numbers, contractions).
    return [o.replace("|", " ") for o in out]


def expected_for_sentence(sentence: str, phonemize=phonemize_words) -> list[ExpectedWord]:
    """Expected phoneme tokens per word. ``phonemize`` is injectable for tests."""
    words = [s.text for s in split_words(sentence) if s.word is not None]
    raw = phonemize(words)
    return [ExpectedWord(w, tokenize_ipa(ipa)) for w, ipa in zip(words, raw)]
