from pathlib import Path
from typing import cast

import httpx
from fastapi.testclient import TestClient

from seqchat.api import create_app
from seqchat.llm import HttpxChatCompletionsModel
from seqchat.models import ErrorDetail, WorkflowState
from seqchat.settings import Settings
from seqchat.workflow import QueryWorkflow


class StubWorkflow:
    def __init__(self, result: WorkflowState) -> None:
        self.result = result

    def invoke(self, question: str) -> WorkflowState:
        return self.result


def client_for(result: WorkflowState, settings: Settings | None = None) -> TestClient:
    workflow = cast(QueryWorkflow, StubWorkflow(result))
    configured = settings or Settings(_env_file=None)
    return TestClient(create_app(settings=configured, workflow=workflow))


def test_health_contract() -> None:
    with client_for({}) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_ready_contract_with_complete_configuration_and_valid_database(
    database_path: Path,
) -> None:
    settings = Settings(
        _env_file=None,
        database_path=database_path,
        llm_base_url="https://provider.example/v1",
        llm_api_key="test-key",
        llm_model="any-model",
    )
    with client_for({}, settings) as client:
        response = client.get("/api/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["components"]["database"]["code"] == "database_ready"
    assert response.json()["components"]["model"]["code"] == "model_configured"
    assert "test-key" not in response.text
    assert str(database_path) not in response.text


def test_readiness_distinguishes_missing_model_configuration(database_path: Path) -> None:
    settings = Settings(_env_file=None, database_path=database_path)
    with client_for({}, settings) as client:
        payload = client.get("/api/ready").json()
    assert payload["status"] == "not_ready"
    assert payload["components"]["database"]["status"] == "ready"
    assert payload["components"]["model"]["code"] == "model_not_configured"


def test_readiness_distinguishes_missing_database(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        database_path=tmp_path / "missing.duckdb",
        llm_base_url="https://provider.example/v1",
        llm_api_key="test-key",
        llm_model="any-model",
    )
    with client_for({}, settings) as client:
        payload = client.get("/api/ready").json()
    assert payload["status"] == "not_ready"
    assert payload["components"]["database"]["code"] == "database_not_ready"
    assert payload["components"]["model"]["status"] == "ready"
    assert str(tmp_path) not in str(payload)


def test_rejects_empty_and_overlong_questions() -> None:
    with client_for({}) as client:
        empty = client.post("/api/query", json={"question": "   "})
        overlong = client.post("/api/query", json={"question": "x" * 2001})
    assert empty.status_code == 422
    assert empty.json()["error"]["code"] == "input_error"
    assert overlong.status_code == 422
    assert overlong.json()["error"]["code"] == "input_error"


def test_success_shape() -> None:
    result: WorkflowState = {
        "answer": "There are 254 subjects.",
        "validated_sql": "SELECT COUNT(*) AS subject_count FROM adsl LIMIT 100",
        "columns": ["subject_count"],
        "rows": [[254]],
        "row_count": 1,
        "warnings": [],
    }
    with client_for(result) as client:
        response = client.post("/api/query", json={"question": "Count subjects"})
    assert response.status_code == 200
    assert set(response.json()) == {
        "answer",
        "sql",
        "columns",
        "rows",
        "row_count",
        "warnings",
    }


def test_provider_failure_api_message_does_not_leak_secret_or_body(
    database_path: Path,
) -> None:
    secret = "SENTINEL_SECRET_KEY"
    raw_body = "SENTINEL_RAW_PROVIDER_BODY"
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(403, text=raw_body, headers={"x-request-id": "safe-id"})
    )
    model = HttpxChatCompletionsModel(
        base_url="https://provider.example/v1",
        api_key=secret,
        model="test-model",
        client=httpx.Client(transport=transport),
    )
    workflow = QueryWorkflow(database_path, model)
    with TestClient(create_app(settings=Settings(_env_file=None), workflow=workflow)) as client:
        response = client.post("/api/query", json={"question": "Count subjects"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_auth_error"
    assert secret not in response.text
    assert raw_body not in response.text


def test_controlled_error_shape_does_not_leak_details() -> None:
    result: WorkflowState = {
        "error": ErrorDetail(
            code="provider_error", message="The model failed", stage="generation"
        )
    }
    with client_for(result) as client:
        response = client.post("/api/query", json={"question": "Count subjects"})
    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "code": "provider_error",
            "message": "The model failed",
            "stage": "generation",
        }
    }
