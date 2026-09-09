from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from seqchat.llm import ChatModel, HttpxChatCompletionsModel, ProviderError
from seqchat.models import ErrorDetail, ErrorResponse, GeneratedQuery, QueryRequest, QuerySuccess
from seqchat.settings import Settings
from seqchat.workflow import QueryWorkflow


class UnconfiguredModel:
    def generate_query(self, *, question: str, schema: str) -> GeneratedQuery:
        raise ProviderError("The model provider is not configured")

    def generate_answer(
        self,
        *,
        question: str,
        sql: str,
        columns: list[str],
        rows: list[list[object]],
    ) -> str:
        raise ProviderError("The model provider is not configured")


def create_app(
    *, settings: Settings | None = None, workflow: QueryWorkflow | None = None
) -> FastAPI:
    configured = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if workflow is not None:
            app.state.workflow = workflow
        else:
            model: ChatModel
            if configured.provider_is_configured:
                model = HttpxChatCompletionsModel(
                    base_url=configured.llm_base_url,
                    api_key=configured.llm_api_key,
                    model=configured.llm_model,
                )
            else:
                model = UnconfiguredModel()
            app.state.workflow = QueryWorkflow(configured.database_path, model)
        yield

    app = FastAPI(title="SeqChat API", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[configured.frontend_origin],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _error: RequestValidationError) -> JSONResponse:
        detail = ErrorDetail(
            code="input_error", message="Question must contain 1 to 2000 characters", stage="input"
        )
        return JSONResponse(status_code=422, content=ErrorResponse(error=detail).model_dump())

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "healthy"}

    @app.post(
        "/api/query",
        response_model=QuerySuccess,
        responses={
            422: {"model": ErrorResponse},
            502: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    def query(payload: QueryRequest, request: Request) -> QuerySuccess | JSONResponse:
        question = payload.question.strip()
        if not question:
            detail = ErrorDetail(
                code="input_error", message="Question must not be blank", stage="input"
            )
            return JSONResponse(status_code=422, content=ErrorResponse(error=detail).model_dump())

        active_workflow: QueryWorkflow = request.app.state.workflow
        result = active_workflow.invoke(question)
        error = result.get("error")
        if error is not None:
            status = 422 if error.code == "unsafe_sql" else 503
            if error.code in {
                "provider_error",
                "model_parse_error",
                "generation_error",
                "answer_error",
            }:
                status = 502
            return JSONResponse(
                status_code=status, content=ErrorResponse(error=error).model_dump()
            )
        return QuerySuccess(
            answer=result["answer"],
            sql=result["validated_sql"],
            columns=result["columns"],
            rows=result["rows"],
            row_count=result["row_count"],
            warnings=result.get("warnings", []),
        )

    return app


app = create_app()
