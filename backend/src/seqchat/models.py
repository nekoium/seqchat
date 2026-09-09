from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

Stage = Literal["input", "schema", "generation", "validation", "execution", "answer"]


class GeneratedQuery(BaseModel):
    sql: str = Field(min_length=1)
    rationale: str = ""


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2_000)


class QuerySuccess(BaseModel):
    answer: str
    sql: str
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    warnings: list[str]


class ErrorDetail(BaseModel):
    code: str
    message: str
    stage: Stage


class ErrorResponse(BaseModel):
    error: ErrorDetail


class WorkflowState(TypedDict, total=False):
    question: str
    schema: str
    generated_sql: str
    validated_sql: str
    columns: list[str]
    rows: list[list[Any]]
    row_count: int
    answer: str
    current_stage: Stage
    warnings: list[str]
    error: ErrorDetail
