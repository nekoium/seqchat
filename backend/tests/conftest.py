from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest

from seqchat import data


@pytest.fixture
def dataset_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    names = ["USUBJID", "TRT01P", "SEX"] + [f"COL{i:02d}" for i in range(4, 49)]
    treatments = (
        ["Xanomeline High Dose"] * 84
        + ["Xanomeline Low Dose"] * 84
        + ["Placebo"] * 86
    )
    sexes = ["F"] * 143 + ["M"] * 111
    rows = [
        [f"SUBJECT-{index + 1:03d}", treatments[index], sexes[index], *([None] * 45)]
        for index in range(254)
    ]
    path = tmp_path / "adsl.json"
    path.write_text(
        json.dumps({"columns": [{"name": name} for name in names], "rows": rows}),
        encoding="utf-8",
    )
    monkeypatch.setattr(data, "EXPECTED_SHA256", hashlib.sha256(path.read_bytes()).hexdigest())
    return path


@pytest.fixture
def database_path(dataset_json: Path, tmp_path: Path) -> Path:
    path = tmp_path / "seqchat.duckdb"
    data.initialize_database(dataset_json, path)
    return path


@pytest.fixture
def db_connection(database_path: Path) -> Iterator[duckdb.DuckDBPyConnection]:
    connection = duckdb.connect(str(database_path), read_only=True)
    try:
        yield connection
    finally:
        connection.close()
