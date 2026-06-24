from __future__ import annotations

import csv
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATABASE = PROJECT_ROOT / "backend" / "data" / "bookpile.db"
REPORTS_DIRECTORY = PROJECT_ROOT / "maintenance" / "reports"


def database_path() -> Path:
    return Path(os.getenv("BOOKPILE_DATABASE", DEFAULT_DATABASE))


def connect_read_only() -> sqlite3.Connection:
    path = database_path().resolve()
    connection = sqlite3.connect(f"{path.as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def report_path(prefix: str) -> Path:
    REPORTS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return REPORTS_DIRECTORY / f"{prefix}-{timestamp}.csv"


def write_csv(path: Path, columns: Iterable[str], rows: Iterable[dict]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(columns))
        writer.writeheader()
        writer.writerows(rows)
