# Model card

## Intended use

Demonstrate a transparent, reproducible pseudo-real-time nowcasting workflow for official energy statistics.

## Out-of-scope use

Operational dispatch, trading, tariff setting, official-statistics replacement, or causal inference.

## Target and features

- Target: Eurostat monthly electricity available to the internal market, GWh.
- Features: country, month sine/cosine, target lags 3 and 12, partial-month HDD/CDD, mean temperature, observed-day count and coverage.
- Explicit exclusion: HICP.

## Evaluation

Expanding rolling origin; three-month release lag; day-20 weather cutoff. Aggregate candidate MAE: **1,618.9 GWh**. Baseline MAE: **1,607.2 GWh**. H2: **NOT_SUPPORTED**.

## Uncertainty

Nominal 80% intervals use prior admissible out-of-origin absolute errors. Coverage and interval width are reported rather than assumed.

## Known limitations

Pseudo-real-time rather than exact vintage reconstruction; urban weather proxies; two-country scope; simple linear model; future revisions not yet observed.

## Maintenance

Every run stores source hashes and can compare a new snapshot with its predecessor. Model claims must be refreshed when data or code changes.
