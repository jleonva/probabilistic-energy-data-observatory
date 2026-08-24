from energy_observatory.sources.eurostat import parse_jsonstat


def test_parse_jsonstat_respects_dimension_order():
    payload = {
        "id": ["geo", "time"], "size": [2, 2],
        "dimension": {
            "geo": {"category": {"index": {"DE": 0, "FR": 1}, "label": {"DE": "Germany", "FR": "France"}}},
            "time": {"category": {"index": {"2024-01": 0, "2024-02": 1}, "label": {}}},
        },
        "value": {"0": 10, "1": 11, "2": 20, "3": 21}, "status": {"3": "p"},
    }
    frame = parse_jsonstat(payload)
    assert frame[["geo", "time", "value"]].to_dict("records") == [
        {"geo": "DE", "time": "2024-01", "value": 10.0},
        {"geo": "DE", "time": "2024-02", "value": 11.0},
        {"geo": "FR", "time": "2024-01", "value": 20.0},
        {"geo": "FR", "time": "2024-02", "value": 21.0},
    ]
    assert frame.iloc[-1]["observation_flag"] == "p"

