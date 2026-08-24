import pandas as pd

from energy_observatory.features import build_model_frame, monthly_weather_features


def test_weather_features_stop_at_cutoff():
    weather = pd.DataFrame({
        "geo": ["FR"] * 3,
        "date": pd.to_datetime(["2024-01-19", "2024-01-20", "2024-01-21"]),
        "temperature_2m_mean": [10.0, 20.0, -20.0],
    })
    result = monthly_weather_features(weather, cutoff_day=20, temperature_base_c=18.0)
    assert result.iloc[0]["weather_days"] == 2
    assert result.iloc[0]["hdd_partial"] == 8.0
    assert result.iloc[0]["cdd_partial"] == 2.0
    assert pd.Timestamp(result.iloc[0]["effective_weather_cutoff"]).day == 20


def test_target_lags_are_country_specific():
    target = pd.DataFrame({
        "geo": ["DE"] * 13 + ["FR"] * 13,
        "time": [str(value) for value in pd.period_range("2023-01", periods=13, freq="M")] * 2,
        "value": list(range(13)) + list(range(100, 113)),
    })
    weather = pd.DataFrame({
        "geo": [geo for geo in ["DE", "FR"] for _ in range(13)],
        "period": list(pd.period_range("2023-01", periods=13, freq="M")) * 2,
        "hdd_partial": 1.0, "cdd_partial": 2.0, "temperature_mean_partial": 15.0,
        "weather_days": 20, "effective_weather_cutoff": pd.Timestamp("2024-01-20"),
        "weather_coverage": 1.0,
    })
    frame = build_model_frame(target, weather)
    france_last = frame[(frame["geo"] == "FR") & (frame["period"] == pd.Period("2024-01"))].iloc[0]
    assert france_last["lag3"] == 109
    assert france_last["lag12"] == 100

