from __future__ import annotations

import html
from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go


COUNTRY_NAMES = {"FR": "France", "DE": "Germany"}
COLORS = {"FR": "#0055A4", "DE": "#DD0000"}


def _fmt(value: Any, decimals: int = 1) -> str:
    if value is None or pd.isna(value):
        return "n/a"
    return f"{float(value):,.{decimals}f}"


def _figure_html(figure: go.Figure, include_js: bool = False) -> str:
    figure.update_layout(
        template="plotly_white", margin=dict(l=45, r=25, t=55, b=45),
        font=dict(family="Arial, sans-serif", color="#152238"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    return figure.to_html(
        full_html=False, include_plotlyjs="inline" if include_js else False,
        config={"displaylogo": False, "responsive": True},
    )


def build_dashboard(
    path: Path,
    target: pd.DataFrame,
    hicp: pd.DataFrame,
    predictions: pd.DataFrame,
    metrics: pd.DataFrame,
    current: pd.DataFrame,
    quality: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
    source_probe: dict[str, Any],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    history = target.copy()
    history["country"] = history["geo"].map(COUNTRY_NAMES)
    history["date"] = pd.to_datetime(history["time"])
    fig_history = px.line(
        history, x="date", y="value", color="country",
        color_discrete_map={"France": COLORS["FR"], "Germany": COLORS["DE"]},
        labels={"value": "Electricity available to internal market (GWh)", "date": "Month", "country": "Country"},
        title="Official monthly electricity availability",
    )

    season = history.assign(month=history["date"].dt.month).groupby(["country", "month"], as_index=False)["value"].mean()
    fig_season = px.line(
        season, x="month", y="value", color="country", markers=True,
        color_discrete_map={"France": COLORS["FR"], "Germany": COLORS["DE"]},
        labels={"value": "Average GWh", "month": "Month", "country": "Country"},
        title="Average seasonal profile",
    )

    price = hicp.copy()
    price["country"] = price["geo"].map(COUNTRY_NAMES)
    price["date"] = pd.to_datetime(price["time"])
    fig_price = px.line(
        price, x="date", y="value", color="country",
        color_discrete_map={"France": COLORS["FR"], "Germany": COLORS["DE"]},
        labels={"value": "Consumer electricity price index (2025=100)", "date": "Month", "country": "Country"},
        title="Consumer electricity price index — context only",
    )

    plot_predictions = predictions.copy()
    plot_predictions["date"] = plot_predictions["period"].astype(str).map(pd.Timestamp)
    plot_predictions["country"] = plot_predictions["geo"].map(COUNTRY_NAMES)
    fig_validation = go.Figure()
    for geo, group in plot_predictions.groupby("geo"):
        group = group.sort_values("date")
        fig_validation.add_trace(go.Scatter(
            x=group["date"], y=group["actual"], name=f"{COUNTRY_NAMES[geo]} actual",
            line=dict(color=COLORS[geo], width=2.5),
        ))
        fig_validation.add_trace(go.Scatter(
            x=group["date"], y=group["candidate"], name=f"{COUNTRY_NAMES[geo]} nowcast",
            line=dict(color=COLORS[geo], dash="dot"),
        ))
    fig_validation.update_layout(title="Pseudo-real-time rolling-origin validation", yaxis_title="GWh", xaxis_title="Month")

    metric_plot = metrics[metrics["geo"] == "ALL"].copy()
    fig_metrics = px.bar(
        metric_plot, x="model", y="mae", color="model", text_auto=".0f",
        color_discrete_map={"baseline": "#8294A6", "candidate": "#00876C"},
        labels={"mae": "Aggregate MAE (GWh)", "model": "Model"}, title="Primary metric",
    )

    current_cards = "".join(
        f"<div class='card'><h3>{COUNTRY_NAMES.get(row.geo, row.geo)}</h3>"
        f"<div class='big'>{_fmt(row.point_estimate_gwh, 0)} GWh</div>"
        f"<p>80% interval: {_fmt(row.lower_80_gwh, 0)}–{_fmt(row.upper_80_gwh, 0)} GWh</p>"
        f"<p>Weather through {html.escape(str(pd.Timestamp(row.effective_weather_cutoff).date()))}</p></div>"
        for row in current.itertuples()
    ) or "<div class='card'><h3>Current nowcast</h3><p>Blocked: insufficient admissible data.</p></div>"

    quality_rows = "".join(
        f"<tr><td>{q['check_id']}</td><td>{html.escape(q['check_name'])}</td>"
        f"<td><span class='status {q['status'].lower()}'>{q['status']}</span></td>"
        f"<td>{q['affected_rows']}</td></tr>" for q in quality
    )
    hypothesis_rows = "".join(
        f"<tr><td>{h['hypothesis_id']}</td><td>{html.escape(h['claim'])}</td>"
        f"<td><span class='status {h['status'].lower()}'>{h['status']}</span></td></tr>"
        for h in hypotheses
    )
    latest_target_by_geo = target.groupby("geo")["time"].max().to_dict()
    latest_target = " / ".join(f"{geo} {period}" for geo, period in sorted(latest_target_by_geo.items()))
    latest_hicp = str(hicp["time"].max())
    updated = source_probe["electricity"]["updated"]
    css = """
    :root{--ink:#152238;--muted:#5d6b7a;--paper:#f5f7fa;--line:#dce3ea;--blue:#0b5cab}
    *{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:Arial,sans-serif}
    header{background:linear-gradient(125deg,#082f49,#0b5cab);color:white;padding:42px max(24px,calc((100vw - 1180px)/2))}
    header h1{margin:0 0 10px;font-size:clamp(2rem,4vw,3.5rem)}header p{max-width:850px;line-height:1.55}
    main{max-width:1180px;margin:0 auto;padding:28px 20px 60px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}
    .panel,.card{background:white;border:1px solid var(--line);border-radius:14px;box-shadow:0 5px 18px rgba(20,40,70,.06)}
    .panel{padding:18px;margin-bottom:20px}.cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin:20px 0}
    .card{padding:18px}.card h3{margin:0 0 9px;font-size:1rem;color:var(--muted)}.big{font-size:1.65rem;font-weight:700}
    table{border-collapse:collapse;width:100%}th,td{text-align:left;border-bottom:1px solid var(--line);padding:10px 8px;vertical-align:top}
    .status{font-weight:700;font-size:.8rem;padding:4px 8px;border-radius:999px}.pass,.supported{background:#d7f3e8;color:#006644}
    .warn,.mixed,.not_tested{background:#fff0c2;color:#704d00}.fail,.not_supported,.blocked{background:#ffe0e0;color:#8a1c1c}
    .note{border-left:4px solid var(--blue);padding:10px 15px;background:#edf6ff;line-height:1.5}.muted{color:var(--muted)}
    @media(max-width:850px){.grid,.cards{grid-template-columns:1fr}}
    """
    dashboard = f"""<!doctype html><html lang='en'><head><meta charset='utf-8'>
    <meta name='viewport' content='width=device-width,initial-scale=1'><title>Probabilistic Energy Data Observatory</title>
    <style>{css}</style></head><body><header><h1>Probabilistic Energy Data Observatory</h1>
    <p>Experimental pseudo-real-time nowcasting of official monthly electricity availability in France and Germany, with publication-safe lags, partial-month weather proxies and explicit uncertainty.</p></header><main>
    <div class='note'><strong>Estimand:</strong> Eurostat electricity available to the internal market (E7000 / AIM / GWH). This is not wholesale price and is not automatically equivalent to electricity demand.</div>
    <div class='cards'><div class='card'><h3>Countries</h3><div class='big'>2</div><p>France and Germany</p></div>
    <div class='card'><h3>Latest official target</h3><div class='big'>{latest_target}</div><p>Eurostat update {html.escape(updated)}</p></div>
    <div class='card'><h3>Price context</h3><div class='big'>{latest_hicp}</div><p>HICP, 2025=100</p></div>{current_cards}</div>
    <div class='grid'><section class='panel'>{_figure_html(fig_history, True)}</section><section class='panel'>{_figure_html(fig_season)}</section></div>
    <div class='grid'><section class='panel'>{_figure_html(fig_price)}</section><section class='panel'>{_figure_html(fig_metrics)}</section></div>
    <section class='panel'>{_figure_html(fig_validation)}</section>
    <div class='grid'><section class='panel'><h2>Data quality</h2><table><thead><tr><th>ID</th><th>Check</th><th>Status</th><th>Affected</th></tr></thead><tbody>{quality_rows}</tbody></table></section>
    <section class='panel'><h2>Hypotheses</h2><table><thead><tr><th>ID</th><th>Pre-registered claim</th><th>Status</th></tr></thead><tbody>{hypothesis_rows}</tbody></table></section></div>
    <section class='panel'><h2>Limitations</h2><ul><li>Paris and Berlin are urban weather proxies, not national temperature aggregates.</li><li>The historical exercise is pseudo-real-time: exact source vintages are unavailable.</li><li>A conservative three-month publication lag is assumed.</li><li>HICP is contextual and excluded from model features.</li><li>Revision tracking begins with locally stored snapshots.</li></ul></section>
    <p class='muted'>Generated locally. NOT PUSHED / NOT PUBLISHED.</p></main></body></html>"""
    path.write_text(dashboard, encoding="utf-8")


def write_documentation(
    root: Path,
    target: pd.DataFrame,
    metrics: pd.DataFrame,
    current: pd.DataFrame,
    quality: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
    revision_summary: dict[str, Any],
) -> None:
    all_metrics = metrics[metrics["geo"] == "ALL"].set_index("model")
    baseline_mae = all_metrics.loc["baseline", "mae"]
    candidate_mae = all_metrics.loc["candidate", "mae"]
    h2 = next(item for item in hypotheses if item["hypothesis_id"] == "H2")
    checks_passed = sum(item["status"] == "PASS" for item in quality)
    coverage_by_geo = {
        geo: {"first": group["time"].min(), "last": group["time"].max(), "rows": len(group)}
        for geo, group in target.groupby("geo")
    }
    coverage_text = ", ".join(
        f"{COUNTRY_NAMES.get(geo, geo)} {values['first']}–{values['last']} ({values['rows']} observations)"
        for geo, values in sorted(coverage_by_geo.items())
    )
    readme = f"""# Probabilistic Energy Data Observatory

An evidence-first MVP for **pseudo-real-time nowcasting** of Eurostat monthly electricity availability in France and Germany.

## What it estimates

The target is Eurostat **electricity available to the internal market** (`nrg_cb_em`, `E7000`, `AIM`, `GWH`). It is not labelled as demand, load or wholesale price. Verified coverage: **{coverage_text}**.

## Current evidence

- Seasonal-naive aggregate MAE: **{baseline_mae:,.1f} GWh**.
- Weather-adjusted Ridge aggregate MAE: **{candidate_mae:,.1f} GWh**.
- H2 status: **{h2['status']}** under the pre-registered rule.
- Data-quality checks passed: **{checks_passed}/6**.
- Revision tracking: **{revision_summary['status']}**.

The candidate is not declared better unless the rolling-origin results support that claim. HICP is shown as context and is excluded from model features.

## Architecture

```mermaid
flowchart LR
  E[Eurostat API] --> S[Immutable snapshots]
  W[Open-Meteo] --> S
  S --> Q[Six quality checks]
  S --> DB[(SQLite)]
  Q --> F[Cutoff-safe features]
  DB --> F
  F --> M[Seasonal baseline + Ridge]
  M --> V[Rolling-origin evaluation]
  V --> A[Artifacts + interactive HTML]
```

## Reproduce on PowerShell

```powershell
.\\.venv\\Scripts\\python.exe -m pip install -e .[dev]
.\\.venv\\Scripts\\python.exe -m pytest
.\\.venv\\Scripts\\python.exe -m energy_observatory.cli run
```

Open `docs/index.html` directly in a browser. It is self-contained and makes no API calls while viewed.

## Repository map

- `src/energy_observatory/`: ingestion, SQL, quality, features, model and reporting.
- `data/snapshots/`: timestamped source responses used by the run.
- `artifacts/`: machine-readable evidence and model outputs.
- `docs/index.html`: interactive recruiter-facing dashboard.
- `docs/technical_report.md`: assumptions, methods and results.
- `docs/model_card.md`: intended use and limitations.
- `tests/`: network-free regression and leakage checks.

## Limitations

- Paris and Berlin are weather proxies, not national aggregates.
- Exact historical source vintages are unavailable; evaluation is pseudo-real-time.
- A three-month publication lag is assumed conservatively.
- H1 (vintage-safe HICP as a model feature) is not tested.
- First-run revision status cannot show historical changes.

**Work completed locally on branch `codex/mvp`. NOT PUSHED / NOT PUBLISHED.**
"""
    (root / "README.md").write_text(readme, encoding="utf-8")

    quality_lines = "\n".join(f"- **{q['check_id']} {q['check_name']}** — {q['status']}" for q in quality)
    nowcast_lines = "\n".join(
        f"- {COUNTRY_NAMES.get(row.geo, row.geo)}: {row.point_estimate_gwh:,.0f} GWh "
        f"(80% interval {_fmt(row.lower_80_gwh, 0)}–{_fmt(row.upper_80_gwh, 0)} GWh)."
        for row in current.itertuples()
    ) or "- Current nowcast blocked because admissible inputs were insufficient."
    report = f"""# Technical report

## Executive summary — CURRENT OUTPUT

This MVP estimates Eurostat monthly electricity availability for France and Germany before official release. The weather-adjusted candidate achieved an aggregate MAE of **{candidate_mae:,.1f} GWh**, versus **{baseline_mae:,.1f} GWh** for seasonal-naive. H2 is **{h2['status']}**. This is descriptive rolling-origin evidence, not a claim of causal weather effects or production readiness.

## Statistical question and estimand — IMPLEMENTED AND TESTED

The estimand is the final published monthly value of electricity available to the internal market (`E7000`, `AIM`, `GWH`). The implementation validates codes and labels from Eurostat before modelling.

## Sources and provenance — IMPLEMENTED AND TESTED

- Eurostat `nrg_cb_em`: official monthly target.
- Eurostat `prc_hicp_minr`, `CP0451`, `I25`: consumer electricity price index, context only.
- Open-Meteo archive API: Paris and Berlin daily temperature proxies.
- Each response is stored as an immutable timestamped snapshot with SHA-256 provenance and a SQL ingestion record.

## Data quality — CURRENT OUTPUT

{quality_lines}

## Availability assumptions — ASSUMPTION

The exercise uses a day-20 weather cutoff and a conservative three-month official-release lag. Training targets for month `t` stop at `t-3`. Exact historical Eurostat and weather vintages are not reconstructed, so the evaluation is labelled pseudo-real-time.

## Models and uncertainty — IMPLEMENTED AND TESTED

The baseline uses the same month one year earlier. The pooled candidate is Ridge regression with country, seasonal encodings, lags 3 and 12, and partial-month HDD/CDD. The 80% interval uses prior rolling-origin absolute errors that would be observable under the same release-lag assumption.

## Current nowcast — CURRENT OUTPUT

{nowcast_lines}

## Hypotheses

- **H1 — NOT TESTED:** a release-safe HICP feature may improve nowcasts. Vintage availability was not reconstructed, so HICP is excluded.
- **H2 — {h2['status']}:** weather-adjusted Ridge versus seasonal-naive, judged on aggregate and country MAE under the pre-registered rule.

## Revisions — CURRENT OUTPUT

Status: **{revision_summary['status']}**. Revision tracking begins with snapshots created by this project; it does not reconstruct historical versions retroactively.

## Limitations and future work

- Replace capital-city proxies with population-weighted national weather.
- Reconstruct source-release calendars and vintages before using HICP predictively.
- Accumulate snapshots to measure real revisions.
- Test broader models only after fixing an untouched evaluation period.

## Reproducibility

Run tests, then `python -m energy_observatory.cli run`. Machine-readable configuration, metrics, predictions, checks and provenance are under `config/` and `artifacts/`.
"""
    (root / "docs" / "technical_report.md").write_text(report, encoding="utf-8")

    model_card = f"""# Model card

## Intended use

Demonstrate a transparent, reproducible pseudo-real-time nowcasting workflow for official energy statistics.

## Out-of-scope use

Operational dispatch, trading, tariff setting, official-statistics replacement, or causal inference.

## Target and features

- Target: Eurostat monthly electricity available to the internal market, GWh.
- Features: country, month sine/cosine, target lags 3 and 12, partial-month HDD/CDD, mean temperature, observed-day count and coverage.
- Explicit exclusion: HICP.

## Evaluation

Expanding rolling origin; three-month release lag; day-20 weather cutoff. Aggregate candidate MAE: **{candidate_mae:,.1f} GWh**. Baseline MAE: **{baseline_mae:,.1f} GWh**. H2: **{h2['status']}**.

## Uncertainty

Nominal 80% intervals use prior admissible out-of-origin absolute errors. Coverage and interval width are reported rather than assumed.

## Known limitations

Pseudo-real-time rather than exact vintage reconstruction; urban weather proxies; two-country scope; simple linear model; future revisions not yet observed.

## Maintenance

Every run stores source hashes and can compare a new snapshot with its predecessor. Model claims must be refreshed when data or code changes.
"""
    (root / "docs" / "model_card.md").write_text(model_card, encoding="utf-8")
