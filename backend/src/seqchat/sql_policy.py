from __future__ import annotations

from dataclasses import dataclass

from sqlglot import exp, parse
from sqlglot.errors import ParseError

MAX_ROWS = 100
FORBIDDEN_NODE_KEYS = {
    "alter",
    "attach",
    "command",
    "copy",
    "create",
    "delete",
    "detach",
    "drop",
    "insert",
    "load_data",
    "merge",
    "pragma",
    "transaction",
    "update",
    "use",
}


class SQLPolicyError(ValueError):
    """Raised when generated SQL is not safe to execute."""


@dataclass(frozen=True)
class ValidatedSQL:
    sql: str
    limit_was_changed: bool


def validate_sql(sql: str) -> ValidatedSQL:
    try:
        statements = [statement for statement in parse(sql, read="duckdb") if statement is not None]
    except ParseError as error:
        raise SQLPolicyError("SQL could not be parsed") from error

    if len(statements) != 1:
        raise SQLPolicyError("Exactly one SQL statement is required")
    statement = statements[0]
    if not isinstance(statement, exp.Query):
        raise SQLPolicyError("Only read-only SELECT queries are allowed")

    if any(node.key in FORBIDDEN_NODE_KEYS for node in statement.walk()):
        raise SQLPolicyError("The query contains a prohibited operation")

    cte_names = {cte.alias_or_name.lower() for cte in statement.find_all(exp.CTE)}
    for table in statement.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise SQLPolicyError("External table functions are not allowed")
        table_name = table.name.lower()
        if table_name not in {"adsl", *cte_names}:
            raise SQLPolicyError(f"Table '{table.name}' is not allowed")
        if table.catalog or table.db:
            raise SQLPolicyError("Qualified table references are not allowed")

    changed = False
    limit = statement.args.get("limit")
    if limit is None:
        statement.limit(MAX_ROWS, copy=False)
        changed = True
    else:
        value = limit.expression
        if not isinstance(value, exp.Literal) or not value.is_int:
            raise SQLPolicyError("LIMIT must be a fixed integer")
        if int(value.this) > MAX_ROWS:
            statement.limit(MAX_ROWS, copy=False)
            changed = True

    return ValidatedSQL(sql=statement.sql(dialect="duckdb"), limit_was_changed=changed)
