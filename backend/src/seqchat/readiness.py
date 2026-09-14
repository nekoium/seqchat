from __future__ import annotations

from pathlib import Path
from typing import Literal

import duckdb

from seqchat.models import ComponentReadiness, ReadinessResponse
from seqchat.settings import Settings


def check_database_readiness(database_path: Path) -> ComponentReadiness:
    if not database_path.is_file():
        return ComponentReadiness(
            status="not_ready",
            code="database_not_ready",
            message="Initialize the SeqChat dataset before submitting a query.",
        )
    try:
        connection = duckdb.connect(str(database_path), read_only=True)
        try:
            row = connection.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE lower(table_name) = 'adsl'"
            ).fetchone()
        finally:
            connection.close()
    except Exception:
        return ComponentReadiness(
            status="not_ready",
            code="database_not_ready",
            message="The SeqChat database is not accessible.",
        )
    if row is None or row[0] < 1:
        return ComponentReadiness(
            status="not_ready",
            code="database_not_ready",
            message="Initialize the SeqChat dataset before submitting a query.",
        )
    return ComponentReadiness(
        status="ready", code="database_ready", message="The ADSL dataset is ready."
    )


def check_model_readiness(settings: Settings) -> ComponentReadiness:
    error = settings.provider_configuration_error
    if error == "model_not_configured":
        return ComponentReadiness(
            status="not_ready",
            code=error,
            message="Configure the SeqChat model provider before submitting a query.",
        )
    if error is not None:
        return ComponentReadiness(
            status="not_ready",
            code=error,
            message="Correct the SeqChat model provider configuration.",
        )
    return ComponentReadiness(
        status="ready",
        code="model_configured",
        message="Model settings are complete; live availability has not been tested.",
    )


def assess_readiness(settings: Settings) -> ReadinessResponse:
    components = {
        "backend": ComponentReadiness(
            status="ready", code="backend_reachable", message="The SeqChat API is reachable."
        ),
        "database": check_database_readiness(settings.database_path),
        "model": check_model_readiness(settings),
    }
    overall: Literal["ready", "not_ready"] = (
        "ready" if all(item.status == "ready" for item in components.values()) else "not_ready"
    )
    return ReadinessResponse(status=overall, components=components)
