from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import urllib.request
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast

import duckdb

UPSTREAM_COMMIT = "b8068a0b9a6da07d8b3efef27ae4fc40110054e9"
FIXTURE_URL = (
    "https://raw.githubusercontent.com/cdisc-org/sdtm-adam-pilot-project/"
    f"{UPSTREAM_COMMIT}/updated-pilot-submission-package/900172/m5/datasets/"
    "cdiscpilot01/analysis/adam/datasets/adsl.json"
)
EXPECTED_SHA256 = "5f8815fc77b65674ce9af5f8b67b08ab7dc5e0c87d439f7d3c2add062a91affa"
EXPECTED_ROWS = 254
EXPECTED_COLUMNS = 48
REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_JSON_PATH = REPO_ROOT / "data" / "adsl.json"
DEFAULT_DB_PATH = REPO_ROOT / "data" / "seqchat.duckdb"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_fixture(destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        verify_checksum(destination)
        return
    file_descriptor, temporary_name = tempfile.mkstemp(dir=destination.parent, suffix=".download")
    os.close(file_descriptor)
    temporary = Path(temporary_name)
    try:
        with urllib.request.urlopen(FIXTURE_URL, timeout=60) as response:  # noqa: S310
            temporary.write_bytes(response.read())
        verify_checksum(temporary)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def verify_checksum(path: Path) -> None:
    actual = sha256(path)
    if actual != EXPECTED_SHA256:
        raise ValueError(f"Fixture checksum mismatch: expected {EXPECTED_SHA256}, got {actual}")


def map_dataset_json(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    columns = payload.get("columns")
    rows = payload.get("rows")
    if not isinstance(columns, list) or not isinstance(rows, list):
        raise ValueError("Dataset-JSON must contain columns and rows arrays")
    raw_names = [column.get("name") for column in columns if isinstance(column, dict)]
    if len(raw_names) != len(columns) or not all(
        isinstance(name, str) and name for name in raw_names
    ):
        raise ValueError("Every Dataset-JSON column must have a non-empty name")
    names = cast(list[str], raw_names)
    mapped: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if not isinstance(row, list) or len(row) != len(names):
            raise ValueError(f"Row {index} does not match the column count")
        mapped.append(dict(zip(names, row, strict=True)))
    return mapped, names


def _duckdb_type(values: Sequence[Any]) -> str:
    populated = [value for value in values if value is not None]
    if populated and all(isinstance(value, bool) for value in populated):
        return "BOOLEAN"
    if populated and all(
        isinstance(value, int) and not isinstance(value, bool) for value in populated
    ):
        return "BIGINT"
    if populated and all(
        isinstance(value, (int, float)) and not isinstance(value, bool) for value in populated
    ):
        return "DOUBLE"
    return "VARCHAR"


def initialize_database(
    json_path: Path = DEFAULT_JSON_PATH, db_path: Path = DEFAULT_DB_PATH
) -> None:
    verify_checksum(json_path)
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    mapped, names = map_dataset_json(payload)
    if len(mapped) != EXPECTED_ROWS or len(names) != EXPECTED_COLUMNS:
        raise ValueError(
            f"Unexpected fixture dimensions: got {len(mapped)} rows and {len(names)} columns"
        )

    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(db_path))
    try:
        definitions = ", ".join(
            f'"{name.replace(chr(34), chr(34) * 2)}" '
            f'{_duckdb_type([row[name] for row in mapped])}'
            for name in names
        )
        connection.execute("DROP TABLE IF EXISTS adsl")
        connection.execute(f"CREATE TABLE adsl ({definitions})")
        placeholders = ", ".join("?" for _ in names)
        connection.executemany(
            f"INSERT INTO adsl VALUES ({placeholders})",
            [[row[name] for name in names] for row in mapped],
        )
        row_result = connection.execute("SELECT COUNT(*) FROM adsl").fetchone()
        column_result = connection.execute(
            "SELECT COUNT(*) FROM pragma_table_info('adsl')"
        ).fetchone()
        if row_result is None or column_result is None:
            raise RuntimeError("Could not verify initialized database")
        if (row_result[0], column_result[0]) != (EXPECTED_ROWS, EXPECTED_COLUMNS):
            raise RuntimeError("Initialized database dimensions are incorrect")
    finally:
        connection.close()


def prepare_data(json_path: Path = DEFAULT_JSON_PATH, db_path: Path = DEFAULT_DB_PATH) -> None:
    download_fixture(json_path)
    initialize_database(json_path, db_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare the pinned ADSL fixture and DuckDB file")
    parser.add_argument("--json-path", type=Path, default=DEFAULT_JSON_PATH)
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    args = parser.parse_args()
    prepare_data(args.json_path, args.db_path)
    print(f"Prepared adsl: {EXPECTED_ROWS} rows, {EXPECTED_COLUMNS} columns")


if __name__ == "__main__":
    main()
