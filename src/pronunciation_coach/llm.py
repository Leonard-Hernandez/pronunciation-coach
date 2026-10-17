"""LLM providers behind a small interface, so the writing feature does not depend on Groq.

A provider takes a system prompt, a user prompt and a JSON schema, and returns the raw
JSON text. Parsing and validation live in writing.py. To add another provider (e.g.
Claude), implement `LLMProvider` and register it in `build_provider`.

The API key is read lazily from the environment or config.ENV_FILE and never logged.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Protocol

from . import config

log = logging.getLogger("pronunciation_coach.llm")


class LLMError(Exception):
    """The provider failed; the message is safe to show in the UI."""


class LLMUnavailable(LLMError):
    """No provider is configured (e.g. missing API key)."""


class LLMRateLimited(LLMError):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


@dataclass
class LLMReply:
    text: str
    model: str
    seconds: float


class LLMProvider(Protocol):
    name: str
    model: str

    def available(self) -> bool: ...

    def complete_json(self, *, system: str, user: str, schema: dict, schema_name: str,
                      temperature: float = 0.2, max_tokens: int = 8000) -> LLMReply: ...


def _retry_after(exc) -> float | None:
    try:
        value = exc.response.headers.get("retry-after")
        return float(value) if value else None
    except Exception:
        return None


class GroqProvider:
    """Groq's OpenAI-compatible chat API with structured (JSON schema) output.

    Falls back to `fallback_model` when the main model is rate-limited, over capacity or
    gone, and to plain JSON mode if a model rejects `json_schema`.
    """

    name = "groq"

    def __init__(self, model: str | None = None, fallback_model: str | None = None,
                 api_key: str | None = None, timeout: float | None = None,
                 reasoning_effort: str | None = None) -> None:
        self.model = model or config.WRITING_MODEL
        self.fallback_model = fallback_model if fallback_model is not None else config.WRITING_FALLBACK_MODEL
        self._api_key = api_key
        self.timeout = timeout or config.WRITING_TIMEOUT
        self.reasoning_effort = reasoning_effort or config.WRITING_REASONING_EFFORT
        self._client = None

    def _key(self) -> str | None:
        return self._api_key or config.secret("GROQ_API_KEY")

    def available(self) -> bool:
        return bool(self._key())

    def _get_client(self):
        if self._client is None:
            key = self._key()
            if not key:
                raise LLMUnavailable(
                    f"No Groq API key. Add GROQ_API_KEY=... to {config.ENV_FILE} (chmod 600) "
                    "and restart the server.")
            from groq import Groq  # imported lazily: keeps startup fast and tests offline

            self._client = Groq(api_key=key, timeout=self.timeout, max_retries=1)
        return self._client

    def _request(self, model: str, system: str, user: str, schema: dict, schema_name: str,
                 temperature: float, max_tokens: int, structured: bool):
        kwargs: dict = {
            "model": model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
        }
        if structured:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": True},
            }
        else:
            kwargs["response_format"] = {"type": "json_object"}
        if model.startswith("openai/gpt-oss"):
            kwargs["reasoning_effort"] = self.reasoning_effort
            kwargs["include_reasoning"] = False
        return self._get_client().chat.completions.create(**kwargs)

    def complete_json(self, *, system: str, user: str, schema: dict, schema_name: str,
                      temperature: float = 0.2, max_tokens: int = 8000) -> LLMReply:
        import groq

        models = [self.model] + ([self.fallback_model] if self.fallback_model and self.fallback_model != self.model else [])
        last_exc: Exception | None = None
        for i, model in enumerate(models):
            structured = True
            for _ in range(2):  # second pass only when json_schema is rejected
                t0 = time.monotonic()
                try:
                    resp = self._request(model, system, user, schema, schema_name,
                                         temperature, max_tokens, structured)
                except groq.RateLimitError as exc:
                    last_exc = exc
                    log.warning("groq rate limit on %s", model)
                    break  # try the fallback model, which has its own limits
                except (groq.NotFoundError, groq.InternalServerError) as exc:
                    last_exc = exc
                    log.warning("groq %s failed (%s), trying fallback", model, type(exc).__name__)
                    break
                except groq.BadRequestError as exc:
                    msg = str(exc).lower()
                    if structured and ("json_schema" in msg or "response_format" in msg):
                        log.warning("%s rejected json_schema, retrying in JSON mode", model)
                        structured = False
                        user = f"{user}\n\nReturn ONLY a JSON object that matches this JSON schema:\n{schema}"
                        continue
                    if "json_validate_failed" in msg or "failed to generate json" in msg:
                        raise LLMError("The model returned invalid JSON.") from exc
                    raise LLMError(f"The writing model rejected the request: {exc.message}") from exc
                except groq.AuthenticationError as exc:
                    raise LLMUnavailable("Groq rejected the API key (401). Check GROQ_API_KEY.") from exc
                except groq.APITimeoutError as exc:
                    raise LLMError("The writing model took too long to answer. Try again.") from exc
                except groq.APIConnectionError as exc:
                    raise LLMError("Could not reach Groq. Check your internet connection.") from exc
                except groq.APIStatusError as exc:
                    raise LLMError(f"Groq error {exc.status_code}.") from exc
                seconds = time.monotonic() - t0
                text = resp.choices[0].message.content or ""
                if i:
                    log.info("used fallback model %s", model)
                log.info("groq %s answered in %.1f s", model, seconds)
                return LLMReply(text=text, model=model, seconds=seconds)
        if isinstance(last_exc, groq.RateLimitError):
            retry = _retry_after(last_exc)
            wait = f" Try again in about {int(retry) + 1} s." if retry else " Wait a minute and try again."
            raise LLMRateLimited("Groq's free-tier rate limit was reached." + wait, retry) from last_exc
        raise LLMError("The writing model is unavailable right now. Try again later.") from last_exc


def build_provider() -> LLMProvider:
    if config.WRITING_PROVIDER == "groq":
        return GroqProvider()
    raise ValueError(f"unknown PC_WRITING_PROVIDER: {config.WRITING_PROVIDER}")
