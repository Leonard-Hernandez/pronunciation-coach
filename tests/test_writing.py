import json

import httpx
import pytest
from fastapi.testclient import TestClient

from pronunciation_coach import config, server
from pronunciation_coach import grammar_lessons as gl
from pronunciation_coach import writing
from pronunciation_coach.db import Database
from pronunciation_coach.llm import GroqProvider, LLMRateLimited, LLMReply, LLMUnavailable

SAMPLE = ("Is important to say that I have 25 years and I work in this company since 2020. "
          "People is very kind and they explained me everything.")


def correction_json(**over):
    data = {
        "errors": [
            {"original": "Is important", "occurrence": 1, "correction": "It is important",
             "category": "missing_subject", "lesson": "missing-subject-it",
             "explanation_es": "Falta el sujeto «it».", "example": "It is raining."},
            {"original": "I have 25 years", "occurrence": 1, "correction": "I am 25 years old",
             "category": "word_choice", "lesson": "age-with-be",
             "explanation_es": "La edad se dice con «be».", "example": "She is 30."},
            {"original": "people is", "occurrence": 1, "correction": "People are",  # wrong case on purpose
             "category": "subject_verb_agreement", "lesson": "none",
             "explanation_es": "«People» es plural.", "example": "People are nice."},
            {"original": "they explaned me everything", "occurrence": 1,  # typo on purpose -> fuzzy
             "correction": "they explained everything to me", "category": "pronoun", "lesson": "explain-to",
             "explanation_es": "«Explain something to someone».", "example": "Explain it to me."},
            {"original": "not in the text at all", "occurrence": 1, "correction": "x",
             "category": "articles", "lesson": "none", "explanation_es": "…", "example": ""},
            {"original": "kind", "occurrence": 1, "correction": "kind",  # no-op, dropped
             "category": "other", "lesson": "none", "explanation_es": "", "example": ""},
        ],
        "corrected_text": "It is important to say that I am 25 years old…",
        "upgraded_text": "I would like to point out that…",
        "scores": {"task_achievement": 60, "coherence_cohesion": 55, "grammar": 140, "vocabulary": -3},
        "cefr_estimate": "b1",
        "ielts_band_estimate": 5.3,
        "priorities": [{"category": "missing_subject", "lesson": "there-is-are", "title_es": "Sujeto", "detail_es": "Usa «it»."},
                       {"category": "not_a_category", "title_es": "Otro", "detail_es": "…"}],
        "summary_es": "Buen comienzo.",
    }
    data.update(over)
    return json.dumps(data, ensure_ascii=False)


TASK_JSON = json.dumps({
    "title": "Ask for feedback", "exam": "work", "genre": "email_semi", "register": "semi-formal",
    "prompt": "Write to your manager asking for feedback.", "points": ["why", "when"],
    "words_min": 120, "words_max": 900, "minutes": 3,
})


class FakeProvider:
    name = "fake"
    model = "fake-model"

    def __init__(self, replies=None, exc=None, available=True):
        self.replies = list(replies or [])
        self.exc = exc
        self.calls = []
        self._available = available

    def available(self):
        return self._available

    def complete_json(self, *, system, user, schema, schema_name, temperature=0.2, max_tokens=8000):
        self.calls.append({"system": system, "user": user, "schema_name": schema_name})
        if self.exc:
            raise self.exc
        return LLMReply(text=self.replies.pop(0), model=self.model, seconds=0.5)


class _NoRecognizer:
    def shutdown(self):
        pass


@pytest.fixture
def make_client():
    from contextlib import ExitStack

    with ExitStack() as stack:
        def make(provider):
            app = server.create_app(db=Database(":memory:"), recognizer=_NoRecognizer(), llm=provider)
            return stack.enter_context(TestClient(app))

        yield make


# ------------------------------------------------------------------ locating
def test_locate_exact_and_occurrence():
    text = "I go to the gym. I go to work."
    assert writing.locate(text, "I go", 1) == (0, 4, "exact")
    assert writing.locate(text, "I go", 2) == (17, 21, "exact")
    # Out-of-range occurrence falls back to the first free match.
    assert writing.locate(text, "I go", 7) == (0, 4, "exact")
    # Used spans are skipped.
    assert writing.locate(text, "I go", 1, used=[(0, 4)]) == (17, 21, "exact")


