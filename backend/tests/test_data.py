from pathlib import Path

import duckdb
import pytest

from seqchat.data import initialize_database, map_dataset_json, verify_checksum


def test_maps_dataset_json_columns_to_row_values() -> None:
    mapped, names = map_dataset_json(
        {"columns": [{"name": "A"}, {"name": "B"}], "rows": [[1, "two"]]}
    )
    assert names == ["A", "B"]
    assert mapped == [{"A": 1, "B": "two"}]


def test_rejects_checksum_mismatch(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_checksum(path)


def test_initialization_is_idempotent_with_expected_dimensions(
    dataset_json: Path, database_path: Path
) -> None:
    initialize_database(dataset_json, database_path)
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        assert connection.execute("SELECT COUNT(*) FROM adsl").fetchone()[0] == 254
        column_count = connection.execute(
            "SELECT COUNT(*) FROM pragma_table_info('adsl')"
        ).fetchone()
        assert column_count is not None and column_count[0] == 48
    finally:
        connection.close()


def test_reference_smoke_queries(db_connection: duckdb.DuckDBPyConnection) -> None:
    assert db_connection.execute("SELECT COUNT(*) FROM adsl").fetchone() == (254,)
    treatment = db_connection.execute(
        "SELECT TRT01P, COUNT(*) FROM adsl GROUP BY TRT01P ORDER BY TRT01P"
    ).fetchall()
    assert treatment == [
        ("Placebo", 86),
        ("Xanomeline High Dose", 84),
        ("Xanomeline Low Dose", 84),
    ]
    sex = db_connection.execute(
        "SELECT SEX, COUNT(*) FROM adsl GROUP BY SEX ORDER BY SEX"
    ).fetchall()
    assert sex == [("F", 143), ("M", 111)]
