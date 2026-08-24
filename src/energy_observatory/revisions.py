from __future__ import annotations

import sqlite3
import uuid
from typing import Any

import pandas as pd

from .database import previous_snapshot_id, snapshot_observations
from .provenance import utc_now


KEY = ["source", "dataset_code", "geo", "period", "measure_code", "unit"]


def compare_snapshots(
    connection: sqlite3.Connection,
    source: str,
    dataset: str,
    current_snapshot_id: str,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    previous_id = previous_snapshot_id(connection, source, dataset, current_snapshot_id)
    if previous_id is None:
        empty = pd.DataFrame(columns=KEY + ["previous_value", "current_value", "change_type"])
        return empty, {
            "source": source, "dataset": dataset, "status": "NO_PRIOR_SNAPSHOT",
            "previous_snapshot_id": None, "current_snapshot_id": current_snapshot_id,
            "added": 0, "removed": 0, "modified": 0,
        }
    previous = snapshot_observations(connection, previous_id).rename(columns={"value": "previous_value"})
    current = snapshot_observations(connection, current_snapshot_id).rename(columns={"value": "current_value"})
    merged = previous.merge(current, on=KEY, how="outer", indicator=True)
    merged["change_type"] = "UNCHANGED"
    merged.loc[merged["_merge"] == "left_only", "change_type"] = "REMOVED"
    merged.loc[merged["_merge"] == "right_only", "change_type"] = "ADDED"
    modified = (merged["_merge"] == "both") & (merged["previous_value"] != merged["current_value"])
    merged.loc[modified, "change_type"] = "MODIFIED"
    changes = merged[merged["change_type"] != "UNCHANGED"].drop(columns="_merge").copy()
    now = utc_now()
    for row in changes.to_dict("records"):
        key = "|".join(str(row[col]) for col in KEY)
        connection.execute(
            "INSERT INTO revision_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), source, dataset, key, previous_id, current_snapshot_id,
             row.get("previous_value"), row.get("current_value"), row["change_type"], now),
        )
    connection.commit()
    summary = {
        "source": source, "dataset": dataset, "status": "COMPARED",
        "previous_snapshot_id": previous_id, "current_snapshot_id": current_snapshot_id,
        "added": int((changes["change_type"] == "ADDED").sum()),
        "removed": int((changes["change_type"] == "REMOVED").sum()),
        "modified": int((changes["change_type"] == "MODIFIED").sum()),
    }
    return changes, summary

