"""FastAPI application. Must never import torch (recognition lives in worker.py's child)."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from .audio import AudioError, decode_to_16k_mono
from .books import UnsupportedFormat, extract, split_sentences
from .db import Database
from .phonemes import EspeakUnavailable, espeak_available, expected_for_sentence, split_words, tokenize_ipa
from .scoring import score
from .phoneme_guide import guide_payload
from . import grammar_lessons, writing
from .llm import LLMError, LLMProvider, LLMRateLimited, LLMUnavailable, build_provider
from .writing_tasks import EXAMS, GENRES, TASKS_BY_ID, tasks_payload
from .tts import Synthesizer, TTSError, TTSInputError, UnknownPhoneme
from .worker import RecognizerClient, RecognizerError

log = logging.getLogger("pronunciation_coach")
STATIC_DIR = Path(__file__).parent / "static"
MAX_UPLOAD_BYTES = 200 * 1024 * 1024


class Position(BaseModel):
    idx: int


class CorrectRequest(BaseModel):
    text: str
    task: dict | None = None
    seconds_spent: int | None = None


class GenerateTaskRequest(BaseModel):
    exam: str | None = None
    genre: str | None = None
    topic: str | None = None


class LessonAnswers(BaseModel):
    answers: list[str | None]


def _clean_task(task: dict | None) -> dict | None:
    """Library tasks are taken from the server; generated ones are trimmed to known fields."""
    if not task:
        return None
    if task.get("id") in TASKS_BY_ID:
        return TASKS_BY_ID[task["id"]]
    words = task.get("words") or [120, 200]
    try:
        words = [int(words[0]), int(words[1])]
    except (TypeError, ValueError, IndexError):
        words = [120, 200]
    return {
        "id": None, "generated": True,
        "exam": task.get("exam") if task.get("exam") in EXAMS else "work",
        "genre": task.get("genre") if task.get("genre") in GENRES else "email_formal",
        "register": str(task.get("register") or "")[:20],
        "title": str(task.get("title") or "Custom task")[:120],
        "prompt": str(task.get("prompt") or "")[:1500],
        "points": [str(p)[:200] for p in (task.get("points") or [])][:6],
        "words": words, "minutes": int(task.get("minutes") or 30) if str(task.get("minutes") or "").isdigit() else 30,
    }


def _recognized_with_spans(reply: dict) -> tuple[list[str], list[list[float]] | None]:
    """Normalize the recognizer's phonemes, carrying each raw token's time span along.

    tokenize_ipa works chunk by chunk, so normalizing each raw token separately gives the
    same sequence; if that ever stops being true, timings are dropped (no word playback).
    """
    recognized = tokenize_ipa(reply["phonemes"])
    raw_spans = reply.get("spans")
    raw = reply["phonemes"].split()
    if not raw_spans or len(raw_spans) != len(raw):
        return recognized, None
    tokens: list[str] = []
    spans: list[list[float]] = []
    for tok, span in zip(raw, raw_spans):
        for t in tokenize_ipa(tok):
            tokens.append(t)
            spans.append(span)
    return (recognized, spans) if tokens == recognized else (recognized, None)


def _llm_http_error(exc: LLMError) -> HTTPException:
    if isinstance(exc, LLMRateLimited):
        headers = {"Retry-After": str(int(exc.retry_after) + 1)} if exc.retry_after else None
        return HTTPException(429, str(exc), headers=headers)
    if isinstance(exc, LLMUnavailable):
        return HTTPException(503, str(exc))
    return HTTPException(502, str(exc))


def create_app(db: Database | None = None, recognizer: RecognizerClient | None = None,
               synthesizer: Synthesizer | None = None, llm: LLMProvider | None = None) -> FastAPI:
    state = {"db": db, "rec": recognizer, "tts": synthesizer or Synthesizer(), "llm": llm}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if state["db"] is None:
            state["db"] = Database(config.DB_PATH)
        if state["rec"] is None:
            state["rec"] = RecognizerClient()
        if state["llm"] is None:
            state["llm"] = build_provider()
        log.info("writing model: %s/%s (key %s)", state["llm"].name, state["llm"].model,
                 "found" if state["llm"].available() else "missing")
        log.info("data dir: %s", config.DATA_DIR)
        yield
        state["rec"].shutdown()
        state["db"].close()

    app = FastAPI(title="Pronunciation Coach", lifespan=lifespan)

    def _db() -> Database:
        return state["db"]

    def _sentence_payload(book: dict, idx: int) -> dict:
        idx = max(0, min(idx, max(book["sentence_count"] - 1, 0)))
        text = _db().get_sentence(book["id"], idx) or ""
        return {
            "book_id": book["id"], "title": book["title"], "idx": idx,
            "total": book["sentence_count"], "text": text,
            "segments": [asdict(s) for s in split_words(text)],
        }

    @app.get("/api/health")
    def health():
        llm = state["llm"]
        return {"ok": True, "espeak": espeak_available(), "model": config.MODEL_NAME,
                "writing": {"provider": llm.name, "model": llm.model, "available": llm.available()}
                if llm else None}

    @app.get("/api/books")
    def list_books():
        return {"books": _db().list_books(), "last_book_id": _db().last_book_id()}

    @app.post("/api/books")
    async def upload_book(file: UploadFile | None = File(None), text: str | None = Form(None),
                          title: str | None = Form(None)):
        if file is not None and file.filename:
            data = await file.read(MAX_UPLOAD_BYTES + 1)
            if len(data) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, "file too large")
            try:
                book_title, paragraphs = extract(file.filename, data)
            except UnsupportedFormat as exc:
                raise HTTPException(415, str(exc)) from exc
            except Exception as exc:
                log.exception("extraction failed")
                raise HTTPException(422, f"could not read {file.filename}: {exc}") from exc
            filename = file.filename
        elif text and text.strip():
            book_title, paragraphs, filename = "Pasted text", text, "pasted.txt"
        else:
            raise HTTPException(400, "send a file or some text")
        sentences = split_sentences(paragraphs)
        if not sentences:
            raise HTTPException(422, "no readable sentences found")
        book_id = _db().add_book(title or book_title, filename, sentences)
        return {"id": book_id, "title": title or book_title, "sentence_count": len(sentences)}

    @app.delete("/api/books/{book_id}")
    def delete_book(book_id: int):
        if not _db().delete_book(book_id):
            raise HTTPException(404, "book not found")
        return {"ok": True}

    @app.get("/api/books/{book_id}/sentence")
    def get_sentence(book_id: int, idx: int | None = None):
        book = _db().get_book(book_id)
        if not book:
            raise HTTPException(404, "book not found")
        payload = _sentence_payload(book, book["position"] if idx is None else idx)
        _db().set_position(book_id, payload["idx"])
        return payload

    @app.post("/api/books/{book_id}/position")
    def set_position(book_id: int, pos: Position):
        book = _db().get_book(book_id)
        if not book:
            raise HTTPException(404, "book not found")
        payload = _sentence_payload(book, pos.idx)
        _db().set_position(book_id, payload["idx"])
        return payload

    @app.get("/api/expected")
    def expected(text: str):
        try:
            words = expected_for_sentence(text)
        except EspeakUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        return {"words": [asdict(w) for w in words]}

    @app.post("/api/score")
    def score_attempt(audio: UploadFile = File(...), text: str = Form(...),
                      book_id: int | None = Form(None), sentence_idx: int | None = Form(None),
                      session_id: str | None = Form(None)):
        try:
            expected_words = expected_for_sentence(text)
        except EspeakUnavailable as exc:
            raise HTTPException(503, str(exc)) from exc
        try:
            samples = decode_to_16k_mono(audio.file.read())
        except AudioError as exc:
            raise HTTPException(400, str(exc)) from exc
        try:
            reply = state["rec"].recognize(samples)
        except RecognizerError as exc:
            raise HTTPException(503, f"recognizer unavailable: {exc}") from exc
        recognized, spans = _recognized_with_spans(reply)
        result = score(expected_words, recognized, spans, reply.get("audio_seconds"))
        data = result.to_dict()
        attempt_id = _db().add_attempt(
            book_id=book_id, sentence_idx=sentence_idx, sentence=text,
            accuracy=result.accuracy, session_id=session_id,
            expected=result.expected, recognized=result.recognized,
            words=[{k: w[k] for k in ("text", "score", "status", "expected", "heard")} for w in data["words"]],
            errors=data["errors"],
        )
        data.update(
            attempt_id=attempt_id, raw_recognized=reply["phonemes"],
            device=reply.get("device"), device_name=reply.get("device_name"),
            infer_seconds=reply.get("infer_seconds"),
            segments=[asdict(s) for s in split_words(text)],
        )
        return data

    @app.get("/api/tts")
    def tts(text: str, rate: float = 1.0):
        # Plain `def`: synthesis is blocking, so FastAPI runs it in its threadpool.
        try:
            speech = state["tts"].synthesize(text, rate)
        except TTSInputError as exc:
            raise HTTPException(400, str(exc)) from exc
        except TTSError as exc:
            raise HTTPException(503, str(exc)) from exc
        return Response(speech.audio, media_type=speech.media_type,
                        headers={"X-TTS-Engine": speech.engine, "Cache-Control": "private, max-age=86400"})

    @app.get("/api/tts/phoneme")
    def tts_phoneme(symbol: str):
        try:
            speech = state["tts"].synthesize_phoneme(symbol)
        except UnknownPhoneme as exc:
            raise HTTPException(404, f"unknown phoneme: {symbol}") from exc
        except TTSError as exc:
            raise HTTPException(503, str(exc)) from exc
        return Response(speech.audio, media_type=speech.media_type,
                        headers={"X-TTS-Engine": speech.engine, "X-TTS-Method": speech.method,
                                 "X-Phoneme-Source": speech.source,
                                 "Cache-Control": "private, max-age=86400"})

    @app.get("/api/phonemes")
    def phonemes():
        return guide_payload()

    @app.get("/api/stats")
    def stats():
        from .tips import tip_for

        data = _db().stats()
        for e in data["top_errors"]:
            e["tip"] = tip_for("substitution" if e["kind"] == "substitution" else e["kind"],
                               e["expected"] or "", e["actual"] or "", word_final=True)
        return data

    # ------------------------------------------------------------- writing
    @app.get("/api/writing/tasks")
    def writing_tasks():
        llm = state["llm"]
        return tasks_payload() | {"criteria": writing.CRITERIA,
                                  "llm": {"model": llm.model, "available": llm.available()}}

    @app.post("/api/writing/tasks/generate")
    def writing_generate(req: GenerateTaskRequest):
        avoid = [t["title"] for t in TASKS_BY_ID.values()] + [
            r["task_title"] for r in _db().list_writing(30) if r["task_title"]]
        try:
            return writing.generate_task(state["llm"], exam=req.exam, genre=req.genre,
                                         topic=(req.topic or "").strip() or None, avoid=avoid)
        except LLMError as exc:
            raise _llm_http_error(exc) from exc

    @app.post("/api/writing/correct")
    def writing_correct(req: CorrectRequest):
        # Plain `def`: the LLM call blocks, so FastAPI runs it in its threadpool.
        try:
            text = writing.validate_text(req.text)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        task = _clean_task(req.task)
        try:
            result = writing.correct(state["llm"], text, task)
        except LLMError as exc:
            raise _llm_http_error(exc) from exc
        seconds = max(0, min(req.seconds_spent, 6 * 3600)) if req.seconds_spent is not None else None
        sub_id = _db().add_writing(task=task, text=text, result=result, seconds_spent=seconds)
        return result | {"id": sub_id, "text": text, "task": task}

    @app.get("/api/writing/submissions")
    def writing_list():
        return {"submissions": _db().list_writing()}

    @app.get("/api/writing/submissions/{sub_id}")
    def writing_get(sub_id: int):
        sub = _db().get_writing(sub_id)
        if not sub:
            raise HTTPException(404, "submission not found")
        return sub["result"] | {"id": sub["id"], "text": sub["text"], "task": sub["task"],
                                "created_at": sub["created_at"], "seconds_spent": sub["seconds_spent"]}

    @app.delete("/api/writing/submissions/{sub_id}")
    def writing_delete(sub_id: int):
        if not _db().delete_writing(sub_id):
            raise HTTPException(404, "submission not found")
        return {"ok": True}

    @app.get("/api/writing/stats")
    def writing_stats():
        data = _db().writing_stats()
        for cat in data["categories"]:
            cat["label"] = grammar_lessons.CATEGORIES.get(cat["category"], cat["category"])
            cat["lesson_id"] = grammar_lessons.lesson_for(cat["category"], cat.pop("top_lesson", None))
        weights: dict[str, int] = {}
        for r in data["recent_categories"]:
            lid = grammar_lessons.lesson_for(r["category"], r["lesson_id"])
            if lid:
                weights[lid] = weights.get(lid, 0) + r["count"]
        data["suggested_lessons"] = [
            {"lesson_id": lid, "title": grammar_lessons.LESSONS_BY_ID[lid]["title"],
             "summary": grammar_lessons.LESSONS_BY_ID[lid]["summary"], "count": n}
            for lid, n in sorted(weights.items(), key=lambda kv: -kv[1])[:4]
        ]
        del data["recent_categories"]
        data["criteria"] = writing.CRITERIA
        return data

    @app.get("/api/writing/lessons")
    def writing_lessons():
        return {"lessons": grammar_lessons.public_lessons(), "categories": grammar_lessons.CATEGORIES}

    @app.post("/api/writing/lessons/{lesson_id}/check")
    def writing_check(lesson_id: str, body: LessonAnswers):
        try:
            return grammar_lessons.check_answers(lesson_id, [a or "" for a in body.answers])
        except KeyError as exc:
            raise HTTPException(404, "lesson not found") from exc

    @app.get("/api/worker")
    def worker_status():
        return asdict(state["rec"].info()) | {"idle_timeout": state["rec"].idle_timeout}

    @app.get("/")
    def index():
        return FileResponse(STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    uvicorn.run(app, host=config.HOST, port=config.PORT, log_level="info")


if __name__ == "__main__":
    main()
