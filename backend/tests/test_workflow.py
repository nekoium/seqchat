from pathlib import Path

from seqchat.llm import ProviderError
from seqchat.models import GeneratedQuery
from seqchat.workflow import QueryWorkflow


class DeterministicFakeModel:
    def __init__(self, sql: str = "SELECT COUNT(*) AS subject_count FROM adsl") -> None:
        self.sql = sql
        self.calls: list[str] = []

    def generate_query(self, *, question: str, schema: str) -> GeneratedQuery:
        self.calls.append("generation")
        assert "adsl table" in schema
        return GeneratedQuery(sql=self.sql, rationale="Deterministic test query")

    def generate_answer(
        self,
        *,
        question: str,
        sql: str,
        columns: list[str],
        rows: list[list[object]],
    ) -> str:
        self.calls.append("answer")
        assert columns == ["subject_count"]
        assert rows == [[254]]
        return "There are 254 subjects."


class FailingFakeModel(DeterministicFakeModel):
    def generate_query(self, *, question: str, schema: str) -> GeneratedQuery:
        raise ProviderError("secret raw provider response")


def test_fixed_graph_runs_all_stages(database_path: Path) -> None:
    model = DeterministicFakeModel()
    result = QueryWorkflow(database_path, model).invoke("How many subjects are there?")
    assert result["current_stage"] == "answer"
    assert result["answer"] == "There are 254 subjects."
    assert result["rows"] == [[254]]
    assert model.calls == ["generation", "answer"]


def test_validation_failure_stops_before_execution_and_answer(database_path: Path) -> None:
    model = DeterministicFakeModel("DROP TABLE adsl")
    result = QueryWorkflow(database_path, model).invoke("Drop the table")
    assert result["error"].code == "unsafe_sql"
    assert result["error"].stage == "validation"
    assert model.calls == ["generation"]


def test_provider_failure_is_controlled_and_safe(database_path: Path) -> None:
    result = QueryWorkflow(database_path, FailingFakeModel()).invoke("Count subjects")
    assert result["error"].code == "provider_error"
    assert "secret" not in result["error"].message


def test_missing_database_stops_at_schema(tmp_path: Path) -> None:
    model = DeterministicFakeModel()
    result = QueryWorkflow(tmp_path / "missing.duckdb", model).invoke("Count subjects")
    assert result["error"].stage == "schema"
    assert model.calls == []
