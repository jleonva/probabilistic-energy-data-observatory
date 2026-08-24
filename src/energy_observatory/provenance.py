from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Snapshot:
    source: str
    dataset: str
    path: Path
    sha256: str
    created_at_utc: str
    row_count: int
    query: str
    source_updated_at: str | None = None


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def save_snapshot(
    payload: bytes,
    snapshot_dir: Path,
    source: str,
    dataset: str,
    query: str,
    row_count: int,
    source_updated_at: str | None = None,
) -> Snapshot:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(payload).hexdigest()
    created = utc_now()
    stamp = created.replace(":", "").replace("+00:00", "Z").replace("-", "")
    path = snapshot_dir / f"{source}_{dataset}_{stamp}_{digest[:12]}.json"
    if not path.exists():
        path.write_bytes(payload)
    return Snapshot(
        source=source,
        dataset=dataset,
        path=path,
        sha256=digest,
        created_at_utc=created,
        row_count=row_count,
        query=query,
        source_updated_at=source_updated_at,
    )


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")

