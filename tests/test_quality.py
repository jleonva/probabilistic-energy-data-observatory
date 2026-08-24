import pandas as pd

from energy_observatory.quality import run_quality_checks


def test_six_quality_checks_pass_on_clean_fixture():
    periods = ["2024-01", "2024-02"]
    target = pd.DataFrame([
        {"freq": "M", "unit": "GWH", "nrg_bal": "AIM", "siec": "E7000", "geo": geo,
         "time": period, "value": value, "observation_flag": None}
        for geo in ["FR", "DE"] for period, value in zip(periods, [100.0, 110.0])
    ])
    hicp = pd.DataFrame({"geo": ["FR", "DE"], "time": ["2024-02"] * 2, "value": [100.0, 101.0]})
    weather = pd.DataFrame({
        "geo": ["FR", "DE"], "date": pd.to_datetime(["2024-02-20"] * 2),
        "temperature_2m_mean": [10.0, 9.0],
    })
    checks = run_quality_checks(target, hicp, weather, {"FR", "DE"}, 20)
    assert len(checks) == 6
    assert all(item["status"] == "PASS" for item in checks)

