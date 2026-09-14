from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest

from seqchat.check import run_checks
from seqchat.llm import ProviderError
from seqchat.models import GeneratedQuery
from seqchat.settings import Settings


class SuccessfulModel:
    def generate_query(self, *, question: str, schema: str) -> GeneratedQuery:
        return GeneratedQuery(sql="SELECT COUNT(*) FROM adsl", rationale="diagnostic")

    def generate_answer(
        self,
        *,
        question: str,
        sql: str,
        columns: list[str],
        rows: list[list[object]],
    ) -> str:
        return "unused"


class FailingModel(SuccessfulModel):
    def __init__(self, error: ProviderError) -> None:
        self.error = error

    def generate_query(self, *, question: str, schema: str) -> GeneratedQuery:
        raise self.error


def complete_settings(database_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        database_path=database_path,
        llm_base_url="https://provider.example/v1",
        llm_api_key="SENTINEL_SECRET_KEY",
        llm_model="test-model",
    )


def test_check_passes_only_after_structured_provider_output(database_path: Path) -> None:
    output = StringIO()
    code = run_checks(
        complete_settings(database_path),
        output=output,
        model_factory=lambda _settings: SuccessfulModel(),
    )
    assert code == 0
    assert "[PASS] Settings" in output.getvalue()
    assert "[PASS] Database" in output.getvalue()
    assert "[PASS] Chat Completions endpoint" in output.getvalue()
    assert "[PASS] Provider returned the required structured SQL shape" in output.getvalue()
    assert "SENTINEL_SECRET_KEY" not in output.getvalue()


def test_check_fails_for_missing_settings(database_path: Path) -> None:
    output = StringIO()
    code = run_checks(Settings(_env_file=None, database_path=database_path), output=output)
    assert code != 0
    assert "[FAIL] Settings" in output.getvalue()


def test_check_fails_for_missing_database(tmp_path: Path) -> None:
    output = StringIO()
    code = run_checks(complete_settings(tmp_path / "missing.duckdb"), output=output)
    assert code != 0
    assert "[FAIL] Database" in output.getvalue()
    assert str(tmp_path) not in output.getvalue()


@pytest.mark.parametrize(
    "error",
    [
        ProviderError("provider_connection_error", "Cannot connect to the model provider"),
        ProviderError(
            "model_parse_error",
            "The model returned invalid structured SQL output",
            upstream_reached=True,
        ),
    ],
)
def test_check_fails_for_endpoint_or_structured_contract(
    database_path: Path, error: ProviderError
) -> None:
    output = StringIO()
    code = run_checks(
        complete_settings(database_path),
        output=output,
        model_factory=lambda _settings: FailingModel(error),
    )
    assert code != 0
    assert "[FAIL] Structured SQL output" in output.getvalue()
    assert "SENTINEL_SECRET_KEY" not in output.getvalue()
