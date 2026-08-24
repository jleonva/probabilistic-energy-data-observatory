import numpy as np
import pandas as pd

from energy_observatory.modeling import MODEL_FEATURES, calculate_metrics, rolling_origin_evaluation


def _model_frame() -> pd.DataFrame:
    rows = []
    periods = pd.period_range("2010-01", periods=96, freq="M")
    for geo, offset in [("DE", 1000), ("FR", 1200)]:
        values = [offset + 100 * np.sin(2 * np.pi * p.month / 12) + i for i, p in enumerate(periods)]
        for i, (period, target) in enumerate(zip(periods, values)):
            rows.append({
                "geo": geo, "period": period, "target": target,
                "lag3": values[i - 3] if i >= 3 else np.nan,
                "lag12": values[i - 12] if i >= 12 else np.nan,
                "month_sin": np.sin(2 * np.pi * period.month / 12),
                "month_cos": np.cos(2 * np.pi * period.month / 12),
                "hdd_partial": max(0, 18 - 10 - period.month / 10),
                "cdd_partial": max(0, period.month - 8),
                "temperature_mean_partial": 10 + period.month,
                "weather_days": 20, "weather_coverage": 1.0,
            })
    return pd.DataFrame(rows)


def test_rolling_origin_obeys_release_lag():
    predictions = rolling_origin_evaluation(_model_frame(), 3, 24, 0.8)
    assert not predictions.empty
    assert all(row.last_target_available == row.period - 3 for row in predictions.itertuples())
    assert "hicp" not in MODEL_FEATURES


def test_metrics_compare_identical_origins():
    predictions = rolling_origin_evaluation(_model_frame(), 3, 24, 0.8)
    metrics = calculate_metrics(predictions, 0.8)
    origins = metrics[metrics["geo"] == "ALL"].set_index("model")["origins"]
    assert origins["baseline"] == origins["candidate"]

