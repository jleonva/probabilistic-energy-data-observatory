from __future__ import annotations

import itertools
import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import pandas as pd
import requests


BASE_URL = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"


@dataclass(frozen=True)
class EurostatResponse:
    dataset: str
    url: str
    raw: bytes
    payload: dict[str, Any]
    frame: pd.DataFrame


def build_url(dataset: str, filters: dict[str, Any]) -> str:
    pairs: list[tuple[str, str]] = [("lang", "en")]
    for key, value in filters.items():
        if isinstance(value, (list, tuple)):
            pairs.extend((key, str(item)) for item in value)
        else:
            pairs.append((key, str(value)))
    return f"{BASE_URL}/{dataset}?{urlencode(pairs)}"


def fetch_dataset(dataset: str, filters: dict[str, Any], timeout: int = 60) -> EurostatResponse:
    url = build_url(dataset, filters)
    response = requests.get(url, timeout=timeout, headers={"User-Agent": "energy-observatory/0.1"})
    response.raise_for_status()
    payload = response.json()
    frame = parse_jsonstat(payload)
    return EurostatResponse(dataset=dataset, url=url, raw=response.content, payload=payload, frame=frame)


def _position_to_code(dimension: dict[str, Any]) -> dict[int, str]:
    index = dimension["category"]["index"]
    if isinstance(index, list):
        return {position: code for position, code in enumerate(index)}
    return {int(position): code for code, position in index.items()}


def parse_jsonstat(payload: dict[str, Any]) -> pd.DataFrame:
    ids = list(payload["id"])
    sizes = [int(value) for value in payload["size"]]
    position_maps = {dim: _position_to_code(payload["dimension"][dim]) for dim in ids}
    label_maps = {
        dim: payload["dimension"][dim]["category"].get("label", {}) for dim in ids
    }
    values = payload.get("value", {})
    statuses = payload.get("status", {})
    if isinstance(values, list):
        values = {str(i): value for i, value in enumerate(values) if value is not None}
    rows: list[dict[str, Any]] = []
    for flat_key, value in values.items():
        flat_index = int(flat_key)
        positions: list[int] = [0] * len(sizes)
        remainder = flat_index
        for idx in range(len(sizes) - 1, -1, -1):
            positions[idx] = remainder % sizes[idx]
            remainder //= sizes[idx]
        row: dict[str, Any] = {}
        for dim, position in zip(ids, positions, strict=True):
            code = position_maps[dim][position]
            row[dim] = code
            row[f"{dim}_label"] = label_maps[dim].get(code, code)
        row["value"] = float(value) if value is not None else None
        row["observation_flag"] = statuses.get(str(flat_index))
        rows.append(row)
    return pd.DataFrame(rows)


def describe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    description: dict[str, Any] = {
        "label": payload.get("label"),
        "source": payload.get("source"),
        "updated": payload.get("updated"),
        "dimensions": list(payload.get("id", [])),
        "sizes": list(payload.get("size", [])),
    }
    for dim in payload.get("id", []):
        labels = payload["dimension"][dim]["category"].get("label", {})
        description[f"{dim}_labels"] = labels
    return description

