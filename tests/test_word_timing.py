import io

import numpy as np
from fastapi.testclient import TestClient

from pronunciation_coach import server
from pronunciation_coach.db import Database
from pronunciation_coach.phonemes import ExpectedWord, expected_for_sentence
from pronunciation_coach.scoring import SPAN_PAD, score
from pronunciation_coach.worker import WorkerInfo, ctc_collapse

from .conftest import fake_phonemize

VOCAB = {0: "<pad>", 1: "θ", 2: "ɪ", 3: "ŋ", 4: "k", 5: "|", 6: "s"}


def test_ctc_collapse_keeps_time():
    # frames: pad pad θ θ ɪ pad ŋ k k | pad s
    ids = [0, 0, 1, 1, 2, 0, 3, 4, 4, 5, 0, 6]
    tokens, spans = ctc_collapse(ids, VOCAB.get, 0.02)
    assert tokens == ["θ", "ɪ", "ŋ", "k", "s"]
    assert spans == [[0.04, 0.08], [0.08, 0.1], [0.12, 0.14], [0.14, 0.18], [0.22, 0.24]]
    assert ctc_collapse([], VOCAB.get, 0.02) == ([], [])


def test_word_spans_from_phoneme_spans():
    words = [ExpectedWord("I", ["aɪ"]), ExpectedWord("think", ["θ", "ɪ", "ŋ", "k"]),
             ExpectedWord("so", ["s", "oʊ"])]
    rec = ["aɪ", "t", "ɪ", "ŋ", "k", "s", "oʊ"]
    spans = [[0.10, 0.20], [0.40, 0.45], [0.45, 0.50], [0.50, 0.55], [0.55, 0.60], [0.90, 1.00], [1.00, 1.20]]
    r = score(words, rec, spans, audio_seconds=1.25)
    got = [w.heard_span for w in r.words]
    assert got[0] == [round(0.10 - SPAN_PAD, 3), round(0.20 + SPAN_PAD, 3)]
    assert got[1] == [round(0.40 - SPAN_PAD, 3), round(0.60 + SPAN_PAD, 3)]
    assert got[2] == [round(1.00 - 0.10 - SPAN_PAD, 3), 1.25]  # clamped to the audio length


def test_word_spans_missing_word_and_no_timings():
    words = [ExpectedWord("the", ["ð", "ə"]), ExpectedWord("cat", ["k", "æ", "t"])]
    r = score(words, ["k", "æ", "t"], [[0.5, 0.6], [0.6, 0.7], [0.7, 0.8]], audio_seconds=1.0)
    assert r.words[0].heard_span is None and r.words[1].heard_span is not None
    # Without timings (or with a length mismatch) nothing breaks and there are no spans.
    assert all(w.heard_span is None for w in score(words, ["k", "æ", "t"]).words)
    assert all(w.heard_span is None for w in score(words, ["k", "æ", "t"], [[0, 1]]).words)


def test_recognized_with_spans_follows_normalization():
    reply = {"phonemes": "ð ˈɪ s", "spans": [[0, 0.1], [0.1, 0.2], [0.2, 0.3]]}
    tokens, spans = server._recognized_with_spans(reply)
    assert len(tokens) == len(spans) and tokens[0] == "ð"
    assert server._recognized_with_spans({"phonemes": "ð ɪ s"}) == (["ð", "ɪ", "s"], None)
    assert server._recognized_with_spans({"phonemes": "ð ɪ s", "spans": [[0, 1]]})[1] is None


class _TimedRecognizer:
    idle_timeout = 1.0

    def recognize(self, audio):
        phs = "t ɪ ŋ k ð ɪ s ɪ z ɡ ʊ d".split()
        return {"phonemes": " ".join(phs), "spans": [[0.3 + 0.1 * i, 0.4 + 0.1 * i] for i in range(len(phs))],
                "audio_seconds": 2.0, "device": "cpu", "device_name": "fake", "infer_seconds": 0.01}

    def info(self):
        return WorkerInfo(False, None, None, None, 0, 0)

    def shutdown(self):
        pass


def test_score_endpoint_returns_word_spans(monkeypatch):
    monkeypatch.setattr(server, "expected_for_sentence",
                        lambda text: expected_for_sentence(text, phonemize=fake_phonemize))
    monkeypatch.setattr(server, "decode_to_16k_mono", lambda data: np.zeros(16000, dtype=np.float32))
    app = server.create_app(db=Database(":memory:"), recognizer=_TimedRecognizer())
    with TestClient(app) as c:
        r = c.post("/api/score", files={"audio": ("a.webm", io.BytesIO(b"x"), "audio/webm")},
                   data={"text": "I think this is good."})
    words = r.json()["words"]
    assert words[0]["heard_span"] is None  # "I" was not heard
    think = words[1]["heard_span"]
    assert think == [round(0.3 - SPAN_PAD, 3), round(0.7 + SPAN_PAD, 3)]
    assert all(w["heard_span"] for w in words[1:])