def test_locate_normalized_case_quotes_whitespace():
    text = "It’s  important.\nPeople is kind."
    a, b, m = writing.locate(text, "it's important", 1)
    assert m == "normalized" and text[a:b] == "It’s  important"
    a, b, m = writing.locate(text, "people is", 1)
    assert m == "normalized" and text[a:b] == "People is"


def test_locate_fuzzy_and_missing():
    a, b, m = writing.locate(SAMPLE, "they explaned me everything", 1)
    assert m == "fuzzy" and SAMPLE[a:b] == "they explained me everything"
    assert writing.locate(SAMPLE, "completely unrelated words here", 1) is None
    assert writing.locate(SAMPLE, "   ", 1) is None


# ---------------------------------------------------------------- validation
def test_correction_schema_validation_and_result():
    out = writing.CorrectionOut.model_validate(json.loads(correction_json()))
    assert out.scores.grammar == 100 and out.scores.vocabulary == 0  # clamped
    assert out.cefr_estimate == "B1" and out.ielts_band_estimate == 5.5
    r = writing.build_result(SAMPLE, out)
    assert [SAMPLE[e["start"]:e["end"]] for e in r["errors"]] == [
        "Is important", "I have 25 years", "People is", "they explained me everything"]
    # The highlight text is what is in the user's text, not what the model quoted.
    assert r["errors"][2]["original"] == "People is"
    assert [e["original"] for e in r["unlocated"]] == ["not in the text at all"]
    assert r["errors"][2]["lesson_id"] == "people-plural" or r["errors"][2]["lesson_id"] == "third-person-s"
    assert r["errors"][0]["lesson_id"] == "missing-subject-it"
    assert r["priorities"][1]["category"] == "other" and r["priorities"][1]["lesson_id"] is None
    assert r["priorities"][0]["lesson_id"] == "there-is-are"  # the model's pick wins over the default
    assert r["overall"] == round((60 + 55 + 100 + 0) / 4)
    assert sorted(e["id"] for e in r["errors"] + r["unlocated"]) == list(range(5))


def test_schema_is_strict_compatible():
    def walk(node):
        if isinstance(node, dict) and node.get("type") == "object":
            assert node["additionalProperties"] is False
            assert set(node["required"]) == set(node["properties"])
            for v in node["properties"].values():
                walk(v)
        elif isinstance(node, dict) and node.get("type") == "array":
            walk(node["items"])

    walk(writing.CORRECTION_SCHEMA)
    walk(writing.TASK_SCHEMA)
    assert set(writing.CORRECTION_SCHEMA["properties"]["errors"]["items"]["properties"]["category"]["enum"]) == set(gl.CATEGORIES)


def test_retry_once_on_invalid_json():
    p = FakeProvider(["not json {", correction_json()])
    r = writing.correct(p, SAMPLE, None)
    assert len(p.calls) == 2 and "not valid JSON" in p.calls[1]["user"]
    assert r["model"] == "fake-model" and r["word_count"] == writing.count_words(SAMPLE)


def test_invalid_twice_raises():
    p = FakeProvider(["{}", '{"errors": "nope"}'])
    with pytest.raises(writing.InvalidOutput):
        writing.correct(p, SAMPLE, None)
    assert len(p.calls) == 2


def test_prompt_contains_task_and_text():
    p = FakeProvider([correction_json()])
    from pronunciation_coach.writing_tasks import TASKS_BY_ID

    writing.correct(p, SAMPLE, TASKS_BY_ID["ielts-gt1-complaint"])
    user = p.calls[0]["user"]
    assert "Target length: 150-200 words" in user and f"<student_text>\n{SAMPLE}\n</student_text>" in user


def test_validate_text():
    with pytest.raises(ValueError):
        writing.validate_text("Too short.")
    with pytest.raises(ValueError):
        writing.validate_text("word " * 2000)
    assert writing.validate_text("  " + SAMPLE + "\r\n") == SAMPLE
    assert writing.count_words("It's a well-known fact, isn't it?") == 6


# ------------------------------------------------------------------- lessons
def test_lessons_are_consistent():
    assert len(gl.LESSONS) >= 20
    ids = [lesson["id"] for lesson in gl.LESSONS]
    assert len(ids) == len(set(ids))
    for lesson in gl.LESSONS:
        assert lesson["explanation"] and lesson["examples"] and len(lesson["exercise"]) >= 3
        assert all(c in gl.CATEGORIES for c in lesson["categories"])
        for i, item in enumerate(lesson["exercise"]):
            assert item["kind"] in ("fill", "fix") and item["answers"]
            if item["kind"] == "fill":
                assert item["prompt"].count("___") == 1
            for ans in item["answers"]:  # every accepted answer passes its own check
                res = gl.check_answers(lesson["id"], [""] * i + [ans])
                assert res["results"][i]["correct"], (lesson["id"], i, ans)
    for cat, lid in gl.CATEGORY_LESSON.items():
        assert cat in gl.CATEGORIES and (lid is None or lid in gl.LESSONS_BY_ID)


