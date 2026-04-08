from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from core.database import _iso
from statistics import mean, pstdev
from typing import Any, Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import AsyncSessionLocal, Transaction, UploadBatch


NO_DATA_STATUS = "No Data"
EXCELLENT_STATUS = "Excellent"
GOOD_STATUS = "Good"
AVERAGE_STATUS = "Average"
POOR_STATUS = "Poor"


def _round2(value: float) -> float:
    return round(float(value), 2)


def _safe_parse_date(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d")
    except ValueError:
        return None


def _normalize_category(value: Any) -> str:
    if not value:
        return "Uncategorized"
    text = str(value).strip()
    if not text:
        return "Uncategorized"
    lowered = text.lower()
    aliases = {
        "income": "Income",
        "dining": "Dining",
        "subscriptions": "Subscriptions",
        "shopping": "Shopping",
        "groceries": "Groceries",
        "transport": "Transport",
        "utilities": "Utilities",
        "housing": "Housing",
        "health": "Health",
        "cash": "Cash",
        "entertainment": "Entertainment",
    }
    return aliases.get(lowered, text[:1].upper() + text[1:])


def _is_income(txn: Any, category: str, amount: float) -> bool:
    txn_type = str(getattr(txn, "transaction_type", "") or "").lower()
    return amount > 0 or txn_type == "credit" or category.lower() == "income"


def _clamp(value: float, minimum: int, maximum: int) -> int:
    return max(minimum, min(maximum, int(round(value))))


def _score_cash_flow(total_income: float, total_expenses: float) -> tuple[int, str]:
    if total_income <= 0:
        return 0, "No measurable income"

    net = total_income - total_expenses
    savings_rate = net / total_income

    if net < 0:
        return 0, f"Spending exceeded income by ${_round2(abs(net))}"
    if savings_rate >= 0.35:
        return 35, f"Strong surplus of ${_round2(net)}"
    if savings_rate >= 0.20:
        return 30, f"Healthy savings rate of {round(savings_rate * 100, 1)}%"
    if savings_rate >= 0.10:
        return 24, f"Positive cash flow with {round(savings_rate * 100, 1)}% savings"
    if savings_rate >= 0.05:
        return 16, f"Thin surplus of ${_round2(net)}"
    return 8, f"Small surplus of ${_round2(net)}"


def _score_spending_discipline(
    category_totals: dict[str, float],
    total_income: float,
    total_expenses: float,
) -> tuple[int, str, list[str], list[str]]:
    if total_income <= 0:
        return 0, "No income baseline", [], []

    score = 30
    positives: list[str] = []
    negatives: list[str] = []

    def share(category: str) -> float:
        return category_totals.get(category, 0.0) / total_income if total_income > 0 else 0.0

    dining_share = share("Dining")
    subs_share = share("Subscriptions")
    shopping_share = share("Shopping")
    housing_share = share("Housing")
    transport_share = share("Transport")
    utilities_share = share("Utilities")

    if dining_share > 0.40:
        score -= 12
        negatives.append(f"Dining uses {round(dining_share * 100, 1)}% of income")
    elif dining_share > 0.25:
        score -= 8
        negatives.append(f"Dining uses {round(dining_share * 100, 1)}% of income")
    elif dining_share > 0.15:
        score -= 4
        negatives.append(f"Dining is elevated at {round(dining_share * 100, 1)}% of income")
    else:
        positives.append("Dining spend is controlled")

    if subs_share > 0.12:
        score -= 9
        negatives.append(f"Subscriptions use {round(subs_share * 100, 1)}% of income")
    elif subs_share > 0.07:
        score -= 5
        negatives.append(f"Subscriptions use {round(subs_share * 100, 1)}% of income")
    else:
        positives.append("Subscriptions are under control")

    if shopping_share > 0.25:
        score -= 10
        negatives.append(f"Shopping uses {round(shopping_share * 100, 1)}% of income")
    elif shopping_share > 0.15:
        score -= 6
        negatives.append(f"Shopping uses {round(shopping_share * 100, 1)}% of income")
    else:
        positives.append("Shopping pressure looks manageable")

    if housing_share > 0.45:
        score -= 8
        negatives.append(f"Housing consumes {round(housing_share * 100, 1)}% of income")
    elif housing_share > 0.35:
        score -= 4
        negatives.append(f"Housing is high at {round(housing_share * 100, 1)}% of income")
    else:
        positives.append("Housing stays within a workable range")

    if transport_share > 0.20:
        score -= 3
        negatives.append(f"Transport uses {round(transport_share * 100, 1)}% of income")
    elif transport_share < 0.08 and category_totals.get("Transport", 0) > 0:
        score += 1
        positives.append("Transport spend is efficient")

    if utilities_share < 0.08 and category_totals.get("Utilities", 0) > 0:
        score += 1
        positives.append("Utilities are well contained")

    if category_totals.get("Groceries", 0) > category_totals.get("Dining", 0):
        score += 2
        positives.append("Groceries outrun discretionary dining")

    return _clamp(score, 0, 30), "Spending pattern scored", positives[:3], negatives[:3]


def _score_income_stability(monthly_income: dict[str, float], total_income: float) -> tuple[int, str]:
    if total_income <= 0 or not monthly_income:
        return 0, "No income stream to evaluate"

    incomes = list(monthly_income.values())
    if len(incomes) == 1:
        return 6, "Only one income month detected"
    if len(incomes) == 2:
        return 10, "Two income months detected"

    avg_income = mean(incomes)
    if avg_income <= 0:
        return 0, "Income data is not usable"

    volatility = pstdev(incomes) / avg_income if len(incomes) > 1 else 0.0
    if volatility <= 0.05:
        return 20, "Income is very stable month to month"
    if volatility <= 0.15:
        return 16, "Income is reasonably stable"
    if volatility <= 0.30:
        return 11, "Income shows moderate volatility"
    return 6, "Income is volatile"


def _score_recurring_pressure(
    category_totals: dict[str, float],
    total_income: float,
) -> tuple[int, str]:
    if total_income <= 0:
        return 0, "No income baseline"

    score = 15
    recurring_total = (
        category_totals.get("Subscriptions", 0.0)
        + category_totals.get("Housing", 0.0)
        + category_totals.get("Utilities", 0.0)
    )
    recurring_share = recurring_total / total_income
    subs_share = category_totals.get("Subscriptions", 0.0) / total_income
    housing_share = category_totals.get("Housing", 0.0) / total_income

    if recurring_share > 0.70:
        score -= 8
    elif recurring_share > 0.55:
        score -= 5
    elif recurring_share > 0.40:
        score -= 2

    if subs_share > 0.12:
        score -= 3
    elif subs_share < 0.05 and category_totals.get("Subscriptions", 0.0) > 0:
        score += 1

    if housing_share > 0.45:
        score -= 3
    elif housing_share < 0.25 and category_totals.get("Housing", 0.0) > 0:
        score += 1

    return _clamp(score, 0, 15), "Recurring burden scored"


def _build_drivers(
    *,
    cash_flow_detail: str,
    spending_positive: list[str],
    spending_negative: list[str],
    income_detail: str,
    recurring_detail: str,
    total_income: float,
    total_expenses: float,
    category_totals: dict[str, float],
) -> list[dict[str, Any]]:
    net = total_income - total_expenses
    savings_rate = (net / total_income * 100) if total_income > 0 else 0.0
    drivers: list[dict[str, Any]] = []

    if net >= 0:
        drivers.append(
            {
                "label": "Positive cash flow",
                "impact": 12 if savings_rate >= 10 else 8,
                "detail": cash_flow_detail,
            }
        )
    else:
        drivers.append(
            {
                "label": "Negative cash flow",
                "impact": -15,
                "detail": cash_flow_detail,
            }
        )

    for item in spending_positive[:2]:
        drivers.append({"label": "Spending strength", "impact": 4, "detail": item})
    for item in spending_negative[:3]:
        impact = -6 if "Dining" in item or "Shopping" in item else -4
        drivers.append({"label": "Spending pressure", "impact": impact, "detail": item})

    drivers.append(
        {
            "label": "Income stability",
            "impact": 8 if "stable" in income_detail.lower() else 4 if total_income > 0 else 0,
            "detail": income_detail,
        }
    )
    drivers.append(
        {
            "label": "Recurring commitments",
            "impact": 5 if "manageable" in recurring_detail.lower() else -4,
            "detail": recurring_detail,
        }
    )

    return sorted(drivers, key=lambda d: abs(int(d["impact"])), reverse=True)[:5]


def _build_recommendations(
    *,
    category_totals: dict[str, float],
    total_income: float,
) -> list[str]:
    recommendations: list[str] = []

    if total_income <= 0:
        return ["No income detected, so the health score is not meaningful yet."]

    def share(category: str) -> float:
        return category_totals.get(category, 0.0) / total_income if total_income > 0 else 0.0

    if share("Dining") > 0.25:
        recommendations.append(
            f"Cap dining spend near 15% of income; it is currently {round(share('Dining') * 100, 1)}%."
        )
    if share("Subscriptions") > 0.08:
        recommendations.append(
            f"Review subscriptions worth about ${_round2(category_totals.get('Subscriptions', 0.0))}."
        )
    if share("Shopping") > 0.15:
        recommendations.append(
            f"Set a shopping ceiling below {round(share('Shopping') * 100, 1)}% of income."
        )
    if share("Housing") > 0.40:
        recommendations.append(
            f"Housing consumes {round(share('Housing') * 100, 1)}% of income; try to keep fixed costs lower."
        )
    if share("Dining") > 0 and category_totals.get("Groceries", 0.0) > category_totals.get("Dining", 0.0):
        recommendations.append("Keep leaning into groceries over dining to preserve cash flow.")
    if not recommendations:
        recommendations.append("Spending looks broadly balanced. Keep tracking the same mix.")

    return recommendations[:5]


def _build_summary(score: int, total_income: float, total_expenses: float, status: str) -> str:
    net = total_income - total_expenses
    if status == NO_DATA_STATUS:
        return "No transactions were available to score."
    if net >= 0:
        savings_rate = (net / total_income * 100) if total_income > 0 else 0.0
        return f"You generated a ${_round2(net)} surplus and saved {round(savings_rate, 1)}% of income."
    return f"Spending exceeded income by ${_round2(abs(net))}, so the health score is under pressure."


def analyze_transactions(transactions: Sequence[Any]) -> dict[str, Any]:
    txns = list(transactions)
    if not txns:
        return {
            "score": 0,
            "health_score": 0,
            "status": NO_DATA_STATUS,
            "health_status": NO_DATA_STATUS,
            "summary": "No transactions were available to score.",
            "subscores": {
                "cash_flow": {"score": 0, "max_score": 35, "detail": "No transaction data"},
                "spending_discipline": {"score": 0, "max_score": 30, "detail": "No transaction data"},
                "income_stability": {"score": 0, "max_score": 20, "detail": "No transaction data"},
                "recurring_pressure": {"score": 0, "max_score": 15, "detail": "No transaction data"},
            },
            "drivers": [],
            "recommendations": ["No transactions available for this batch."],
            "metrics": {
                "total_income": 0.0,
                "total_expenses": 0.0,
                "net_cash_flow": 0.0,
                "savings_rate_pct": 0.0,
                "expense_ratio_pct": 0.0,
                "largest_expense_category": None,
            },
            "transaction_count": 0,
            "date_range": {"from": None, "to": None},
            "category_totals": {},
            "income": 0.0,
            "expenses": 0.0,
        }

    total_income = 0.0
    total_expenses = 0.0
    category_totals: defaultdict[str, float] = defaultdict(float)
    monthly_income: defaultdict[str, float] = defaultdict(float)
    dates: list[datetime] = []

    for txn in txns:
        amount = float(getattr(txn, "amount", 0.0) or 0.0)
        category = _normalize_category(getattr(txn, "category", None))
        dt = _safe_parse_date(getattr(txn, "date", None))
        if dt:
            dates.append(dt)

        if _is_income(txn, category, amount):
            total_income += abs(amount)
            if dt:
                monthly_income[dt.strftime("%Y-%m")] += abs(amount)
        else:
            total_expenses += abs(amount)
            category_totals[category] += abs(amount)

    if total_income <= 0 and total_expenses <= 0:
        return analyze_transactions([])

    cash_flow_score, cash_flow_detail = _score_cash_flow(total_income, total_expenses)
    spending_score, spending_detail, spending_positive, spending_negative = _score_spending_discipline(
        dict(category_totals),
        total_income,
        total_expenses,
    )
    income_stability_score, income_detail = _score_income_stability(dict(monthly_income), total_income)
    recurring_score, recurring_detail = _score_recurring_pressure(dict(category_totals), total_income)

    score = _clamp(cash_flow_score + spending_score + income_stability_score + recurring_score, 0, 100)
    status = get_status(score)
    metrics = {
        "total_income": _round2(total_income),
        "total_expenses": _round2(total_expenses),
        "net_cash_flow": _round2(total_income - total_expenses),
        "savings_rate_pct": _round2(((total_income - total_expenses) / total_income * 100) if total_income > 0 else 0.0),
        "expense_ratio_pct": _round2((total_expenses / total_income * 100) if total_income > 0 else 0.0),
        "largest_expense_category": max(category_totals.items(), key=lambda item: item[1])[0] if category_totals else None,
    }
    recommendations = _build_recommendations(category_totals=dict(category_totals), total_income=total_income)
    drivers = _build_drivers(
        cash_flow_detail=cash_flow_detail,
        spending_positive=spending_positive,
        spending_negative=spending_negative,
        income_detail=income_detail,
        recurring_detail=recurring_detail,
        total_income=total_income,
        total_expenses=total_expenses,
        category_totals=dict(category_totals),
    )

    date_values = sorted(dates)
    date_range = {
        "from": date_values[0].strftime("%Y-%m-%d") if date_values else None,
        "to": date_values[-1].strftime("%Y-%m-%d") if date_values else None,
    }

    return {
        "score": score,
        "health_score": score,
        "status": status,
        "health_status": status,
        "summary": _build_summary(score, total_income, total_expenses, status),
        "subscores": {
            "cash_flow": {"score": cash_flow_score, "max_score": 35, "detail": cash_flow_detail},
            "spending_discipline": {"score": spending_score, "max_score": 30, "detail": spending_detail},
            "income_stability": {"score": income_stability_score, "max_score": 20, "detail": income_detail},
            "recurring_pressure": {"score": recurring_score, "max_score": 15, "detail": recurring_detail},
        },
        "drivers": drivers,
        "recommendations": recommendations,
        "metrics": metrics,
        "transaction_count": len(txns),
        "date_range": date_range,
        "category_totals": {k: _round2(v) for k, v in category_totals.items()},
        "income": _round2(total_income),
        "expenses": _round2(total_expenses),
    }


async def get_batch_health_report(batch_id: str, db: Optional[AsyncSession] = None) -> dict[str, Any]:
    owns_db = db is None
    if owns_db:
        db = AsyncSessionLocal()

    try:
        batch_result = await db.execute(select(UploadBatch).where(UploadBatch.batch_id == batch_id))
        batch = batch_result.scalar_one_or_none()
        if not batch:
            raise ValueError(f"Batch {batch_id} not found")

        txn_result = await db.execute(
            select(Transaction)
            .where(Transaction.batch_id == batch_id)
            .order_by(Transaction.date.asc())
        )
        transactions = txn_result.scalars().all()

        report = analyze_transactions(transactions)
        report["batch_id"] = batch_id
        report["batch_status"] = batch.status
        report["batch_created_at"] = _iso(batch.created_at)
        report["batch_completed_at"] = _iso(batch.completed_at) if getattr(batch, "completed_at", None) else None
        return report
    finally:
        if owns_db and db:
            await db.close()


def calculate_health_score(transactions: Sequence[Any]) -> dict[str, Any]:
    return analyze_transactions(transactions)


def get_status(score: int, has_data: bool = True) -> str:
    if not has_data:
        return NO_DATA_STATUS
    if score >= 85:
        return EXCELLENT_STATUS
    if score >= 70:
        return GOOD_STATUS
    if score >= 50:
        return AVERAGE_STATUS
    return POOR_STATUS


def generate_insights(category_totals: dict[str, float], income: float) -> list[str]:
    if income <= 0:
        return ["No income detected"]

    insights: list[str] = []
    if category_totals.get("Dining", 0) > 0.25 * income:
        insights.append("Dining is taking too large a share of income")
    if category_totals.get("Subscriptions", 0) > 0.08 * income:
        insights.append("Recurring subscriptions are worth a review")
    if category_totals.get("Shopping", 0) > 0.15 * income:
        insights.append("Shopping is creating avoidable pressure")
    if category_totals.get("Housing", 0) > 0.40 * income:
        insights.append("Housing costs are high relative to income")
    if not insights:
        insights.append("Spending mix looks broadly balanced")
    return insights
