from __future__ import annotations

import json
from typing import Protocol

import httpx

from seqchat.models import GeneratedQuery


class ProviderError(RuntimeError):
    """A safe provider failure without response details or credentials."""


class ModelResponseError(ProviderError):
    """The provider responded, but its structured output was invalid."""


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


class HttpxChatCompletionsModel:
    def __init__(self, *, base_url: str, api_key: str, model: str, timeout: float = 60) -> None:
        if not base_url or not api_key or not model:
            raise ProviderError("The model provider is not configured")
        self._url = f"{base_url.rstrip('/')}/chat/completions"
        self._api_key = api_key
        self._model = model
        self._timeout = timeout

    def _complete(self, *, system: str, user: str, json_mode: bool = False) -> str:
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
            response = httpx.post(
                self._url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise ValueError("Missing model content")
            return content
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
            raise ProviderError("The model provider could not complete the request") from error

    def generate_query(self, *, question: str, schema: str) -> GeneratedQuery:
        content = self._complete(
            system=(
                "You generate one DuckDB read-only SQL query for the physical table adsl. "
                "Use only columns present in the supplied schema. Do not invent columns, use "
                "external table functions, or emit multiple statements. Return a JSON object "
                'with exactly the keys "sql" and "rationale".'
            ),
            user=f"Actual database schema:\n{schema}\n\nQuestion:\n{question}",
            json_mode=True,
        )
        try:
            return GeneratedQuery.model_validate(json.loads(content))
        except (json.JSONDecodeError, ValueError) as error:
            raise ModelResponseError(
                "The model returned an invalid structured SQL response"
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
        return self._complete(
            system=(
                "Answer using only the supplied SQL result. State no unsupported facts. "
                "If the result is empty or insufficient, say so plainly. Keep the answer concise."
            ),
            user=f"Question: {question}\nValidated SQL: {sql}\nBounded result: {evidence}",
        )
