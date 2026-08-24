from __future__ import annotations

import importlib.metadata
import json
import platform
import subprocess
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from .config import load_config
from .database import connect, insert_observations, record_quality, record_snapshot
from .features import build_model_frame, current_feature_rows, monthly_weather_features
from .modeling import calculate_metrics, evaluate_h2, make_current_nowcast, rolling_origin_evaluation
from .provenance import save_snapshot, utc_now, write_json
from .quality import run_quality_checks
from .reporting import build_dashboard, write_documentation
from .revisions import compare_snapshots
from .sources.eurostat import describe_payload, fetch_dataset
from .sources.open_meteo import fetch_weather


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _observation_rows(
    frame: pd.DataFrame,
    source: str,
    dataset: str,
    measure_code: str,
    measure_label: str,
    unit: str,
    snapshot_id: str,
) -> list[dict[str, Any]]:
    now = utc_now()
    return [
        {
            "source": source, "dataset_code": dataset, "geo": row.geo,
            "period": str(row.time), "measure_code": measure_code,
            "measure_label": measure_label, "unit": unit,
            "value": None if pd.isna(row.value) else float(row.value),
            "observation_flag": None if pd.isna(row.observation_flag) else str(row.observation_flag),
            "snapshot_id": snapshot_id, "ingested_at_utc": now,
        }
        for row in frame.itertuples()
    ]


def _weather_observation_rows(
    frame: pd.DataFrame, snapshot_id: str
) -> list[dict[str, Any]]:
    now = utc_now()
    rows: list[dict[str, Any]] = []
    for row in frame.itertuples():
        for measure in ["temperature_2m_mean", "temperature_2m_min", "temperature_2m_max"]:
            value = getattr(row, measure)
            rows.append({
                "source": "open_meteo", "dataset_code": "historical_weather",
                "geo": row.geo, "period": pd.Timestamp(row.date).strftime("%Y-%m-%d"),
                "measure_code": measure, "measure_label": measure.replace("_", " "),
                "unit": "DEG_C", "value": None if pd.isna(value) else float(value),
                "observation_flag": None, "snapshot_id": snapshot_id,
                "ingested_at_utc": now,
            })
    return rows


