from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Protocol

import httpx
from pydantic import ValidationError

from seqchat.models import GeneratedQuery
from seqchat.settings import (
    ProviderConfigurationError,
    normalize_chat_completions_base_url,
)

logger = logging.getLogger(__name__)
_JSON_FENCE = re.compile(
    r"\A\s*```(?:json)?\s*\n(?P<body>.*?)\n```\s*\Z", re.DOTALL | re.IGNORECASE
)
_SAFE_REQUEST_ID_HEADERS = ("x-request-id", "request-id", "x-amzn-requestid", "cf-ray")


class ProviderError(RuntimeError):
    """A classified provider failure with a browser-safe message."""

    def __init__(
        self,
        code: str,
        safe_message: str,
        *,
        status_code: int | None = None,
        upstream_reached: bool = False,
    ) -> None:
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.status_code = status_code
        self.upstream_reached = upstream_reached


class ModelResponseError(ProviderError):
    """The provider responded, but SQL-generation output was invalid."""


@dataclass(frozen=True)
class Completion:
    content: str
    status_code: int
    request_id: str | None


class ChatModel(Protocol):
    def generate_query(self, *, question: str, schema: str) -> GeneratedQuery: ...

    def generate_answer(
        self,
        *,
        question: str,
        sql: str,
        columns: list[str],
        rows: list[list[object]],
    ) -> str: ...


def _safe_request_id(response: httpx.Response, *, forbidden: tuple[str, ...]) -> str | None:
    for name in _SAFE_REQUEST_ID_HEADERS:
        value = response.headers.get(name)
        if value:
            sanitized = "".join(
                character for character in value[:128] if character.isprintable()
            )
            if sanitized and not any(secret and secret in sanitized for secret in forbidden):
                return sanitized
    return None


def _log_failure(
    category: str, *, status_code: int | None = None, request_id: str | None = None
) -> None:
    logger.warning(
        "provider_failure category=%s status_code=%s request_id=%s",
        category,
        status_code if status_code is not None else "none",
        request_id or "none",
    )


def _structured_json_text(content: str) -> str:
    match = _JSON_FENCE.fullmatch(content)
    return match.group("body") if match else content


class HttpxChatCompletionsModel:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        json_mode: bool = False,
        timeout: float = 60,
        client: httpx.Client | None = None,
    ) -> None:
        api_key = api_key.strip()
        model = model.strip()
        if not base_url.strip() or not api_key or not model:
            raise ProviderError(
                "model_not_configured", "The model provider is not configured"
            )
        try:
            normalized = normalize_chat_completions_base_url(base_url)
        except ProviderConfigurationError as error:
            raise ProviderError(
                "model_configuration_invalid", "The model provider configuration is invalid"
            ) from error
        self._url = f"{normalized}/chat/completions"
        self._api_key = api_key
        self._model = model
        self._json_mode = json_mode
        self._timeout = timeout
        self._client = client or httpx.Client()

    @property
    def endpoint(self) -> str:
        """The normalized endpoint, intended for tests and diagnostics without query data."""
        return self._url

    def _complete(self, *, system: str, user: str, json_mode: bool = False) -> Completion:
        payload: dict[str, object] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        try:
            response = self._client.post(
                self._url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
                timeout=self._timeout,
            )
        except httpx.TimeoutException as error:
            _log_failure("timeout")
            raise ProviderError(
                "provider_timeout", "The model provider timed out"
            ) from error
        except httpx.ConnectError as error:
            _log_failure("connection")
            raise ProviderError(
                "provider_connection_error", "Cannot connect to the model provider"
            ) from error
        except httpx.HTTPError as error:
            _log_failure("connection")
            raise ProviderError(
                "provider_connection_error", "Cannot connect to the model provider"
            ) from error

        request_id = _safe_request_id(response, forbidden=(self._api_key,))
        if not response.is_success:
            status = response.status_code
            if status in {401, 403}:
                code = "provider_auth_error"
                message = "The model provider rejected authentication or authorization"
                category = "authentication"
            elif status == 429:
                code = "provider_overloaded"
                message = "The model provider is rate limited or overloaded"
                category = "overload"
            else:
                code = "provider_http_error"
                message = "The model provider returned an HTTP error"
                category = "http"
            _log_failure(category, status_code=status, request_id=request_id)
            raise ProviderError(
                code,
                message,
                status_code=status,
                upstream_reached=True,
            )

        try:
            body = response.json()
        except (json.JSONDecodeError, ValueError) as error:
            _log_failure(
                "malformed_response",
                status_code=response.status_code,
                request_id=request_id,
            )
            raise ProviderError(
                "provider_malformed_response",
                "The model provider returned a non-JSON response",
                status_code=response.status_code,
                upstream_reached=True,
            ) from error

        try:
            choices = body["choices"]
            message = choices[0]["message"]
        except (KeyError, IndexError, TypeError) as error:
            _log_failure(
                "incompatible_response",
                status_code=response.status_code,
                request_id=request_id,
            )
            raise ProviderError(
                "provider_incompatible_response",
                "The model provider returned an incompatible Chat Completions response",
                status_code=response.status_code,
                upstream_reached=True,
            ) from error
        try:
            content = message["content"]
        except (KeyError, TypeError) as error:
            _log_failure("missing_content", status_code=response.status_code, request_id=request_id)
            raise ProviderError(
                "provider_missing_content",
                "The model provider response did not contain message content",
                status_code=response.status_code,
                upstream_reached=True,
            ) from error
        if not isinstance(content, str) or not content.strip():
            _log_failure("missing_content", status_code=response.status_code, request_id=request_id)
            raise ProviderError(
                "provider_missing_content",
                "The model provider response did not contain nonblank text content",
                status_code=response.status_code,
                upstream_reached=True,
            )
        return Completion(
            content=content,
            status_code=response.status_code,
            request_id=request_id,
        )

    def generate_query(self, *, question: str, schema: str) -> GeneratedQuery:
        completion = self._complete(
            system=(
                "You generate one DuckDB read-only SQL query for the physical table adsl. "
                "Use only columns present in the supplied schema. Do not invent columns, use "
                "external table functions, or emit multiple statements. Return only a JSON object "
                'with exactly the keys "sql" and "rationale"; do not add prose or other keys.'
            ),
            user=f"Actual database schema:\n{schema}\n\nQuestion:\n{question}",
            json_mode=self._json_mode,
        )
        try:
            raw = json.loads(_structured_json_text(completion.content))
            return GeneratedQuery.model_validate(raw)
        except (json.JSONDecodeError, ValidationError, ValueError) as error:
            _log_failure(
                "invalid_structured_sql",
                status_code=completion.status_code,
                request_id=completion.request_id,
            )
            raise ModelResponseError(
                "model_parse_error",
                "The model returned invalid structured SQL output",
                upstream_reached=True,
            ) from error

    def generate_answer(
        self,
        *,
        question: str,
        sql: str,
        columns: list[str],
        rows: list[list[object]],
    ) -> str:
        evidence = json.dumps({"columns": columns, "rows": rows}, default=str)
        completion = self._complete(
            system=(
                "Answer using only the supplied SQL result. State no unsupported facts. "
                "If the result is empty or insufficient, say so plainly. Keep the answer concise."
            ),
            user=f"Question: {question}\nValidated SQL: {sql}\nBounded result: {evidence}",
        )
        return completion.content
