from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, cast

import duckdb
from langgraph.graph import END, START, StateGraph

from seqchat.llm import ChatModel, ModelResponseError, ProviderError
from seqchat.models import ErrorDetail, Stage, WorkflowState
from seqchat.sql_policy import SQLPolicyError, validate_sql

COLUMN_DESCRIPTIONS = {
    "USUBJID": "Unique subject identifier",
    "TRT01P": "Planned treatment for period 1",
    "TRT01A": "Actual treatment for period 1",
    "SEX": "Sex",
    "AGE": "Age",
    "RACE": "Race",
    "SAFFL": "Safety population flag",
}


def _error(stage: Stage, code: str, message: str) -> WorkflowState:
    return {"current_stage": stage, "error": ErrorDetail(code=code, message=message, stage=stage)}


class QueryWorkflow:
    def __init__(self, database_path: Path, model: ChatModel) -> None:
        self.database_path = database_path
        self.model = model
        self._graph = self._build_graph()

    def _schema(self, state: WorkflowState) -> WorkflowState:
        stage: Stage = "schema"
        try:
            connection = duckdb.connect(str(self.database_path), read_only=True)
            try:
                columns = connection.execute("PRAGMA table_info('adsl')").fetchall()
            finally:
                connection.close()
            if not columns:
                raise RuntimeError("ADSL table is missing")
            lines = ["adsl table:"]
            for column in columns:
                name, data_type = str(column[1]), str(column[2])
                description = COLUMN_DESCRIPTIONS.get(name, "ADSL analysis column")
                lines.append(f'- "{name}" {data_type} — {description}')
            return {"current_stage": stage, "schema": "\n".join(lines)}
        except Exception:
            return _error(stage, "database_unavailable", "The dataset is not available")

    def _generation(self, state: WorkflowState) -> WorkflowState:
        stage: Stage = "generation"
        try:
            generated = self.model.generate_query(
                question=state["question"], schema=state["schema"]
            )
            return {"current_stage": stage, "generated_sql": generated.sql}
        except ModelResponseError:
            return _error(stage, "model_parse_error", "The model returned invalid query data")
        except ProviderError:
            return _error(stage, "provider_error", "The model could not generate a query")
        except Exception:
            return _error(stage, "generation_error", "Query generation failed")

    def _validation(self, state: WorkflowState) -> WorkflowState:
        stage: Stage = "validation"
        try:
            validated = validate_sql(state["generated_sql"])
            warnings = list(state.get("warnings", []))
            if validated.limit_was_changed:
                warnings.append("The query result was limited to 100 rows.")
            return {
                "current_stage": stage,
                "validated_sql": validated.sql,
                "warnings": warnings,
            }
        except SQLPolicyError:
            return _error(stage, "unsafe_sql", "The generated query did not pass the SQL policy")

    def _execution(self, state: WorkflowState) -> WorkflowState:
        stage: Stage = "execution"
        try:
            connection = duckdb.connect(str(self.database_path), read_only=True)
            try:
                cursor = connection.execute(state["validated_sql"])
                columns = [item[0] for item in cursor.description]
                rows = [list(row) for row in cursor.fetchall()]
            finally:
                connection.close()
            return {
                "current_stage": stage,
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
            }
        except Exception:
            return _error(stage, "database_error", "The validated query could not be executed")

    def _answer(self, state: WorkflowState) -> WorkflowState:
        stage: Stage = "answer"
        try:
            answer = self.model.generate_answer(
                question=state["question"],
                sql=state["validated_sql"],
                columns=state["columns"],
                rows=cast(list[list[object]], state["rows"]),
            )
            return {"current_stage": stage, "answer": answer}
        except ProviderError:
            return _error(stage, "provider_error", "The model could not explain the result")
        except Exception:
            return _error(stage, "answer_error", "Answer generation failed")

    @staticmethod
    def _route(state: WorkflowState) -> Literal["next", "end"]:
        return "end" if "error" in state else "next"

    def _build_graph(self) -> Any:
        graph = StateGraph(WorkflowState)
        graph.add_node("schema", self._schema)
        graph.add_node("generation", self._generation)
        graph.add_node("validation", self._validation)
        graph.add_node("execution", self._execution)
        graph.add_node("answer", self._answer)
        graph.add_edge(START, "schema")
        graph.add_conditional_edges(
            "schema", self._route, {"next": "generation", "end": END}
        )
        graph.add_conditional_edges(
            "generation", self._route, {"next": "validation", "end": END}
        )
        graph.add_conditional_edges(
            "validation", self._route, {"next": "execution", "end": END}
        )
        graph.add_conditional_edges(
            "execution", self._route, {"next": "answer", "end": END}
        )
        graph.add_edge("answer", END)
        return graph.compile()

    def invoke(self, question: str) -> WorkflowState:
        initial: WorkflowState = {"question": question, "warnings": []}
        return cast(WorkflowState, self._graph.invoke(initial))
