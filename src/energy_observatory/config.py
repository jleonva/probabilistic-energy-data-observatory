from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path
from typing import Any


def load_config(path: Path) -> dict[str, Any]:
    with path.open("rb") as stream:
        config = tomllib.load(stream)
    config["_config_path"] = str(path.resolve())
    config["_config_hash"] = hashlib.sha256(path.read_bytes()).hexdigest()
    return config


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)

