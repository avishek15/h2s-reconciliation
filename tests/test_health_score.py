from types import SimpleNamespace

from core.health_score import analyze_transactions, calculate_health_score, get_status
from db.seed_data import get_seed_transactions


def _wrap(rows):
    return [SimpleNamespace(**row) for row in rows]


def test_empty_batch_returns_no_data():
    report = analyze_transactions([])

    assert report["score"] == 0
    assert report["status"] == "No Data"
    assert report["transaction_count"] == 0
    assert report["metrics"]["total_income"] == 0.0
    assert report["metrics"]["total_expenses"] == 0.0


def test_seed_batch_produces_bounded_score_and_breakdown():
    txns = _wrap(get_seed_transactions())
    report = calculate_health_score(txns)

    assert report["transaction_count"] == len(txns)
    assert 0 <= report["score"] <= 100
    assert report["status"] in {"Excellent", "Good", "Average", "Poor", "No Data"}
    assert set(report["subscores"].keys()) == {
        "cash_flow",
        "spending_discipline",
        "income_stability",
        "recurring_pressure",
    }
    assert report["recommendations"]
    assert report["drivers"]
    assert report["date_range"]["from"] is not None


def test_status_thresholds_are_stable():
    assert get_status(90) == "Excellent"
    assert get_status(75) == "Good"
    assert get_status(55) == "Average"
    assert get_status(12) == "Poor"
    assert get_status(0, has_data=False) == "No Data"