def test_check_answers_normalization():
    res = gl.check_answers("since-for", ["Since", " for. ", "I've studied English since I was a child",
                                         "She work here for three months."])
    assert [r["correct"] for r in res["results"]] == [True, True, True, False]
    assert res["score"] == 3 and res["total"] == 4
    assert gl.normalize_answer("It’s  raining!") == "it is raining"
    assert gl.normalize_answer("They don't") == gl.normalize_answer("they do not")
    # Empty answers are wrong, not crashes.
    assert gl.check_answers("articles", [])["score"] == 0
    with pytest.raises(KeyError):
        gl.check_answers("nope", [])


def test_public_lessons_hide_answers():
    for lesson in gl.public_lessons():
        for item in lesson["exercise"]:
            assert set(item) == {"kind", "prompt"}


# ----------------------------------------------------------------- endpoints
def test_correct_endpoint_history_and_stats(make_client):
    p = FakeProvider([correction_json(), correction_json()])
    c = make_client(p)
    r = c.post("/api/writing/correct", json={"text": SAMPLE, "task": {"id": "work-thank-colleague", "title": "x"},
                                             "seconds_spent": 120})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == 1 and body["task"]["title"] == "Thank a colleague who is leaving"  # server copy
    assert len(body["errors"]) == 4 and len(body["unlocated"]) == 1
    # Generated tasks are sanitized and kept.
    r2 = c.post("/api/writing/correct", json={"text": SAMPLE, "task": {"title": "Custom", "words": [100, 150],
                                                                       "exam": "bogus", "points": ["a"] * 20}})
    assert r2.json()["task"]["exam"] == "work" and len(r2.json()["task"]["points"]) == 6

    subs = c.get("/api/writing/submissions").json()["submissions"]
    assert [s["id"] for s in subs] == [2, 1] and subs[0]["error_count"] == 5
    one = c.get("/api/writing/submissions/1").json()
    assert one["text"] == SAMPLE and one["seconds_spent"] == 120 and one["scores"]["grammar"] == 100

    stats = c.get("/api/writing/stats").json()
    assert stats["overall"]["submissions"] == 2 and len(stats["timeline"]) == 2
    cats = {x["category"]: x for x in stats["categories"]}
    assert cats["missing_subject"]["count"] == 2 and cats["missing_subject"]["lesson_id"] == "missing-subject-it"
    assert cats["missing_subject"]["examples"][0]["correction"] == "It is important"
    # The category links to the lesson the model chose most often, not just the category default.
    assert cats["word_choice"]["lesson_id"] == "age-with-be" and "top_lesson" not in cats["word_choice"]
    suggested = [s["lesson_id"] for s in stats["suggested_lessons"]]
    assert "missing-subject-it" in suggested and len(suggested) <= 4

    assert c.delete("/api/writing/submissions/1").json() == {"ok": True}
    assert c.get("/api/writing/submissions/1").status_code == 404
    assert c.get("/api/writing/stats").json()["overall"]["submissions"] == 1


def test_correct_endpoint_errors(make_client):
    assert make_client(FakeProvider()).post("/api/writing/correct", json={"text": "hi"}).status_code == 422
    r = make_client(FakeProvider(exc=LLMRateLimited("Rate limit. Try again in about 8 s.", 7.2))).post(
        "/api/writing/correct", json={"text": SAMPLE})
    assert r.status_code == 429 and "Rate limit" in r.json()["detail"] and r.headers["retry-after"] == "8"
    r = make_client(FakeProvider(exc=LLMUnavailable("No Groq API key."))).post(
        "/api/writing/correct", json={"text": SAMPLE})
    assert r.status_code == 503
    c = make_client(FakeProvider(["bad", "bad"]))
    r = c.post("/api/writing/correct", json={"text": SAMPLE})
    assert r.status_code == 502 and "invalid" in r.json()["detail"]
    assert c.get("/api/writing/submissions").json()["submissions"] == []  # nothing stored


