from __future__ import annotations

from typing import Any

import pandas as pd


def _check(
    check_id: str,
    name: str,
    status: str,
    severity: str,
    affected_rows: int,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "check_name": name,
        "status": status,
        "severity": severity,
        "affected_rows": int(affected_rows),
        "evidence": evidence,
    }


def run_quality_checks(
    target: pd.DataFrame,
    hicp: pd.DataFrame,
    weather: pd.DataFrame,
    expected_geos: set[str],
    cutoff_day: int,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    semantic_ok = (
        set(target["freq"].unique()) == {"M"}
        and set(target["unit"].unique()) == {"GWH"}
        and set(target["nrg_bal"].unique()) == {"AIM"}
        and set(target["siec"].unique()) == {"E7000"}
        and set(target["geo"].unique()) == expected_geos
    )
    checks.append(_check(
        "DQ-01", "Schema and code validity", "PASS" if semantic_ok else "FAIL",
        "ERROR", 0 if semantic_ok else len(target),
        {"dimensions": ["freq", "nrg_bal", "siec", "unit", "geo", "time"],
         "observed_geos": sorted(target["geo"].unique()),
         "expected": {"freq": "M", "unit": "GWH", "nrg_bal": "AIM", "siec": "E7000"}},
    ))

    key = ["geo", "time", "nrg_bal", "siec", "unit"]
    duplicates = int(target.duplicated(key, keep=False).sum())
    checks.append(_check(
        "DQ-02", "Primary-key uniqueness", "PASS" if duplicates == 0 else "FAIL",
        "ERROR", duplicates, {"key": key},
    ))

    missing_periods: dict[str, list[str]] = {}
    for geo, group in target.groupby("geo"):
        periods = pd.PeriodIndex(group["time"], freq="M")
        expected = pd.period_range(periods.min(), periods.max(), freq="M")
        missing_periods[geo] = [str(value) for value in expected.difference(periods)]
    gaps = sum(len(values) for values in missing_periods.values())
    checks.append(_check(
        "DQ-03", "Temporal continuity and coverage", "PASS" if gaps == 0 else "WARN",
        "WARNING", gaps,
        {"missing_periods": missing_periods,
         "coverage": {geo: {"first": str(group["time"].min()), "last": str(group["time"].max()),
                            "rows": int(len(group))} for geo, group in target.groupby("geo")}},
    ))

    missing_values = int(target["value"].isna().sum())
    flagged = int(target["observation_flag"].notna().sum())
    checks.append(_check(
        "DQ-04", "Missing values and observation flags",
        "PASS" if missing_values == 0 else "FAIL", "ERROR", missing_values,
        {"missing_values": missing_values, "flagged_observations": flagged,
         "flags": sorted(target["observation_flag"].dropna().astype(str).unique())},
    ))

    negative = int((target["value"] < 0).sum())
    zeros = int((target["value"] == 0).sum())
    extreme_changes = 0
    for _, group in target.sort_values("time").groupby("geo"):
        extreme_changes += int((group["value"].pct_change().abs() > 0.5).sum())
    range_status = "PASS" if negative == 0 and zeros == 0 else "WARN"
    checks.append(_check(
        "DQ-05", "Units, signs and plausible ranges", range_status, "WARNING",
        negative + zeros,
        {"negative_values": negative, "zero_values": zeros,
         "month_over_month_changes_above_50_percent": extreme_changes,
         "note": "Extreme changes are review candidates, not automatic errors."},
    ))

    weather_geos = set(weather["geo"].unique())
    hicp_geos = set(hicp["geo"].unique())
    last_weather = weather.groupby("geo")["date"].max().dt.strftime("%Y-%m-%d").to_dict()
    latest_target_by_geo = target.groupby("geo")["time"].max().to_dict()
    aligned = weather_geos == expected_geos and hicp_geos == expected_geos
    asymmetric_target_freshness = len(set(latest_target_by_geo.values())) > 1
    if not aligned:
        freshness_status, affected = "FAIL", 1
    elif asymmetric_target_freshness:
        freshness_status, affected = "WARN", 1
    else:
        freshness_status, affected = "PASS", 0
    checks.append(_check(
        "DQ-06", "Cross-source alignment and freshness", freshness_status,
        "WARNING" if aligned else "ERROR", affected,
        {"weather_geos": sorted(weather_geos), "hicp_geos": sorted(hicp_geos),
         "latest_weather_date": last_weather,
         "latest_target_period_by_geo": latest_target_by_geo,
         "latest_hicp_period": str(hicp["time"].max()), "cutoff_day": cutoff_day},
    ))
    return checks
