"""SQLite persistence: books, sentences, sections, reading position, attempts and stats."""

from __future__ import annotations

import functools
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS books (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    filename TEXT NOT NULL,
    created_at TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    sentence_count INTEGER NOT NULL DEFAULT 0,
    last_opened_at TEXT
);
CREATE TABLE IF NOT EXISTS sentences (
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (book_id, idx)
);
CREATE TABLE IF NOT EXISTS sections (
    book_id INTEGER NOT NULL REFERENCES books(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('chapter', 'page')),
    idx INTEGER NOT NULL,
    title TEXT,
    start_sentence INTEGER NOT NULL,
    PRIMARY KEY (book_id, kind, idx)
);
CREATE INDEX IF NOT EXISTS idx_sections_start ON sections(book_id, kind, start_sentence);
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY,
    book_id INTEGER REFERENCES books(id) ON DELETE SET NULL,
    sentence_idx INTEGER,
    sentence TEXT NOT NULL,
    accuracy REAL NOT NULL,
    session_id TEXT,
    created_at TEXT NOT NULL,
    expected TEXT,
    recognized TEXT,
    words_json TEXT
);
CREATE TABLE IF NOT EXISTS attempt_errors (
    id INTEGER PRIMARY KEY,
    attempt_id INTEGER NOT NULL REFERENCES attempts(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    expected TEXT,
    actual TEXT,
    word TEXT
);
CREATE INDEX IF NOT EXISTS idx_attempts_created ON attempts(created_at);
CREATE INDEX IF NOT EXISTS idx_errors_attempt ON attempt_errors(attempt_id);
CREATE TABLE IF NOT EXISTS writing_submissions (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    task_id TEXT,
    task_title TEXT,
    task_json TEXT,
    text TEXT NOT NULL,
    word_count INTEGER NOT NULL,
    seconds_spent INTEGER,
    model TEXT,
    task_achievement INTEGER,
    coherence_cohesion INTEGER,
    grammar INTEGER,
    vocabulary INTEGER,
    overall INTEGER,
    cefr_estimate TEXT,
    result_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS writing_errors (
    id INTEGER PRIMARY KEY,
    submission_id INTEGER NOT NULL REFERENCES writing_submissions(id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    lesson_id TEXT,
    original TEXT,
    correction TEXT
);
CREATE INDEX IF NOT EXISTS idx_writing_created ON writing_submissions(created_at);
CREATE INDEX IF NOT EXISTS idx_writing_errors_sub ON writing_errors(submission_id);
"""


def _locked(fn):
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return fn(self, *args, **kwargs)

    return wrapper


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.executescript(SCHEMA)
        self._lock = threading.RLock()

    def close(self) -> None:
        self._conn.close()

    # ------------------------------------------------------------------ books
    @_locked
    def add_book(self, title: str, filename: str, sentences: list[str],
                 chapters: list[tuple[str, int]] = (), page_starts: list[int] | None = None) -> int:
        """Chapters are (title, start sentence); page_starts are stored only for real (PDF) pages."""
        with self._conn:
            return self._insert_book(title, filename, sentences, chapters, page_starts)

    def _insert_book(self, title: str, filename: str, sentences: list[str],
                     chapters: list[tuple[str, int]], page_starts: list[int] | None) -> int:
        cur = self._conn.execute(
            "INSERT INTO books (title, filename, created_at, sentence_count, last_opened_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (title, filename, _now(), len(sentences), _now()),
        )
        self._insert_content(cur.lastrowid, sentences, chapters, page_starts)
        return cur.lastrowid

    @staticmethod
    def _remap_position(old_text: str | None, old_idx: int, sentences: list[str]) -> int:
        """Find the old current sentence in the new text (nearest match wins), else clamp."""
        matches = [i for i, s in enumerate(sentences) if s == old_text] if old_text is not None else []
        if matches:
            return min(matches, key=lambda i: (abs(i - old_idx), i))
        return max(0, min(old_idx, len(sentences) - 1))

    @_locked
    def replace_book_by_filename(self, title: str, filename: str, sentences: list[str],
                                 chapters: list[tuple[str, int]] = (),
                                 page_starts: list[int] | None = None) -> tuple[int, bool]:
        """Add a book, or re-import it in place when a book with this exact filename exists.

        An existing book keeps its id, attempts and last_opened_at; its sentences and sections
        are replaced and the reading position follows the current sentence's text. With several
        matches, the most recently opened one is updated. Returns (book_id, updated).
        """
        with self._conn:
            row = self._conn.execute(
                "SELECT id, position FROM books WHERE filename = ?"
                " ORDER BY COALESCE(last_opened_at, created_at) DESC, id DESC LIMIT 1", (filename,),
            ).fetchone()
            if row is None:
                return self._insert_book(title, filename, sentences, chapters, page_starts), False
            book_id, old_idx = row["id"], row["position"]
            old = self._conn.execute(
                "SELECT text FROM sentences WHERE book_id = ? AND idx = ?", (book_id, old_idx),
            ).fetchone()
            position = self._remap_position(old["text"] if old else None, old_idx, sentences)
            self._conn.execute("DELETE FROM sentences WHERE book_id = ?", (book_id,))
            self._conn.execute("DELETE FROM sections WHERE book_id = ?", (book_id,))
            self._conn.execute(
                "UPDATE books SET title = ?, sentence_count = ?, position = ? WHERE id = ?",
                (title, len(sentences), position, book_id),
            )
            self._insert_content(book_id, sentences, chapters, page_starts)
            return book_id, True

    def _insert_content(self, book_id: int, sentences: list[str],
                        chapters: list[tuple[str, int]], page_starts: list[int] | None) -> None:
        self._conn.executemany(
            "INSERT INTO sentences (book_id, idx, text) VALUES (?, ?, ?)",
            [(book_id, i, s) for i, s in enumerate(sentences)],
        )
        self._conn.executemany(
            "INSERT INTO sections (book_id, kind, idx, title, start_sentence) VALUES (?,?,?,?,?)",
            [(book_id, "chapter", i, t, start) for i, (t, start) in enumerate(chapters)]
            + [(book_id, "page", i, str(i + 1), start) for i, start in enumerate(page_starts or [])],
        )

    @_locked
    def sections(self, book_id: int, kind: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT idx, title, start_sentence AS start FROM sections"
            " WHERE book_id = ? AND kind = ? ORDER BY idx", (book_id, kind),
        ).fetchall()
        return [dict(r) for r in rows]

    @_locked
    def section(self, book_id: int, kind: str, idx: int) -> dict | None:
        row = self._conn.execute(
            "SELECT idx, title, start_sentence AS start FROM sections"
            " WHERE book_id = ? AND kind = ? AND idx = ?", (book_id, kind, idx),
        ).fetchone()
        return dict(row) if row else None

    @_locked
    def section_at(self, book_id: int, kind: str, sentence_idx: int) -> dict | None:
        """The last section of this kind starting at or before the sentence."""
        row = self._conn.execute(
            "SELECT idx, title, start_sentence AS start FROM sections"
            " WHERE book_id = ? AND kind = ? AND start_sentence <= ?"
            " ORDER BY start_sentence DESC, idx DESC LIMIT 1", (book_id, kind, sentence_idx),
        ).fetchone()
        return dict(row) if row else None

    @_locked
    def section_count(self, book_id: int, kind: str) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM sections WHERE book_id = ? AND kind = ?", (book_id, kind),
        ).fetchone()[0]

    @_locked
    def list_books(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, title, filename, created_at, position, sentence_count, last_opened_at,"
            " EXISTS (SELECT 1 FROM sections s WHERE s.book_id = books.id AND s.kind = 'chapter')"
            " AS has_chapters,"
            " EXISTS (SELECT 1 FROM sections s WHERE s.book_id = books.id AND s.kind = 'page')"
            " AS has_pages"
            " FROM books ORDER BY COALESCE(last_opened_at, created_at) DESC"
        ).fetchall()
        return [dict(r) | {"has_chapters": bool(r["has_chapters"]), "has_pages": bool(r["has_pages"])}
                for r in rows]

    @_locked
    def get_book(self, book_id: int) -> dict | None:
        row = self._conn.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
        return dict(row) if row else None

    @_locked
    def delete_book(self, book_id: int) -> bool:
        with self._conn:
            return self._conn.execute("DELETE FROM books WHERE id = ?", (book_id,)).rowcount > 0

    @_locked
    def get_sentence(self, book_id: int, idx: int) -> str | None:
        row = self._conn.execute(
            "SELECT text FROM sentences WHERE book_id = ? AND idx = ?", (book_id, idx)
        ).fetchone()
        return row["text"] if row else None

    @_locked
    def set_position(self, book_id: int, idx: int) -> None:
        with self._conn:
            self._conn.execute(
                "UPDATE books SET position = ?, last_opened_at = ? WHERE id = ?",
                (idx, _now(), book_id),
            )

    @_locked
    def last_book_id(self) -> int | None:
        row = self._conn.execute(
            "SELECT id FROM books ORDER BY COALESCE(last_opened_at, created_at) DESC LIMIT 1"
        ).fetchone()
        return row["id"] if row else None

    # --------------------------------------------------------------- attempts
    @_locked
    def add_attempt(self, *, book_id: int | None, sentence_idx: int | None, sentence: str,
                    accuracy: float, session_id: str | None, expected: list[str],
                    recognized: list[str], words: list[dict], errors: list[dict]) -> int:
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO attempts (book_id, sentence_idx, sentence, accuracy, session_id,"
                " created_at, expected, recognized, words_json) VALUES (?,?,?,?,?,?,?,?,?)",
                (book_id, sentence_idx, sentence, accuracy, session_id, _now(),
                 " ".join(expected), " ".join(recognized), json.dumps(words, ensure_ascii=False)),
            )
            attempt_id = cur.lastrowid
            self._conn.executemany(
                "INSERT INTO attempt_errors (attempt_id, kind, expected, actual, word)"
                " VALUES (?,?,?,?,?)",
                [(attempt_id, e["kind"], e.get("expected"), e.get("actual"), e.get("word"))
                 for e in errors],
            )
            return attempt_id

    @_locked
    def stats(self, *, top: int = 15, recent: int = 50) -> dict:
        c = self._conn
        overall = dict(c.execute(
            "SELECT COUNT(*) AS attempts, AVG(accuracy) AS avg_accuracy,"
            " COUNT(DISTINCT session_id) AS sessions FROM attempts"
        ).fetchone())
        by_day = [dict(r) for r in c.execute(
            "SELECT substr(datetime(created_at, 'localtime'), 1, 10) AS day,"
            " COUNT(*) AS attempts, AVG(accuracy) AS avg_accuracy"
            " FROM attempts GROUP BY day ORDER BY day"
        )]
        by_session = [dict(r) for r in c.execute(
            "SELECT session_id, MIN(created_at) AS started_at, COUNT(*) AS attempts,"
            " AVG(accuracy) AS avg_accuracy FROM attempts WHERE session_id IS NOT NULL"
            " GROUP BY session_id ORDER BY started_at DESC LIMIT 20"
        )]
        recent_rows = [dict(r) for r in c.execute(
            "SELECT id, created_at, accuracy, sentence FROM attempts ORDER BY id DESC LIMIT ?",
            (recent,),
        )][::-1]
        top_errors = [dict(r) for r in c.execute(
            "SELECT kind, expected, actual, COUNT(*) AS count,"
            " GROUP_CONCAT(DISTINCT word) AS words FROM attempt_errors"
            " WHERE kind != 'close'"
            " GROUP BY kind, expected, actual ORDER BY count DESC LIMIT ?",
            (top,),
        )]
        return {"overall": overall, "by_day": by_day, "by_session": by_session,
                "recent": recent_rows, "top_errors": top_errors}

    # ---------------------------------------------------------------- writing
    @_locked
    def add_writing(self, *, task: dict | None, text: str, result: dict,
                    seconds_spent: int | None = None) -> int:
        scores = result["scores"]
        with self._conn:
            cur = self._conn.execute(
                "INSERT INTO writing_submissions (created_at, task_id, task_title, task_json, text,"
                " word_count, seconds_spent, model, task_achievement, coherence_cohesion, grammar,"
                " vocabulary, overall, cefr_estimate, result_json)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (_now(), (task or {}).get("id"), (task or {}).get("title"),
                 json.dumps(task, ensure_ascii=False) if task else None, text, result["word_count"],
                 seconds_spent, result.get("model"), scores["task_achievement"],
                 scores["coherence_cohesion"], scores["grammar"], scores["vocabulary"],
                 result["overall"], result.get("cefr_estimate"), json.dumps(result, ensure_ascii=False)),
            )
            sub_id = cur.lastrowid
            self._conn.executemany(
                "INSERT INTO writing_errors (submission_id, category, lesson_id, original, correction)"
                " VALUES (?,?,?,?,?)",
                [(sub_id, e["category"], e.get("lesson_id"), e.get("original"), e.get("correction"))
                 for e in result["errors"] + result.get("unlocated", [])],
            )
            return sub_id

    @_locked
    def list_writing(self, limit: int = 100) -> list[dict]:
        rows = self._conn.execute(
            "SELECT s.id, s.created_at, s.task_id, s.task_title, s.word_count, s.overall,"
            " s.cefr_estimate, s.task_achievement, s.coherence_cohesion, s.grammar, s.vocabulary,"
            " (SELECT COUNT(*) FROM writing_errors e WHERE e.submission_id = s.id) AS error_count"
            " FROM writing_submissions s ORDER BY s.id DESC LIMIT ?", (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    @_locked
    def get_writing(self, sub_id: int) -> dict | None:
        row = self._conn.execute("SELECT * FROM writing_submissions WHERE id = ?", (sub_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        data["task"] = json.loads(data.pop("task_json")) if data.get("task_json") else None
        data["result"] = json.loads(data.pop("result_json"))
        return data

    @_locked
    def delete_writing(self, sub_id: int) -> bool:
        with self._conn:
            return self._conn.execute("DELETE FROM writing_submissions WHERE id = ?", (sub_id,)).rowcount > 0

    @_locked
    def writing_stats(self, *, recent_window: int = 5) -> dict:
        c = self._conn
        overall = dict(c.execute(
            "SELECT COUNT(*) AS submissions, AVG(overall) AS avg_overall, SUM(word_count) AS words"
            " FROM writing_submissions"
        ).fetchone())
        timeline = [dict(r) for r in c.execute(
            "SELECT id, created_at, task_title, overall, task_achievement, coherence_cohesion, grammar,"
            " vocabulary, cefr_estimate FROM writing_submissions ORDER BY id"
        )]
        categories = [dict(r) for r in c.execute(
            "SELECT category, COUNT(*) AS count, COUNT(DISTINCT submission_id) AS submissions,"
            " (SELECT e2.lesson_id FROM writing_errors e2 WHERE e2.category = e.category"
            "  AND e2.lesson_id IS NOT NULL GROUP BY e2.lesson_id ORDER BY COUNT(*) DESC LIMIT 1) AS top_lesson"
            " FROM writing_errors e GROUP BY category ORDER BY count DESC, category"
        )]
        # Same counts restricted to the latest submissions, to suggest what to review now.
        recent_categories = [dict(r) for r in c.execute(
            "SELECT category, lesson_id, COUNT(*) AS count FROM writing_errors WHERE submission_id IN"
            " (SELECT id FROM writing_submissions ORDER BY id DESC LIMIT ?)"
            " GROUP BY category, lesson_id ORDER BY count DESC", (recent_window,),
        )]
        examples = {}
        for r in c.execute(
            "SELECT category, original, correction FROM writing_errors ORDER BY id DESC"
        ):
            ex = examples.setdefault(r["category"], [])
            if len(ex) < 3 and r["original"] and (r["original"], r["correction"]) not in ex:
                ex.append((r["original"], r["correction"]))
        for cat in categories:
            cat["examples"] = [{"original": o, "correction": k} for o, k in examples.get(cat["category"], [])]
        return {"overall": overall, "timeline": timeline, "categories": categories,
                "recent_categories": recent_categories}
