from typing import cast

from fastapi.testclient import TestClient

from seqchat.api import create_app
from seqchat.models import ErrorDetail, WorkflowState
from seqchat.settings import Settings
from seqchat.workflow import QueryWorkflow


class StubWorkflow:
    def __init__(self, result: WorkflowState) -> None:
        self.result = result

    def invoke(self, question: str) -> WorkflowState:
        return self.result


def client_for(result: WorkflowState) -> TestClient:
    workflow = cast(QueryWorkflow, StubWorkflow(result))
    return TestClient(create_app(settings=Settings(), workflow=workflow))


def test_health_contract() -> None:
    with client_for({}) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


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
