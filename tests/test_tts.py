import io
import wave

import pytest
from fastapi.testclient import TestClient

from pronunciation_coach import server, tts
from pronunciation_coach.db import Database

from .test_api import FakeRecognizer


def make_wav(seconds: float = 0.1, rate: int = 22050) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\0\0" * int(seconds * rate))
    return buf.getvalue()


class FakeSynth:
    def __init__(self, error: Exception | None = None):
        self.calls = []
        self.error = error

    def synthesize(self, text, rate=1.0):
        self.calls.append((text, rate))
        if self.error:
            raise self.error
        return tts.Speech(make_wav(), "piper")


def make_client(synth):
    app = server.create_app(db=Database(":memory:"), recognizer=FakeRecognizer(""), synthesizer=synth)
    return TestClient(app)


def test_tts_endpoint_returns_wav():
    synth = FakeSynth()
    with make_client(synth) as c:
        r = c.get("/api/tts", params={"text": "I think", "rate": 0.8})
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert r.headers["x-tts-engine"] == "piper"
    assert r.content[:4] == b"RIFF" and tts.wav_duration(r.content) > 0
    assert synth.calls == [("I think", 0.8)]


def test_tts_endpoint_errors():
    with make_client(FakeSynth(tts.TTSInputError("empty text"))) as c:
        assert c.get("/api/tts", params={"text": " "}).status_code == 400
    with make_client(FakeSynth(tts.TTSError("no engine"))) as c:
        assert c.get("/api/tts", params={"text": "hi"}).status_code == 503
    with make_client(FakeSynth()) as c:
        assert c.get("/api/tts").status_code == 422  # text is required


@pytest.fixture
def synth(monkeypatch):
    s = tts.Synthesizer()
    s.piper_calls = []

    def fake_piper(text, rate):
        s.piper_calls.append((text, rate))
        return make_wav()

    monkeypatch.setattr(s, "_piper_wav", fake_piper)
    monkeypatch.setattr(tts, "espeak_wav", lambda text, rate=1.0: pytest.fail("espeak used"))
    return s


def test_synthesizer_caches_and_normalizes(synth):
    a = synth.synthesize("  I   think ", 0.8)
    b = synth.synthesize("I think", 0.8)
    assert a is b and a.engine == "piper"
    assert synth.piper_calls == [("I think", 0.8)]
    synth.synthesize("I think", 1.0)  # different rate -> new entry
    assert len(synth.piper_calls) == 2


def test_synthesizer_rate_clamped_and_length_limit(synth):
    synth.synthesize("hi", 10)
    assert synth.piper_calls[-1] == ("hi", tts.MAX_RATE)
    with pytest.raises(tts.TTSInputError):
        synth.synthesize("x" * (tts.MAX_TEXT_CHARS + 1))
    with pytest.raises(tts.TTSInputError):
        synth.synthesize("   ")


def test_synthesizer_lru_eviction(synth):
    synth.cache_size = 2
    for word in ("a", "b", "c"):
        synth.synthesize(word)
    synth.synthesize("a")  # evicted -> synthesized again
    assert [t for t, _ in synth.piper_calls] == ["a", "b", "c", "a"]


def test_falls_back_to_espeak_when_piper_fails(monkeypatch):
    s = tts.Synthesizer()

    def broken_load():
        raise RuntimeError("no voice")

    monkeypatch.setattr(s, "_load_piper", broken_load)
    espeak_calls = []
    monkeypatch.setattr(tts, "espeak_wav", lambda text, rate=1.0: espeak_calls.append(rate) or make_wav())
    assert s.synthesize("hello", 0.8).engine == "espeak-ng"
    s.synthesize("again")
    assert espeak_calls == [0.8, 1.0]


def test_piper_length_scale_grows_when_slower(monkeypatch):
    seen = []

    class FakeVoice:
        class config:
            length_scale = 1.0

        def synthesize_wav(self, text, wav_file, syn_config=None):
            seen.append(syn_config.length_scale)
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(22050)
            wav_file.writeframes(b"\0\0" * 100)

    pytest.importorskip("piper")
    s = tts.Synthesizer()
    monkeypatch.setattr(s, "_load_piper", lambda: FakeVoice())
    s.synthesize("slow", 0.5)
    s.synthesize("fast", 1.25)
    assert seen == [2.0, 0.8]


def test_voice_url():
    assert tts.voice_url("en_US-lessac-medium", "en_US-lessac-medium.onnx").startswith(
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/"
        "en_US-lessac-medium.onnx"
    )
