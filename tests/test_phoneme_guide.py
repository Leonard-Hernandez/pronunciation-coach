import json
import re
import shutil

import pytest
from fastapi.testclient import TestClient

from pronunciation_coach import phoneme_audio as pa
from pronunciation_coach import phoneme_guide as pg
from pronunciation_coach import server, tts
from pronunciation_coach.db import Database
from pronunciation_coach.phonemes import tokenize_ipa
from pronunciation_coach.scoring import CLOSE_PAIRS
from pronunciation_coach.tips import PAIR_TIPS, PHONEME_TIPS

from .conftest import LEXICON
from .test_api import FakeRecognizer
from .test_tts import make_wav

# Every token espeak-ng (en-us) produced, after tokenize_ipa, over ~3000 words
# (captured with espeak-ng 1.52). The scorer's expected side can only emit these.
ESPEAK_EN_US_TOKENS = (
    "s ɹ ɪ n ə k t ɛ d i l p oʊ m ɑ æ z v ɚ b aɪ eɪ f u ɡ ɔ ʌ w j ɾ dʒ ɜ ʃ ŋ tʃ h "
    "aʊ ʊ θ ð ɔɪ ʒ"
).split()

HARD_FOR_SPANISH = "θ ð v z ʃ ʒ dʒ h ŋ ɪ i æ ɑ ʌ ʊ u ə ɚ ɝ ɹ p t k".split()
METHODS = {"isolated", "sustained", "frame", "syllable"}


def test_every_expected_phoneme_has_an_entry():
    missing = [t for t in ESPEAK_EN_US_TOKENS if pg.lookup(t) is None]
    assert missing == []


def test_lexicon_tips_and_close_pairs_are_covered():
    symbols = {t for ipa in LEXICON.values() for t in tokenize_ipa(ipa)}
    symbols |= {s for pair in PAIR_TIPS for s in pair}
    symbols |= {s for pair in CLOSE_PAIRS for s in pair}
    assert sorted(s for s in symbols if pg.lookup(s) is None) == []


@pytest.mark.skipif(shutil.which("espeak-ng") is None, reason="espeak-ng not installed")
def test_live_espeak_inventory_is_covered():
    from pronunciation_coach.phonemes import phonemize_words

    words = ("The quick brown fox jumps over the lazy dog while she measures "
             "thirty-three huge yellow church bells and sings about her vision of water").split()
    tokens = {t for ipa in phonemize_words(words) for t in tokenize_ipa(ipa)}
    assert sorted(t for t in tokens if pg.lookup(t) is None) == []


def test_entries_are_complete():
    categories = {cid for cid, _ in pg.CATEGORIES}
    for p in pg.GUIDE:
        assert p.category in categories, p.symbol
        assert p.name and p.how and p.spanish and p.tip, p.symbol
        assert p.sound.method in METHODS and p.sound.parts, p.symbol
        if p.category == "other":
            continue
        assert len(p.examples) >= 2, p.symbol
        for ex in p.examples:
            parsed = pg.parse_example(ex)
            assert any(part["focus"] for part in parsed["parts"]), ex
            assert "".join(part["text"] for part in parsed["parts"]) == parsed["word"]
        if p.category == "consonant":
            assert p.manner, p.symbol


def test_symbols_and_aliases_are_unique():
    symbols = [p.symbol for p in pg.GUIDE]
    assert len(symbols) == len(set(symbols))
    assert not set(pg.ALIASES) & set(symbols)
    assert pg.lookup("ɜ").symbol == "ɝ" and pg.lookup("g").symbol == "ɡ"
    assert pg.lookup("ʘ") is None


def test_minimal_pairs_contrast_known_sounds():
    pairs = [p for p in pg.GUIDE if p.pair]
    assert len(pairs) >= 25
    for p in pairs:
        a, b = p.pair.words
        assert a != b
        if p.pair.contrast is not None:
            other = pg.lookup(p.pair.contrast)
            assert other is not None and other.symbol != p.symbol, p.symbol
    by = {p.symbol: p.pair.words for p in pairs}
    assert by["θ"] == ("think", "sink") and by["ɪ"] == ("ship", "sheep")
    assert by["v"] == ("very", "berry") and by["ʌ"] == ("cut", "cat")


def test_hard_sounds_are_marked():
    assert {s for s in HARD_FOR_SPANISH if not pg.lookup(s).hard} == set()


def test_sound_methods_by_class():
    method = {p.symbol: p.sound.method for p in pg.GUIDE}
    assert {method[s] for s in "i ɪ æ ɑ ʌ ʊ u ə ɚ ɝ eɪ aɪ oʊ".split()} == {"isolated"}
    assert {method[s] for s in "θ f s ʃ".split()} == {"sustained"}
    assert {method[s] for s in "v ð z ʒ m n ŋ l ɾ".split()} == {"frame"}
    assert {method[s] for s in "p b t d k ɡ tʃ dʒ h ɹ j w".split()} == {"syllable"}


def test_parse_example():
    assert pg.parse_example("[th]ink") == {
        "word": "think",
        "parts": [{"text": "th", "focus": True}, {"text": "ink", "focus": False}],
    }
    assert pg.parse_example("sof[a]")["parts"][-1] == {"text": "a", "focus": True}


