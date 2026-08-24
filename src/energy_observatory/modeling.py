from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


NUMERIC_FEATURES = [
    "lag3", "lag12", "month_sin", "month_cos", "hdd_partial", "cdd_partial",
    "temperature_mean_partial", "weather_days", "weather_coverage",
]
MODEL_FEATURES = ["geo", *NUMERIC_FEATURES]


def build_model() -> Pipeline:
    transformer = ColumnTransformer(
        [
            ("numeric", StandardScaler(), NUMERIC_FEATURES),
            ("country", OneHotEncoder(handle_unknown="ignore", drop="first"), ["geo"]),
        ]
    )
    return Pipeline([("features", transformer), ("ridge", Ridge(alpha=1.0))])


def _conformal_radius(residuals: list[float], coverage: float) -> float | None:
    if len(residuals) < 20:
        return None
    return float(np.quantile(np.asarray(residuals), coverage, method="higher"))


def rolling_origin_evaluation(
    frame: pd.DataFrame,
    release_lag_months: int,
    minimum_months_per_country: int,
    interval_coverage: float,
) -> pd.DataFrame:
    usable = frame.dropna(subset=["target", *NUMERIC_FEATURES]).copy()
    periods = sorted(usable["period"].unique())
    predictions: list[dict[str, Any]] = []
    for origin in periods:
        train_end = origin - release_lag_months
        train = usable[usable["period"] <= train_end]
        test = usable[usable["period"] == origin]
        if set(test["geo"]) != set(usable["geo"].unique()):
            continue
        counts = train.groupby("geo").size()
        if counts.empty or int(counts.min()) < minimum_months_per_country:
            continue
        model = build_model()
        model.fit(train[MODEL_FEATURES], train["target"])
        point = model.predict(test[MODEL_FEATURES])
        known_residuals = [
            abs(float(row["actual"]) - float(row["candidate"]))
            for row in predictions
            if row["period"] <= train_end
        ]
        radius = _conformal_radius(known_residuals, interval_coverage)
        for (_, row), estimate in zip(test.iterrows(), point, strict=True):
            lower = max(0.0, float(estimate - radius)) if radius is not None else np.nan
            upper = float(estimate + radius) if radius is not None else np.nan
            predictions.append({
                "geo": row["geo"], "period": origin,
                "origin_cutoff_day": 20, "last_target_available": train_end,
                "training_rows": int(len(train)), "actual": float(row["target"]),
                "baseline": float(row["lag12"]), "candidate": float(estimate),
                "lower_80": lower, "upper_80": upper,
                "calibration_residuals": len(known_residuals),
            })
    return pd.DataFrame(predictions)


def _interval_score(actual: pd.Series, lower: pd.Series, upper: pd.Series, alpha: float) -> pd.Series:
    width = upper - lower
    below = (2 / alpha) * (lower - actual) * (actual < lower)
    above = (2 / alpha) * (actual - upper) * (actual > upper)
    return width + below + above


def calculate_metrics(predictions: pd.DataFrame, coverage: float) -> pd.DataFrame:
    records: list[dict[str, Any]] = []
    groups: list[tuple[str, pd.DataFrame]] = [("ALL", predictions)]
    groups.extend((geo, group) for geo, group in predictions.groupby("geo"))
    for geo, group in groups:
        for model_name in ["baseline", "candidate"]:
            errors = group[model_name] - group["actual"]
            record: dict[str, Any] = {
                "geo": geo, "model": model_name, "origins": int(len(group)),
                "mae": float(errors.abs().mean()),
                "rmse": float(np.sqrt(np.mean(np.square(errors)))),
                "empirical_coverage_80": np.nan, "mean_interval_width": np.nan,
                "interval_score_80": np.nan,
            }
            if model_name == "candidate":
                valid = group.dropna(subset=["lower_80", "upper_80"])
                if not valid.empty:
                    inside = (valid["actual"] >= valid["lower_80"]) & (valid["actual"] <= valid["upper_80"])
                    record["empirical_coverage_80"] = float(inside.mean())
                    record["mean_interval_width"] = float((valid["upper_80"] - valid["lower_80"]).mean())
                    record["interval_score_80"] = float(_interval_score(
                        valid["actual"], valid["lower_80"], valid["upper_80"], 1 - coverage
                    ).mean())
            records.append(record)
    return pd.DataFrame(records)


def evaluate_h2(metrics: pd.DataFrame) -> dict[str, Any]:
    pivot = metrics.pivot(index="geo", columns="model", values="mae")
    aggregate_improved = bool(pivot.loc["ALL", "candidate"] < pivot.loc["ALL", "baseline"])
    country_results = {
        geo: bool(pivot.loc[geo, "candidate"] <= pivot.loc[geo, "baseline"])
        for geo in pivot.index if geo != "ALL"
    }
    if aggregate_improved and all(country_results.values()):
        status = "SUPPORTED"
    elif aggregate_improved:
        status = "MIXED"
    else:
        status = "NOT_SUPPORTED"
    return {
        "hypothesis_id": "H2", "status": status,
        "claim": "A simple weather-adjusted model improves pseudo-real-time monthly nowcasts relative to a seasonal-naive baseline.",
        "primary_metric": "aggregate MAE", "aggregate_improved": aggregate_improved,
        "country_mae_not_worse": country_results,
        "note": "Descriptive rolling-origin evidence; no statistical significance claim.",
    }


def make_current_nowcast(
    frame: pd.DataFrame,
    current_rows: pd.DataFrame,
    current_period: pd.Period,
    release_lag_months: int,
    prior_predictions: pd.DataFrame,
    interval_coverage: float,
) -> pd.DataFrame:
    if current_rows.empty:
        return pd.DataFrame()
    train_end = current_period - release_lag_months
    train = frame.dropna(subset=["target", *NUMERIC_FEATURES])
    train = train[train["period"] <= train_end]
    model = build_model()
    model.fit(train[MODEL_FEATURES], train["target"])
    estimates = model.predict(current_rows[MODEL_FEATURES])
    known = prior_predictions[prior_predictions["period"] <= train_end]
    residuals = (known["actual"] - known["candidate"]).abs().tolist()
    radius = _conformal_radius(residuals, interval_coverage)
    output = current_rows[["geo", "period", "effective_weather_cutoff", "weather_days"]].copy()
    output["last_target_available"] = str(train_end)
    output["point_estimate_gwh"] = estimates
    output["lower_80_gwh"] = [max(0.0, value - radius) if radius is not None else np.nan for value in estimates]
    output["upper_80_gwh"] = [value + radius if radius is not None else np.nan for value in estimates]
    output["calibration_residuals"] = len(residuals)
    output["status"] = "ESTIMATED" if radius is not None else "POINT_ONLY"
    return output
