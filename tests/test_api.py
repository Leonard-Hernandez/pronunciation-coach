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
    db = Database(":memory:")
    app = server.create_app(db=db, recognizer=rec)
    with TestClient(app) as c:
        c.rec = rec
        c.db = db
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


def _structured_book(client):
    text = "\n\n".join(
        ["Chapter 1"] + [f"Line {i} is here." for i in range(20)]
        + ["Chapter 2: The End"] + [f"Last {i} is here." for i in range(10)]
    )
    return client.post("/api/books", data={"text": text}).json()["id"]


def test_toc_and_jump(client):
    book_id = _structured_book(client)
    toc = client.get(f"/api/books/{book_id}/toc").json()
    assert toc["chapters"] == [{"idx": 0, "title": "Chapter 1", "start": 0},
                               {"idx": 1, "title": "Chapter 2: The End", "start": 21}]
    assert toc["real_pages"] is False and toc["total"] == 32
    assert toc["page_starts"] == [0, 15, 30] and toc["page_count"] == 3

    s = client.post(f"/api/books/{book_id}/jump", json={"chapter": 1}).json()
    assert s["idx"] == 21 and s["chapter"] == {"idx": 1, "title": "Chapter 2: The End"}
    assert s["page"] == 2 and s["page_count"] == 3
    s = client.post(f"/api/books/{book_id}/jump", json={"page": 3}).json()
    assert s["idx"] == 30 and s["page"] == 3
    assert client.get(f"/api/books/{book_id}/sentence").json()["idx"] == 30

    assert client.post(f"/api/books/{book_id}/jump", json={"chapter": 2}).status_code == 404
    assert client.post(f"/api/books/{book_id}/jump", json={"page": 0}).status_code == 404
    assert client.post(f"/api/books/{book_id}/jump", json={"page": 4}).status_code == 404
    assert client.post(f"/api/books/{book_id}/jump", json={}).status_code == 422
    assert client.post(f"/api/books/{book_id}/jump", json={"chapter": 0, "page": 1}).status_code == 422
    assert client.post("/api/books/999/jump", json={"page": 1}).status_code == 404
    assert client.get("/api/books/999/toc").status_code == 404

    listed = {b["id"]: b for b in client.get("/api/books").json()["books"]}[book_id]
    assert listed["chapter"]["title"] == "Chapter 2: The End"
    assert listed["page"] == 3 and listed["page_count"] == 3


def test_legacy_book_without_sections(client):
    db = client.db
    book_id = db.add_book("Old", "old.txt", [f"Sentence {i}." for i in range(40)])
    toc = client.get(f"/api/books/{book_id}/toc").json()
    assert toc["chapters"] == [] and toc["real_pages"] is False
    assert toc["page_starts"] == [0, 15, 30]
    s = client.post(f"/api/books/{book_id}/position", json={"idx": 16}).json()
    assert s["chapter"] is None and s["page"] == 2 and s["page_count"] == 3
    assert client.post(f"/api/books/{book_id}/jump", json={"chapter": 0}).status_code == 404
    assert client.post(f"/api/books/{book_id}/jump", json={"page": 3}).json()["idx"] == 30


def test_real_pages_are_used(client):
    db = client.db
    book_id = db.add_book("Pdf", "b.pdf", ["A.", "B.", "C.", "D."], [("Intro", 0)], [0, 2, 2, 3])
    toc = client.get(f"/api/books/{book_id}/toc").json()
    assert toc["real_pages"] is True and toc["page_starts"] == [0, 2, 2, 3]
    assert client.post(f"/api/books/{book_id}/position", json={"idx": 2}).json()["page"] == 3
    assert client.post(f"/api/books/{book_id}/jump", json={"page": 4}).json()["idx"] == 3
    db.delete_book(book_id)
    assert db.sections(book_id, "page") == []


