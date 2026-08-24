from pathlib import Path

from energy_observatory.database import connect, insert_observations, record_snapshot
from energy_observatory.provenance import Snapshot
from energy_observatory.revisions import compare_snapshots


def _snapshot(tmp_path: Path, digest: str) -> Snapshot:
    path = tmp_path / f"{digest}.json"
    path.write_text("{}", encoding="utf-8")
    return Snapshot("eurostat", "test", path, digest, "2026-01-01T00:00:00+00:00", 1, "query")


def _row(snapshot_id: str, value: float):
    return {
        "source": "eurostat", "dataset_code": "test", "geo": "FR", "period": "2024-01",
        "measure_code": "AIM", "measure_label": "Availability", "unit": "GWH", "value": value,
        "observation_flag": None, "snapshot_id": snapshot_id, "ingested_at_utc": "2026-01-01T00:00:00+00:00",
    }


def test_first_snapshot_is_not_a_fake_revision(tmp_path):
    connection = connect(tmp_path / "test.sqlite")
    _, snapshot_id = record_snapshot(connection, _snapshot(tmp_path, "a" * 64))
    insert_observations(connection, [_row(snapshot_id, 10.0)])
    changes, summary = compare_snapshots(connection, "eurostat", "test", snapshot_id)
    assert changes.empty
    assert summary["status"] == "NO_PRIOR_SNAPSHOT"


def test_modified_value_is_detected(tmp_path):
    connection = connect(tmp_path / "test.sqlite")
    _, first = record_snapshot(connection, _snapshot(tmp_path, "a" * 64))
    insert_observations(connection, [_row(first, 10.0)])
    _, second = record_snapshot(connection, _snapshot(tmp_path, "b" * 64))
    insert_observations(connection, [_row(second, 12.0)])
    changes, summary = compare_snapshots(connection, "eurostat", "test", second)
    assert summary["modified"] == 1
    assert changes.iloc[0]["change_type"] == "MODIFIED"