def test_phoneme_tips_come_from_the_guide():
    assert PHONEME_TIPS["θ"] == pg.lookup("θ").tip
    assert PHONEME_TIPS["ɜ"] == pg.lookup("ɝ").tip
    assert "a" not in PHONEME_TIPS  # Spanish sounds are never expected


def test_trim_and_normalize():
    import numpy as np

    rate = 1000
    x = np.concatenate([np.zeros(200), 0.05 * np.ones(300), np.zeros(200)]).astype(np.float32)
    y = tts.trim_and_normalize(x, rate)
    assert len(y) == 300
    assert float(np.abs(y).max()) == pytest.approx(0.05 * tts.PHONEME_MAX_GAIN)  # gain is capped
    assert tts.trim_and_normalize(np.zeros(500, np.float32), rate).size == 0


# ------------------------------------------------------------- recordings
FREE_LICENSE = re.compile(r"^(CC0|Public domain|CC BY(-SA)? \d\.\d)$")
NO_RECORDING = {"eɪ", "aɪ", "ɔɪ", "oʊ", "aʊ", "ɚ"}  # played in a word with Piper


def test_every_guide_entry_has_a_playable_source():
    sources = {}
    for p in pg.GUIDE:
        source = pa.planned_source(p)
        sources[p.symbol] = source
        assert source in ("recording", "piper"), p.symbol  # espeak is only a runtime fallback
        if source == "recording":
            rec = pa.recording_for(p)
            assert rec.path.is_file() and rec.path.read_bytes()[:4] == b"OggS", p.symbol
            assert rec.url.startswith("/static/phonemes/")
        else:
            assert pg.fallback_word(p), p.symbol
        assert p.sound.parts  # last-resort espeak-ng synthesis is always defined
    assert {s for s, src in sources.items() if src == "piper"} == NO_RECORDING
    assert sum(src == "recording" for src in sources.values()) == len(pg.GUIDE) - len(NO_RECORDING)


def test_every_bundled_recording_is_attributed():
    manifest = json.loads(pa.MANIFEST.read_text("utf-8"))["recordings"]
    files = {f.name for f in pa.AUDIO_DIR.glob("*.ogg")}
    assert files == {e["file"] for e in manifest.values()}  # no unattributed or missing files
    md = (pa.AUDIO_DIR / "ATTRIBUTION.md").read_text("utf-8")
    for symbol, e in manifest.items():
        assert pg.lookup(symbol) is not None and pg.lookup(symbol).symbol == symbol
        assert e["author"].strip() and e["title"].startswith("File:"), symbol
        assert FREE_LICENSE.match(e["license"]), (symbol, e["license"])
        assert e["license"] == "Public domain" or e["license_url"].startswith(("http://", "https://")), symbol
        assert e["source_url"].startswith("https://commons.wikimedia.org/wiki/File:"), symbol
        assert e["file"] in md and e["author"] in md
    assert set(pa.recordings()) == set(manifest)


@pytest.mark.skipif(shutil.which("ffprobe") is None, reason="ffprobe not installed")
def test_recordings_decode_as_short_mono_clips():
    import subprocess

    for rec in pa.recordings().values():
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=channels,codec_name",
             "-of", "json", str(rec.path)], capture_output=True, text=True, check=True).stdout
        info = json.loads(out)
        assert info["streams"][0]["codec_name"] == "opus" and info["streams"][0]["channels"] == 1
        assert 0.3 < float(info["format"]["duration"]) < 4.0, rec.file


# ------------------------------------------------------------- synthesizer + API
@pytest.fixture
def phoneme_synth(monkeypatch):
    s = tts.Synthesizer()
    s.specs, s.words = [], []

    def fake_espeak(spec):
        s.specs.append(spec)
        return make_wav(0.5)

    monkeypatch.setattr(tts, "espeak_phoneme_wav", fake_espeak)
    monkeypatch.setattr(s, "_piper_wav", lambda text, rate: s.words.append((text, rate)) or make_wav())
    return s


def test_synthesize_phoneme_prefers_recording_and_caches(phoneme_synth):
    a = phoneme_synth.synthesize_phoneme("θ")
    assert a is phoneme_synth.synthesize_phoneme("θ")
    assert (a.engine, a.source, a.media_type) == ("recording", "recording", "audio/ogg")
    assert a.audio == pa.recording_for(pg.lookup("θ")).path.read_bytes()
    assert phoneme_synth.specs == [] and phoneme_synth.words == []
    # An alias shares the canonical entry's cache slot.
    assert phoneme_synth.synthesize_phoneme("ɜ") is phoneme_synth.synthesize_phoneme("ɝ")


def test_synthesize_phoneme_uses_piper_word_without_recording(phoneme_synth):
    speech = phoneme_synth.synthesize_phoneme("eɪ")
    assert (speech.engine, speech.method, speech.source) == ("piper", "word", "piper")
    assert phoneme_synth.words == [("day", tts.PHONEME_FALLBACK_RATE)]
    assert phoneme_synth.specs == []


