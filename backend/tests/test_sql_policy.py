import pytest

from seqchat.sql_policy import MAX_ROWS, SQLPolicyError, validate_sql


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT COUNT(*) FROM adsl",
        "WITH grouped AS (SELECT SEX, COUNT(*) n FROM adsl GROUP BY SEX) SELECT * FROM grouped",
        "SELECT * FROM (SELECT USUBJID FROM adsl) subjects",
        "/* harmless */ SELECT -- still safe\n COUNT(*) FROM adsl",
    ],
)
def test_accepts_read_only_queries(sql: str) -> None:
    validated = validate_sql(sql)
    assert "SELECT" in validated.sql
    assert f"LIMIT {MAX_ROWS}" in validated.sql


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE adsl",
        "CREATE TABLE x(i INT)",
        "ALTER TABLE adsl ADD COLUMN x INT",
        "INSERT INTO adsl VALUES (1)",
        "UPDATE adsl SET SEX = 'X'",
        "DELETE FROM adsl",
        "COPY adsl TO 'out.csv'",
        "ATTACH 'other.db' AS other",
        "PRAGMA version",
        "SELECT * FROM adsl; DROP TABLE adsl",
        "SELECT * FROM another_table",
        "SELECT * FROM read_csv('secret.csv')",
    ],
)
def test_rejects_unsafe_or_out_of_scope_sql(sql: str) -> None:
    with pytest.raises(SQLPolicyError):
        validate_sql(sql)


def test_reduces_large_limit() -> None:
    validated = validate_sql("SELECT * FROM adsl LIMIT 999")
    assert validated.sql.endswith("LIMIT 100")
    assert validated.limit_was_changed


def test_preserves_smaller_limit() -> None:
    validated = validate_sql("SELECT * FROM adsl LIMIT 5")
    assert validated.sql.endswith("LIMIT 5")
    assert not validated.limit_was_changed


def test_rejects_dynamic_limit() -> None:
    with pytest.raises(SQLPolicyError):
        validate_sql("SELECT * FROM adsl LIMIT (SELECT COUNT(*) FROM adsl)")
