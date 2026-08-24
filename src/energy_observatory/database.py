from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .provenance import Snapshot, utc_now


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS ingestion_runs (
  run_id TEXT PRIMARY KEY, source TEXT NOT NULL, dataset_code TEXT NOT NULL,
  requested_at_utc TEXT NOT NULL, completed_at_utc TEXT NOT NULL,
  query_or_url TEXT NOT NULL, http_status INTEGER, source_updated_at TEXT,
  payload_sha256 TEXT NOT NULL, row_count INTEGER NOT NULL,
  status TEXT NOT NULL, error_message TEXT
);
CREATE TABLE IF NOT EXISTS source_snapshots (
  snapshot_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, source TEXT NOT NULL,
  dataset_code TEXT NOT NULL, snapshot_path TEXT NOT NULL, schema_version TEXT,
  payload_sha256 TEXT NOT NULL, created_at_utc TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES ingestion_runs(run_id)
);
CREATE TABLE IF NOT EXISTS observations (
  source TEXT NOT NULL, dataset_code TEXT NOT NULL, geo TEXT NOT NULL,
  period TEXT NOT NULL, measure_code TEXT NOT NULL, measure_label TEXT NOT NULL,
  unit TEXT NOT NULL, value REAL, observation_flag TEXT, snapshot_id TEXT NOT NULL,
  ingested_at_utc TEXT NOT NULL,
  PRIMARY KEY(source, dataset_code, geo, period, measure_code, unit, snapshot_id),
  FOREIGN KEY(snapshot_id) REFERENCES source_snapshots(snapshot_id)
);
CREATE TABLE IF NOT EXISTS revision_events (
  event_id TEXT PRIMARY KEY, source TEXT NOT NULL, dataset_code TEXT NOT NULL,
  observation_key TEXT NOT NULL, previous_snapshot_id TEXT,
  current_snapshot_id TEXT NOT NULL, previous_value REAL, current_value REAL,
  change_type TEXT NOT NULL, detected_at_utc TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS quality_results (
  result_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, check_id TEXT NOT NULL,
  check_name TEXT NOT NULL, status TEXT NOT NULL, severity TEXT NOT NULL,
  affected_rows INTEGER NOT NULL, evidence TEXT NOT NULL, created_at_utc TEXT NOT NULL
);
"""


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    connection.executescript(SCHEMA)
    return connection


def record_snapshot(connection: sqlite3.Connection, snapshot: Snapshot) -> tuple[str, str]:
    run_id, snapshot_id, now = str(uuid.uuid4()), str(uuid.uuid4()), utc_now()
    connection.execute(
        "INSERT INTO ingestion_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, snapshot.source, snapshot.dataset, snapshot.created_at_utc, now,
         snapshot.query, 200, snapshot.source_updated_at, snapshot.sha256,
         snapshot.row_count, "SUCCESS", None),
    )
    connection.execute(
        "INSERT INTO source_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (snapshot_id, run_id, snapshot.source, snapshot.dataset, str(snapshot.path),
         "1", snapshot.sha256, snapshot.created_at_utc),
    )
    connection.commit()
    return run_id, snapshot_id


def insert_observations(connection: sqlite3.Connection, rows: Iterable[dict[str, Any]]) -> None:
    connection.executemany(
        """INSERT OR REPLACE INTO observations
        (source, dataset_code, geo, period, measure_code, measure_label, unit,
         value, observation_flag, snapshot_id, ingested_at_utc)
        VALUES (:source, :dataset_code, :geo, :period, :measure_code,
                :measure_label, :unit, :value, :observation_flag,
                :snapshot_id, :ingested_at_utc)""",
        list(rows),
    )
    connection.commit()


def record_quality(connection: sqlite3.Connection, run_id: str, checks: list[dict[str, Any]]) -> None:
    now = utc_now()
    rows = [
        (str(uuid.uuid4()), run_id, check["check_id"], check["check_name"],
         check["status"], check["severity"], int(check.get("affected_rows", 0)),
         json.dumps(check.get("evidence", {}), ensure_ascii=False, default=str), now)
        for check in checks
    ]
    connection.executemany("INSERT INTO quality_results VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    connection.commit()


def previous_snapshot_id(
    connection: sqlite3.Connection, source: str, dataset: str, current_snapshot_id: str
) -> str | None:
    row = connection.execute(
        """SELECT snapshot_id FROM source_snapshots
           WHERE source=? AND dataset_code=? AND snapshot_id<>?
           ORDER BY created_at_utc DESC LIMIT 1""",
        (source, dataset, current_snapshot_id),
    ).fetchone()
    return row[0] if row else None


def snapshot_observations(connection: sqlite3.Connection, snapshot_id: str) -> pd.DataFrame:
    return pd.read_sql_query(
        """SELECT source, dataset_code, geo, period, measure_code, unit, value
           FROM observations WHERE snapshot_id=?""",
        connection,
        params=(snapshot_id,),
    )