def test_synthesize_phoneme_falls_back_to_espeak(monkeypatch, phoneme_synth):
    def broken(text, rate):
        raise RuntimeError("piper broke")

    monkeypatch.setattr(phoneme_synth, "_piper_wav", broken)
    speech = phoneme_synth.synthesize_phoneme("oʊ")
    assert (speech.engine, speech.source, speech.method) == ("espeak-ng", "espeak", "isolated")
    assert phoneme_synth.specs == [pg.lookup("oʊ").sound]


def test_missing_recording_falls_back_to_word(monkeypatch, phoneme_synth):
    monkeypatch.setattr(pa, "recordings", lambda: {})
    assert pa.planned_source(pg.lookup("θ")) == "piper"
    assert phoneme_synth.synthesize_phoneme("θ").engine == "piper"
    assert phoneme_synth.words == [("think", tts.PHONEME_FALLBACK_RATE)]


def test_synthesize_phoneme_unknown(phoneme_synth):
    with pytest.raises(tts.UnknownPhoneme):
        phoneme_synth.synthesize_phoneme("ʘ")


def test_load_manifest_skips_missing_files(tmp_path):
    (tmp_path / "m.json").write_text(json.dumps({"recordings": {"θ": {
        "file": "does-not-exist.ogg", "author": "x", "license": "CC0", "source_url": "u", "title": "File:x",
    }}}))
    assert pa.load_manifest(tmp_path / "m.json") == {}
    assert pa.load_manifest(tmp_path / "missing.json") == {}


class FakePhonemeSynth:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def synthesize(self, text, rate=1.0):
        return tts.Speech(make_wav(), "piper")

    def synthesize_phoneme(self, symbol):
        self.calls.append(symbol)
        if self.error:
            raise self.error
        if pg.lookup(symbol) is None:
            raise tts.UnknownPhoneme(symbol)
        return tts.Speech(make_wav(0.6), "espeak-ng", pg.lookup(symbol).sound.method)


def make_client(synth):
    app = server.create_app(db=Database(":memory:"), recognizer=FakeRecognizer(""), synthesizer=synth)
    return TestClient(app)


def test_phonemes_endpoint():
    with make_client(FakePhonemeSynth()) as c:
        body = c.get("/api/phonemes").json()
    assert [cat["id"] for cat in body["categories"]][:4] == ["vowel", "r_colored", "diphthong", "consonant"]
    by = {p["symbol"]: p for p in body["phonemes"]}
    assert len(by) == len(pg.GUIDE)
    th = by["θ"]
    assert th["hard"] and th["pair"] == {"words": ["think", "sink"], "contrast": "s", "note": pg.lookup("θ").pair.note}
    assert th["examples"][0]["parts"][0] == {"text": "th", "focus": True}
    assert th["sound_method"] == "sustained"
    assert th["source"] == "recording" and th["recording"]["url"].endswith(".ogg")
    assert th["recording"]["license"] and th["recording"]["author"]
    assert by["eɪ"]["source"] == "piper" and by["eɪ"]["recording"] is None
    assert by["eɪ"]["listen_word"] == "day"
    assert body["aliases"]["ɜ"] == "ɝ"


def test_phoneme_tts_endpoint():
    synth = FakePhonemeSynth()
    with make_client(synth) as c:
        r = c.get("/api/tts/phoneme", params={"symbol": "ð"})
        assert r.status_code == 200
        assert r.headers["content-type"] == "audio/wav"
        assert r.headers["x-tts-engine"] == "espeak-ng" and r.headers["x-tts-method"] == "frame"
        assert r.headers["x-phoneme-source"] == "espeak"
        assert tts.wav_duration(r.content) > 0
        assert c.get("/api/tts/phoneme", params={"symbol": "ʘ"}).status_code == 404
        assert c.get("/api/tts/phoneme").status_code == 422
    assert synth.calls == ["ð", "ʘ"]
    with make_client(FakePhonemeSynth(tts.TTSError("no engine"))) as c:
        assert c.get("/api/tts/phoneme", params={"symbol": "θ"}).status_code == 503


def test_phoneme_tts_endpoint_serves_recording():
    with make_client(tts.Synthesizer()) as c:
        r = c.get("/api/tts/phoneme", params={"symbol": "θ"})
        assert r.status_code == 200
        assert r.headers["content-type"] == "audio/ogg"
        assert r.headers["x-phoneme-source"] == "recording" and r.content[:4] == b"OggS"
        static = c.get(pa.recording_for(pg.lookup("θ")).url)
        assert static.status_code == 200 and static.content == r.content


@pytest.mark.skipif(shutil.which("espeak-ng") is None, reason="espeak-ng not installed")
@pytest.mark.parametrize("symbol", ["θ", "ð", "ɪ", "i", "æ", "ʃ", "t", "v"])
def test_real_isolated_phoneme_synthesis(symbol):
    wav = tts.espeak_phoneme_wav(pg.lookup(symbol).sound)
    assert wav[:4] == b"RIFF"
    assert 0.3 < tts.wav_duration(wav) < 2.0