def test_generate_task_endpoint(make_client):
    p = FakeProvider([TASK_JSON])
    r = make_client(p).post("/api/writing/tasks/generate", json={"exam": "work", "topic": "feedback"})
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["generated"] and t["title"] == "Ask for feedback" and t["register"] == "semi-formal"
    assert t["words"] == [120, 450] and t["minutes"] == 10  # clamped
    assert "feedback" in p.calls[0]["user"] and "Apply for a job" in p.calls[0]["user"]  # avoid list


def test_tasks_and_lessons_endpoints(make_client):
    c = make_client(FakeProvider(available=False))
    data = c.get("/api/writing/tasks").json()
    assert len(data["tasks"]) >= 12 and data["llm"]["available"] is False
    assert {t["exam"] for t in data["tasks"]} >= {"ielts_gt_task1", "ielts_task2", "b2_first_essay", "work"}
    lessons = c.get("/api/writing/lessons").json()
    assert '"answers"' not in json.dumps(lessons["lessons"])
    r = c.post("/api/writing/lessons/make-do/check", json={"answers": ["make", "DO", "did", None]})
    assert [x["correct"] for x in r.json()["results"]] == [True, True, False, False]
    assert c.post("/api/writing/lessons/nope/check", json={"answers": []}).status_code == 404
    assert c.get("/api/health").json()["writing"]["available"] is False


# -------------------------------------------------------------- groq provider
def _groq_exc(cls, status, headers=None, message="boom"):
    req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    return cls(message, response=httpx.Response(status, request=req, headers=headers or {}), body=None)


class _FakeCompletions:
    def __init__(self, script):
        self.script = script
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step

        class Msg:
            content = step

        class Choice:
            message = Msg()

        class Resp:
            choices = [Choice()]

        return Resp()


def _provider(script):
    p = GroqProvider(model="big", fallback_model="small", api_key="test-key")
    comp = _FakeCompletions(script)
    p._client = type("C", (), {"chat": type("Chat", (), {"completions": comp})()})()
    return p, comp


def test_groq_structured_output_request():
    p, comp = _provider(['{"ok": 1}'])
    reply = p.complete_json(system="s", user="u", schema={"type": "object"}, schema_name="x")
    assert reply.text == '{"ok": 1}' and reply.model == "big"
    rf = comp.calls[0]["response_format"]
    assert rf["type"] == "json_schema" and rf["json_schema"]["strict"] is True


def test_groq_rate_limit_falls_back_then_reports():
    import groq

    p, comp = _provider([_groq_exc(groq.RateLimitError, 429), '{"ok": 1}'])
    assert p.complete_json(system="s", user="u", schema={}, schema_name="x").model == "small"
    assert [c["model"] for c in comp.calls] == ["big", "small"]

    p, _ = _provider([_groq_exc(groq.RateLimitError, 429), _groq_exc(groq.RateLimitError, 429, {"retry-after": "12"})])
    with pytest.raises(LLMRateLimited) as info:
        p.complete_json(system="s", user="u", schema={}, schema_name="x")
    assert info.value.retry_after == 12.0 and "13 s" in str(info.value)


def test_groq_json_schema_rejected_uses_json_mode():
    import groq

    p, comp = _provider([_groq_exc(groq.BadRequestError, 400, message="response_format json_schema not supported"),
                         '{"ok": 1}'])
    p.complete_json(system="s", user="u", schema={"type": "object"}, schema_name="x")
    assert comp.calls[1]["response_format"] == {"type": "json_object"} and comp.calls[1]["model"] == "big"


def test_groq_without_key(monkeypatch, tmp_path):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "missing")
    p = GroqProvider()
    assert p.available() is False
    with pytest.raises(LLMUnavailable):
        p.complete_json(system="s", user="u", schema={}, schema_name="x")


def test_env_file_and_secret(monkeypatch, tmp_path):
    f = tmp_path / "env"
    f.write_text("# comment\nexport GROQ_API_KEY='abc'\nOTHER = \"x y\"\nbroken line\n")
    assert config.read_env_file(f) == {"GROQ_API_KEY": "abc", "OTHER": "x y"}
    monkeypatch.setattr(config, "ENV_FILE", f)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert config.secret("GROQ_API_KEY") == "abc"
    monkeypatch.setenv("GROQ_API_KEY", "from-env")
    assert config.secret("GROQ_API_KEY") == "from-env"
