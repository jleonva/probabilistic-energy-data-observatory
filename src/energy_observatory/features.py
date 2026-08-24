from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd


def monthly_weather_features(
    weather: pd.DataFrame,
    cutoff_day: int,
    temperature_base_c: float,
) -> pd.DataFrame:
    frame = weather.copy()
    frame["date"] = pd.to_datetime(frame["date"])
    frame = frame[frame["date"].dt.day <= cutoff_day].copy()
    frame["period"] = frame["date"].dt.to_period("M")
    frame["hdd"] = (temperature_base_c - frame["temperature_2m_mean"]).clip(lower=0)
    frame["cdd"] = (frame["temperature_2m_mean"] - temperature_base_c).clip(lower=0)
    features = frame.groupby(["geo", "period"], as_index=False).agg(
        hdd_partial=("hdd", "sum"),
        cdd_partial=("cdd", "sum"),
        temperature_mean_partial=("temperature_2m_mean", "mean"),
        weather_days=("date", "count"),
        effective_weather_cutoff=("date", "max"),
    )
    features["weather_coverage"] = features["weather_days"] / cutoff_day
    return features


def build_model_frame(
    target: pd.DataFrame,
    weather_features: pd.DataFrame,
) -> pd.DataFrame:
    frame = target[["geo", "time", "value"]].rename(columns={"time": "period", "value": "target"}).copy()
    frame["period"] = pd.PeriodIndex(frame["period"], freq="M")
    frame = frame.sort_values(["geo", "period"])
    frame["lag3"] = frame.groupby("geo")["target"].shift(3)
    frame["lag12"] = frame.groupby("geo")["target"].shift(12)
    frame["month_sin"] = np.sin(2 * np.pi * frame["period"].dt.month / 12)
    frame["month_cos"] = np.cos(2 * np.pi * frame["period"].dt.month / 12)
    frame = frame.merge(weather_features, on=["geo", "period"], how="left")
    return frame


def current_feature_rows(
    target: pd.DataFrame,
    weather_features: pd.DataFrame,
    period: pd.Period,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for geo in sorted(target["geo"].unique()):
        series = target[target["geo"] == geo].set_index(pd.PeriodIndex(target[target["geo"] == geo]["time"], freq="M"))["value"]
        weather_row = weather_features[(weather_features["geo"] == geo) & (weather_features["period"] == period)]
        if weather_row.empty or period - 3 not in series.index or period - 12 not in series.index:
            continue
        weather_values = weather_row.iloc[0].to_dict()
        rows.append({
            "geo": geo, "period": period, "target": np.nan,
            "lag3": float(series.loc[period - 3]), "lag12": float(series.loc[period - 12]),
            "month_sin": float(np.sin(2 * np.pi * period.month / 12)),
            "month_cos": float(np.cos(2 * np.pi * period.month / 12)),
            **{key: weather_values[key] for key in ["hdd_partial", "cdd_partial",
                "temperature_mean_partial", "weather_days", "effective_weather_cutoff", "weather_coverage"]},
        })
    return pd.DataFrame(rows)
