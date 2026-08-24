from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any

import pandas as pd
import requests


BASE_URL = "https://archive-api.open-meteo.com/v1/archive"


@dataclass(frozen=True)
class WeatherResponse:
    geo: str
    url: str
    raw: bytes
    payload: dict[str, Any]
    frame: pd.DataFrame


def fetch_weather(
    geo: str,
    latitude: float,
    longitude: float,
    timezone: str,
    start_date: date,
    end_date: date,
    timeout: int = 90,
) -> WeatherResponse:
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "daily": "temperature_2m_mean,temperature_2m_min,temperature_2m_max",
        "timezone": timezone,
    }
    response = requests.get(
        BASE_URL,
        params=params,
        timeout=timeout,
        headers={"User-Agent": "energy-observatory/0.1"},
    )
    response.raise_for_status()
    payload = response.json()
    daily = payload["daily"]
    frame = pd.DataFrame(
        {
            "date": pd.to_datetime(daily["time"]),
            "temperature_2m_mean": daily["temperature_2m_mean"],
            "temperature_2m_min": daily["temperature_2m_min"],
            "temperature_2m_max": daily["temperature_2m_max"],
        }
    )
    frame.insert(0, "geo", geo)
    return WeatherResponse(
        geo=geo,
        url=response.url,
        raw=response.content,
        payload=payload,
        frame=frame,
    )

