from pathlib import Path


def test_dashboard_contract_is_self_contained_in_source():
    source = (Path(__file__).parents[1] / "src" / "energy_observatory" / "reporting.py").read_text(encoding="utf-8")
    assert 'include_plotlyjs="inline"' in source
    assert "NOT PUSHED / NOT PUBLISHED" in source
    assert "Streamlit" not in source