def _git_value(root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=root, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unavailable"


def run(root: Path | None = None) -> dict[str, Any]:
    root = (root or _root()).resolve()
    config = load_config(root / "config" / "project.toml")
    settings = config["project"]
    artifacts = root / config["paths"]["artifacts"]
    snapshots_dir = root / config["paths"]["snapshots"]
    docs = root / config["paths"]["docs"]
    for directory in [artifacts, snapshots_dir, docs]:
        directory.mkdir(parents=True, exist_ok=True)

    electricity_cfg = config["eurostat"]["electricity"]
    target_response = fetch_dataset(
        electricity_cfg["dataset"],
        {"freq": electricity_cfg["freq"], "nrg_bal": electricity_cfg["nrg_bal"],
         "siec": electricity_cfg["siec"], "unit": electricity_cfg["unit"],
         "geo": electricity_cfg["geos"]},
    )
    target = target_response.frame.sort_values(["geo", "time"]).reset_index(drop=True)

    hicp_cfg = config["eurostat"]["hicp"]
    hicp_response = fetch_dataset(
        hicp_cfg["dataset"],
        {"freq": hicp_cfg["freq"], "unit": hicp_cfg["unit"],
         hicp_cfg["coicop_dimension"]: hicp_cfg["coicop"], "geo": hicp_cfg["geos"]},
    )
    hicp = hicp_response.frame.sort_values(["geo", "time"]).reset_index(drop=True)

    today = date.today()
    intended_cutoff = today.replace(day=min(int(settings["cutoff_day"]), today.day))
    archive_safe_end = min(intended_cutoff, today - timedelta(days=5))
    start_date = date.fromisoformat(settings["start_date"])
    weather_frames: list[pd.DataFrame] = []
    weather_responses = []
    for geo in electricity_cfg["geos"]:
        weather_cfg = config["weather"][geo]
        response = fetch_weather(
            geo, float(weather_cfg["latitude"]), float(weather_cfg["longitude"]),
            weather_cfg["timezone"], start_date, archive_safe_end,
        )
        weather_responses.append(response)
        weather_frames.append(response.frame)
    weather = pd.concat(weather_frames, ignore_index=True).sort_values(["geo", "date"])

    source_probe = {
        "generated_at_utc": utc_now(),
        "electricity": {
            "dataset": electricity_cfg["dataset"], "url": target_response.url,
            "label": target_response.payload.get("label"), "updated": target_response.payload.get("updated"),
            "dimensions": target_response.payload.get("id"), "sizes": target_response.payload.get("size"),
            "verified_labels": {
                "nrg_bal": target_response.payload["dimension"]["nrg_bal"]["category"]["label"][electricity_cfg["nrg_bal"]],
                "siec": target_response.payload["dimension"]["siec"]["category"]["label"][electricity_cfg["siec"]],
                "unit": target_response.payload["dimension"]["unit"]["category"]["label"][electricity_cfg["unit"]],
            },
            "first_period": target["time"].min(), "last_period": target["time"].max(),
            "coverage_by_geo": {
                geo: {"first": group["time"].min(), "last": group["time"].max(), "rows": len(group)}
                for geo, group in target.groupby("geo")
            },
            "rows": len(target),
        },
        "hicp": {
            "dataset": hicp_cfg["dataset"], "url": hicp_response.url,
            "label": hicp_response.payload.get("label"), "updated": hicp_response.payload.get("updated"),
            "dimensions": hicp_response.payload.get("id"), "sizes": hicp_response.payload.get("size"),
            "verified_label": hicp_response.payload["dimension"][hicp_cfg["coicop_dimension"]]["category"]["label"][hicp_cfg["coicop"]],
            "first_period": hicp["time"].min(), "last_period": hicp["time"].max(), "rows": len(hicp),
        },
        "weather": {
            "source": "Open-Meteo Historical Weather API", "start_date": str(start_date),
            "requested_end_date": str(archive_safe_end), "rows": len(weather),
            "latest_by_geo": weather.groupby("geo")["date"].max().dt.strftime("%Y-%m-%d").to_dict(),
            "urls": [item.url for item in weather_responses],
        },
    }
    write_json(artifacts / "source_probe.json", source_probe)

    connection = connect(root / config["paths"]["database"])
    target_snapshot = save_snapshot(
        target_response.raw, snapshots_dir, "eurostat", electricity_cfg["dataset"],
        target_response.url, len(target), target_response.payload.get("updated"),
    )
    target_run_id, target_snapshot_id = record_snapshot(connection, target_snapshot)
    insert_observations(connection, _observation_rows(
        target, "eurostat", electricity_cfg["dataset"], electricity_cfg["nrg_bal"],
        "Electricity available to internal market", electricity_cfg["unit"], target_snapshot_id,
    ))

    hicp_snapshot = save_snapshot(
        hicp_response.raw, snapshots_dir, "eurostat", hicp_cfg["dataset"],
        hicp_response.url, len(hicp), hicp_response.payload.get("updated"),
    )
    _, hicp_snapshot_id = record_snapshot(connection, hicp_snapshot)
    insert_observations(connection, _observation_rows(
        hicp, "eurostat", hicp_cfg["dataset"], hicp_cfg["coicop"],
        "Consumer electricity price index", hicp_cfg["unit"], hicp_snapshot_id,
    ))

    for response in weather_responses:
        snapshot = save_snapshot(
            response.raw, snapshots_dir, "open_meteo", f"historical_weather_{response.geo}",
            response.url, len(response.frame), None,
        )
        _, snapshot_id = record_snapshot(connection, snapshot)
        insert_observations(connection, _weather_observation_rows(response.frame, snapshot_id))

    checks = run_quality_checks(
        target, hicp, weather, set(electricity_cfg["geos"]), int(settings["cutoff_day"]),
    )
    record_quality(connection, target_run_id, checks)
    write_json(artifacts / "quality_report.json", {"checks": checks})
    if any(item["status"] == "FAIL" for item in checks[:2]):
        raise RuntimeError("Critical target semantic or uniqueness check failed; modelling stopped.")

    changes, revision_summary = compare_snapshots(
        connection, "eurostat", electricity_cfg["dataset"], target_snapshot_id,
    )
    changes.to_csv(artifacts / "revision_report.csv", index=False)
    write_json(artifacts / "revision_summary.json", revision_summary)

    weather_features = monthly_weather_features(
        weather, int(settings["cutoff_day"]), float(settings["temperature_base_c"]),
    )
    model_frame = build_model_frame(target, weather_features)
    predictions = rolling_origin_evaluation(
        model_frame, int(settings["release_lag_months"]),
        int(settings["minimum_months_per_country"]), float(settings["prediction_interval_coverage"]),
    )
    if predictions.empty:
        raise RuntimeError("No valid rolling-origin predictions were produced.")
    metrics = calculate_metrics(predictions, float(settings["prediction_interval_coverage"]))
    h2 = evaluate_h2(metrics)
    h1 = {
        "hypothesis_id": "H1", "status": "NOT_TESTED",
        "claim": "A release-safe electricity HICP feature may improve electricity-availability nowcasting.",
        "reason": "Historical HICP release vintages were not reconstructed; HICP is context only.",
    }
    hypotheses = [h1, h2]

    requested_current_period = pd.Period(today, freq="M")
    common_latest_target = min(
        pd.Period(value, freq="M") for value in target.groupby("geo")["time"].max().values
    )
    latest_jointly_estimable = common_latest_target + int(settings["release_lag_months"])
    current_period = min(requested_current_period, latest_jointly_estimable)
    current_rows = current_feature_rows(target, weather_features, current_period)
    current = make_current_nowcast(
        model_frame, current_rows, current_period, int(settings["release_lag_months"]),
        predictions, float(settings["prediction_interval_coverage"]),
    )
    if not current.empty:
        current["as_of_date"] = today.isoformat()
        current["requested_current_period"] = str(requested_current_period)
        current["intended_cutoff_day"] = int(settings["cutoff_day"])
        current["selection_note"] = "Latest period jointly estimable for France and Germany under the three-month release-lag assumption."
    predictions.assign(period=predictions["period"].astype(str),
                       last_target_available=predictions["last_target_available"].astype(str)).to_csv(
        artifacts / "rolling_predictions.csv", index=False
    )
    metrics.to_csv(artifacts / "model_metrics.csv", index=False)
    current.assign(period=current["period"].astype(str)).to_csv(artifacts / "current_nowcast.csv", index=False)
    write_json(artifacts / "hypothesis_register.json", hypotheses)

    data_dictionary = pd.DataFrame([
        {"field": "target", "definition": "Eurostat electricity available to internal market", "unit": "GWh", "role": "estimand"},
        {"field": "lag3", "definition": "Target value three months earlier", "unit": "GWh", "role": "feature"},
        {"field": "lag12", "definition": "Target value twelve months earlier", "unit": "GWh", "role": "feature/baseline"},
        {"field": "hdd_partial", "definition": "Heating degree days accumulated through cutoff", "unit": "degree-days", "role": "feature"},
        {"field": "cdd_partial", "definition": "Cooling degree days accumulated through cutoff", "unit": "degree-days", "role": "feature"},
        {"field": "hicp", "definition": "Consumer electricity price index", "unit": "2025=100", "role": "context only"},
    ])
    data_dictionary.to_csv(artifacts / "data_dictionary.csv", index=False)

    run_summary = {
        "status": "COMPLETE", "generated_at_utc": utc_now(), "python": sys.version,
        "platform": platform.platform(), "config_path": config["_config_path"],
        "config_sha256": config["_config_hash"], "git_branch": _git_value(root, "branch", "--show-current"),
        "git_commit": _git_value(root, "rev-parse", "HEAD"),
        "packages": {name: importlib.metadata.version(name) for name in
                     ["numpy", "pandas", "plotly", "requests", "scikit-learn"]},
        "target_rows": len(target), "hicp_rows": len(hicp), "weather_rows": len(weather),
        "prediction_rows": len(predictions), "current_nowcast_rows": len(current),
        "requested_current_period": str(requested_current_period),
        "joint_nowcast_period": str(current_period),
        "revision_status": revision_summary["status"], "h1_status": h1["status"],
        "h2_status": h2["status"], "published": False, "pushed": False,
    }
    write_json(artifacts / "run_summary.json", run_summary)

    build_dashboard(
        docs / "index.html", target, hicp, predictions, metrics, current,
        checks, hypotheses, source_probe,
    )
    write_documentation(root, target, metrics, current, checks, hypotheses, revision_summary)
    connection.close()
    return run_summary
