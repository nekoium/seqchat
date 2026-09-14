from __future__ import annotations

import json
import logging
from collections.abc import Callable

import httpx
import pytest

from seqchat.llm import HttpxChatCompletionsModel, ProviderError

API_KEY = "SENTINEL_SECRET_KEY"
RAW_BODY = "SENTINEL_RAW_PROVIDER_BODY"


def client_with(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def response(
    content: object, status: int = 200, request_id: str = "safe-request-123"
) -> httpx.Response:
    return httpx.Response(
        status,
        json={"choices": [{"message": {"content": content}}]},
        headers={"x-request-id": request_id},
    )


def model_for(
    handler: Callable[[httpx.Request], httpx.Response], **kwargs: object
) -> HttpxChatCompletionsModel:
    return HttpxChatCompletionsModel(
        base_url=" https://provider.example/prefix/v1/ ",
        api_key=f" {API_KEY} ",
        model=" test-model ",
        client=client_with(handler),
        **kwargs,
    )


def test_constructs_exact_chat_completions_url_and_bearer_auth() -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["authorization"] = request.headers["Authorization"]
        observed["payload"] = json.loads(request.content)
        return response('{"sql":"SELECT * FROM adsl","rationale":"test"}')

    generated = model_for(handler).generate_query(question="q", schema="s")
    assert generated.sql == "SELECT * FROM adsl"
    assert observed["url"] == "https://provider.example/prefix/v1/chat/completions"
    assert observed["authorization"] == f"Bearer {API_KEY}"
    assert observed["payload"]["model"] == "test-model"  # type: ignore[index]


@pytest.mark.parametrize(
    "url",
    [
        "https://provider.example/v1/chat/completions",
        "https://provider.example/chat/completions/v1",
        "not-a-url",
        "ftp://provider.example/v1",
    ],
)
def test_rejects_malformed_or_endpoint_including_base_urls(url: str) -> None:
    with pytest.raises(ProviderError) as caught:
        HttpxChatCompletionsModel(base_url=url, api_key="key", model="model")
    assert caught.value.code == "model_configuration_invalid"


@pytest.mark.parametrize("json_mode", [True, False])
def test_json_mode_capability_controls_response_format(json_mode: bool) -> None:
    payloads: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return response('{"sql":"SELECT 1 FROM adsl","rationale":"test"}')

    model_for(handler, json_mode=json_mode).generate_query(question="q", schema="s")
    assert ("response_format" in payloads[0]) is json_mode


@pytest.mark.parametrize(
    "content",
    [
        '{"sql":"SELECT 1 FROM adsl","rationale":"plain"}',
        '```json\n{"sql":"SELECT 1 FROM adsl","rationale":"fenced"}\n```',
        '```\n{"sql":"SELECT 1 FROM adsl","rationale":"fenced"}\n```',
    ],
)
def test_prompt_parse_fallback_accepts_plain_or_narrow_fenced_json(content: str) -> None:
    generated = model_for(lambda _request: response(content), json_mode=False).generate_query(
        question="q", schema="s"
    )
    assert generated.sql == "SELECT 1 FROM adsl"


@pytest.mark.parametrize("status", [401, 403])
def test_classifies_authentication_and_authorization(status: int) -> None:
    with pytest.raises(ProviderError) as caught:
        model_for(lambda _request: httpx.Response(status, text=RAW_BODY)).generate_query(
            question="q", schema="s"
        )
    assert caught.value.code == "provider_auth_error"
    assert caught.value.status_code == status


def test_classifies_rate_limit_and_other_http_failures() -> None:
    for status, code in [(429, "provider_overloaded"), (500, "provider_http_error")]:
        with pytest.raises(ProviderError) as caught:
            active = model_for(
                lambda _request, status=status: httpx.Response(status, text=RAW_BODY)
            )
            active.generate_query(question="q", schema="s")
        assert caught.value.code == code


@pytest.mark.parametrize(
    ("failure", "code"),
    [("timeout", "provider_timeout"), ("connection", "provider_connection_error")],
)
def test_classifies_timeout_and_connection_failure(failure: str, code: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "timeout":
            raise httpx.ReadTimeout("slow", request=request)
        raise httpx.ConnectError("offline", request=request)

    with pytest.raises(ProviderError) as caught:
        model_for(handler).generate_query(question="q", schema="s")
    assert caught.value.code == code


def test_classifies_non_json_response() -> None:
    with pytest.raises(ProviderError) as caught:
        model_for(lambda _request: httpx.Response(200, text=RAW_BODY)).generate_query(
            question="q", schema="s"
        )
    assert caught.value.code == "provider_malformed_response"


def test_classifies_missing_choices_as_incompatible() -> None:
    with pytest.raises(ProviderError) as caught:
        model_for(lambda _request: httpx.Response(200, json={"not_choices": []})).generate_query(
            question="q", schema="s"
        )
    assert caught.value.code == "provider_incompatible_response"


@pytest.mark.parametrize("content", [None, "", "   ", 42])
def test_classifies_missing_blank_or_non_string_content(content: object) -> None:
    with pytest.raises(ProviderError) as caught:
        model_for(lambda _request: response(content)).generate_query(question="q", schema="s")
    assert caught.value.code == "provider_missing_content"


@pytest.mark.parametrize(
    "content",
    [
        "not json",
        '{"sql":"SELECT 1 FROM adsl"}',
        '{"sql":"   ","rationale":"blank"}',
        '{"sql":"SELECT 1 FROM adsl","rationale":"ok","extra":true}',
        f"```json\n{{\"sql\":\"SELECT 1 FROM adsl\",\"rationale\":\"ok\"}}\n``` {RAW_BODY}",
    ],
)
def test_rejects_invalid_generated_query_json(content: str) -> None:
    with pytest.raises(ProviderError) as caught:
        model_for(lambda _request: response(content), json_mode=False).generate_query(
            question="q", schema="s"
        )
    assert caught.value.code == "model_parse_error"


def test_logs_classification_status_and_request_id_without_secrets_or_raw_body(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="seqchat.llm")
    with pytest.raises(ProviderError) as caught:
        model_for(
            lambda _request: httpx.Response(
                403, text=RAW_BODY, headers={"x-request-id": "safe-request-456"}
            )
        ).generate_query(question="q", schema="s")
    combined = caplog.text + str(caught.value)
    assert "category=authentication" in caplog.text
    assert "status_code=403" in caplog.text
    assert "safe-request-456" in caplog.text
    assert API_KEY not in combined
    assert RAW_BODY not in combined
    assert "Authorization" not in combined


def test_does_not_log_api_key_if_provider_echoes_it_as_request_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="seqchat.llm")
    with pytest.raises(ProviderError):
        model_for(
            lambda _request: httpx.Response(
                500, text=RAW_BODY, headers={"x-request-id": f"echo-{API_KEY}"}
            )
        ).generate_query(question="q", schema="s")
    assert API_KEY not in caplog.text
    assert "request_id=none" in caplog.text
