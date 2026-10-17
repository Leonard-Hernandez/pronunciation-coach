import io
import sys

import numpy as np
import pytest
from fastapi.testclient import TestClient

from pronunciation_coach import server
from pronunciation_coach.db import Database
from pronunciation_coach.phonemes import expected_for_sentence
from pronunciation_coach.worker import WorkerInfo

from .conftest import fake_phonemize


class FakeRecognizer:
    idle_timeout = 1.0

    def __init__(self, phonemes):
        self.phonemes = phonemes
        self.calls = 0

    def recognize(self, audio):
        self.calls += 1
        return {"phonemes": self.phonemes, "device": "cpu", "device_name": "fake", "infer_seconds": 0.01}

    def info(self):
        return WorkerInfo(False, None, None, None, self.calls, 0)

    def shutdown(self):
        pass


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(server, "expected_for_sentence",
                        lambda text: expected_for_sentence(text, phonemize=fake_phonemize))
    monkeypatch.setattr(server, "decode_to_16k_mono", lambda data: np.zeros(16000, dtype=np.float32))
    rec = FakeRecognizer("t ɪ ŋ k ð ɪ s ɪ z ɡ ʊ d")
    app = server.create_app(db=Database(":memory:"), recognizer=rec)
    with TestClient(app) as c:
        c.rec = rec
        yield c


def test_server_does_not_import_torch():
    import subprocess

    out = subprocess.run(
        [sys.executable, "-c", "import sys, pronunciation_coach.server; print('torch' in sys.modules)"],
        capture_output=True, text=True, check=True,
    )
    assert out.stdout.strip() == "False"


def test_book_flow_and_resume(client):
    r = client.post("/api/books", data={"text": "I think this is good. The cat sat."})
    assert r.status_code == 200
    book_id = r.json()["id"]
    assert r.json()["sentence_count"] == 2

    s = client.get(f"/api/books/{book_id}/sentence").json()
    assert s["idx"] == 0 and s["text"] == "I think this is good."
    client.post(f"/api/books/{book_id}/position", json={"idx": 1})
    assert client.get(f"/api/books/{book_id}/sentence").json()["idx"] == 1
    assert client.get("/api/books").json()["last_book_id"] == book_id
    # Out-of-range positions are clamped.
    assert client.get(f"/api/books/{book_id}/sentence?idx=99").json()["idx"] == 1


def test_upload_file(client):
    files = {"file": ("story.txt", io.BytesIO(b"One. Two words here."), "text/plain")}
    r = client.post("/api/books", files=files)
    assert r.json()["title"] == "story" and r.json()["sentence_count"] == 2


def test_score_and_stats(client):
    files = {"audio": ("a.webm", io.BytesIO(b"fake"), "audio/webm")}
    r = client.post("/api/score", files=files, data={"text": "I think this is good.", "session_id": "s1"})
    assert r.status_code == 200, r.text
    body = r.json()
    # The fake recognizer misses /aɪ/ ("I") and says /t/ for /θ/.
    assert 0 < body["accuracy"] < 1
    msgs = [e["message"] for e in body["errors"]]
    assert "think: said /t/, expected /θ/" in msgs
    assert body["words"][1]["status"] == "unsure"

    stats = client.get("/api/stats").json()
    assert stats["overall"]["attempts"] == 1
    assert stats["by_day"][0]["attempts"] == 1
    top = {(e["expected"], e["actual"]): e for e in stats["top_errors"]}
    assert ("θ", "t") in top and top[("θ", "t")]["tip"]


def test_worker_status(client):
    assert client.get("/api/worker").json()["alive"] is False


def test_index_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "Pronunciation Coach" in r.text
