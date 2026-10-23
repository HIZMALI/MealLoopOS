from types import SimpleNamespace

import pytest
from app.metrics import chart_data, summarize
from app.parsing import parse_records


def test_aggregation_coverage_and_zero_diners(csv_data):
    rows, _ = parse_records(csv_data, "f.csv")
    records = [SimpleNamespace(**r) for r in rows]
    metrics = summarize(records)
    assert metrics["plate_waste_kg"] == 6
    assert metrics["kitchen_serving_waste_kg"] == 3
    assert metrics["combined_recorded_waste_kg"] == 9
    assert metrics["complete_waste_kg"] == 7
    assert metrics["average_daily_combined_kg"] == 3.5
    assert metrics["average_waste_per_diner_g"] == 30
    assert metrics["coverage"] == {"plate_days": 3, "kitchen_days": 2, "complete_days": 2, "per_diner_days": 1, "per_diner_diners": 100}
    charts = chart_data(records)
    assert charts["daily"][1]["combined_waste_kg"] is None
    assert charts["daily"][2]["waste_per_diner_g"] is None
    assert [m["menu"] for m in charts["menus"]] == [1, 2]


def test_diner_weighted_not_mean_of_ratios():
    records = [SimpleNamespace(plate_waste_kg=1, kitchen_serving_waste_kg=1, diners=10),
               SimpleNamespace(plate_waste_kg=1, kitchen_serving_waste_kg=1, diners=90)]
    assert summarize(records)["average_waste_per_diner_g"] == 40


def test_no_eligible_denominator_and_no_invented_kitchen_mass():
    record = SimpleNamespace(plate_waste_kg=1, kitchen_serving_waste_kg=None, diners=None)
    metrics = summarize([record])
    assert metrics["combined_recorded_waste_kg"] == 1
    assert metrics["kitchen_serving_waste_kg"] is None
    assert metrics["average_waste_per_diner_g"] is None
    assert metrics["average_daily_combined_kg"] is None


def test_empty_and_measured_zero():
    assert summarize([])["combined_recorded_waste_kg"] is None
    assert summarize([SimpleNamespace(plate_waste_kg=0, kitchen_serving_waste_kg=0, diners=10)])["average_waste_per_diner_g"] == 0


def test_gram_duplicate_is_not_extra_mass():
    rows, _ = parse_records(b"PW kg,PW g,KSW kg,DINERS\n1,1000,2,100\n", "f.csv")
    assert summarize([SimpleNamespace(**r) for r in rows])["combined_recorded_waste_kg"] == pytest.approx(3)