def test_existing_database_gains_sections_table(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT NOT NULL, filename TEXT NOT NULL,"
        " created_at TEXT NOT NULL, position INTEGER NOT NULL DEFAULT 0,"
        " sentence_count INTEGER NOT NULL DEFAULT 0, last_opened_at TEXT);"
        "INSERT INTO books VALUES (1, 'Old', 'old.txt', '2026-01-01', 3, 20, NULL);"
    )
    conn.close()
    db = Database(path)
    assert db.sections(1, "chapter") == [] and db.get_book(1)["position"] == 3
    db.close()


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
    assert r.headers["cache-control"] == "no-cache"
    version = server.asset_version()
    assert len(version) == 12 and server.ASSET_VERSION_PLACEHOLDER not in r.text
    for asset in ("app.js", "writing.js", "style.css"):
        assert f"/static/{asset}?v={version}" in r.text
    assert client.get(f"/static/app.js?v={version}").status_code == 200


def _upload(client, name, text):
    return client.post("/api/books", files={"file": (name, io.BytesIO(text.encode()), "text/plain")})


def test_reupload_updates_book_in_place(client):
    db = client.db
    old = [f"Line {i} is here." for i in range(30)]
    # A book imported before chapters existed: same file name, no sections.
    book_id = db.add_book("Novel", "novel.txt", old)
    db.set_position(book_id, 12)
    db.add_attempt(book_id=book_id, sentence_idx=12, sentence=old[12], accuracy=0.5, session_id="s",
                   expected=[], recognized=[], words=[], errors=[])
    opened = db.get_book(book_id)["last_opened_at"]
    assert client.get("/api/books").json()["books"][0]["has_chapters"] is False

    text = "\n\n".join(["Preface text is here.", "Chapter 1"] + old[:10] + ["Chapter 2"] + old[10:])
    r = _upload(client, "novel.txt", text)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"id": book_id, "title": "novel", "sentence_count": 33, "updated": True}

    books = client.get("/api/books").json()["books"]
    assert len(books) == 1 and books[0]["has_chapters"] is True
    book = db.get_book(book_id)
    assert book["position"] == 15 and db.get_sentence(book_id, 15) == old[12]
    assert book["last_opened_at"] == opened
    assert db.stats()["overall"]["attempts"] == 1
    toc = client.get(f"/api/books/{book_id}/toc").json()
    assert [c["title"] for c in toc["chapters"]] == ["Chapter 1", "Chapter 2"]
    assert toc["chapters"][0]["start"] == 1
    s = client.get(f"/api/books/{book_id}/sentence").json()
    assert s["idx"] == 15 and s["chapter"]["title"] == "Chapter 2"


def test_reupload_position_fallbacks():
    remap = Database._remap_position
    assert remap("B.", 5, ["B.", "x", "x", "x", "x", "x", "B.", "x"]) == 6  # nearest duplicate
    assert remap("Gone.", 5, ["a", "b", "c"]) == 2                          # clamped
    assert remap("Gone.", 1, ["a", "b", "c"]) == 1


def test_reupload_without_match_clamps(client):
    book_id = _upload(client, "short.txt", " ".join(f"Old {i} here." for i in range(20))).json()["id"]
    client.post(f"/api/books/{book_id}/position", json={"idx": 15})
    r = _upload(client, "short.txt", "New one here. New two here.").json()
    assert r["id"] == book_id and r["updated"] is True
    assert client.db.get_book(book_id)["position"] == 1


def test_pasted_text_never_dedupes(client):
    a = client.post("/api/books", data={"text": "Same text here."}).json()
    b = client.post("/api/books", data={"text": "Same text here."}).json()
    assert a["id"] != b["id"] and a["updated"] is False and b["updated"] is False
    # A file that happens to be called like pasted text does not replace a pasted book either.
    c = _upload(client, "pasted.txt", "Other text here.").json()
    assert c["id"] not in (a["id"], b["id"]) and c["updated"] is False
    assert len(client.get("/api/books").json()["books"]) == 3


def test_different_filenames_create_books(client):
    a = _upload(client, "a.txt", "One here.").json()
    b = _upload(client, "b.txt", "One here.").json()
    assert a["id"] != b["id"] and not b["updated"]
