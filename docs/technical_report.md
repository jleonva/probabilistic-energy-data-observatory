# Technical report

## Executive summary — CURRENT OUTPUT

This MVP estimates Eurostat monthly electricity availability for France and Germany before official release. The weather-adjusted candidate achieved an aggregate MAE of **1,618.9 GWh**, versus **1,607.2 GWh** for seasonal-naive. H2 is **NOT_SUPPORTED**. This is descriptive rolling-origin evidence, not a claim of causal weather effects or production readiness.

## Statistical question and estimand — IMPLEMENTED AND TESTED

The estimand is the final published monthly value of electricity available to the internal market (`E7000`, `AIM`, `GWH`). The implementation validates codes and labels from Eurostat before modelling.

## Sources and provenance — IMPLEMENTED AND TESTED

- Eurostat `nrg_cb_em`: official monthly target.
- Eurostat `prc_hicp_minr`, `CP0451`, `I25`: consumer electricity price index, context only.
- Open-Meteo archive API: Paris and Berlin daily temperature proxies.
- Each response is stored as an immutable timestamped snapshot with SHA-256 provenance and a SQL ingestion record.

## Data quality — CURRENT OUTPUT

- **DQ-01 Schema and code validity** — PASS
- **DQ-02 Primary-key uniqueness** — PASS
- **DQ-03 Temporal continuity and coverage** — PASS
- **DQ-04 Missing values and observation flags** — PASS
- **DQ-05 Units, signs and plausible ranges** — PASS
- **DQ-06 Cross-source alignment and freshness** — WARN

## Availability assumptions — ASSUMPTION

The exercise uses a day-20 weather cutoff and a conservative three-month official-release lag. Training targets for month `t` stop at `t-3`. Exact historical Eurostat and weather vintages are not reconstructed, so the evaluation is labelled pseudo-real-time.

## Models and uncertainty — IMPLEMENTED AND TESTED

The baseline uses the same month one year earlier. The pooled candidate is Ridge regression with country, seasonal encodings, lags 3 and 12, and partial-month HDD/CDD. The 80% interval uses prior rolling-origin absolute errors that would be observable under the same release-lag assumption.

## Current nowcast — CURRENT OUTPUT

- Germany: 34,823 GWh (80% interval 32,091–37,556 GWh).
- France: 32,083 GWh (80% interval 29,350–34,816 GWh).

## Hypotheses

- **H1 — NOT TESTED:** a release-safe HICP feature may improve nowcasts. Vintage availability was not reconstructed, so HICP is excluded.
- **H2 — NOT_SUPPORTED:** weather-adjusted Ridge versus seasonal-naive, judged on aggregate and country MAE under the pre-registered rule.

## Revisions — CURRENT OUTPUT

Status: **COMPARED**. Revision tracking begins with snapshots created by this project; it does not reconstruct historical versions retroactively.

## Limitations and future work

- Replace capital-city proxies with population-weighted national weather.
- Reconstruct source-release calendars and vintages before using HICP predictively.
- Accumulate snapshots to measure real revisions.
- Test broader models only after fixing an untouched evaluation period.

## Reproducibility

Run tests, then `python -m energy_observatory.cli run`. Machine-readable configuration, metrics, predictions, checks and provenance are under `config/` and `artifacts/`.
