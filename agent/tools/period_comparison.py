from collections import defaultdict
from datetime import datetime

from sqlalchemy import select

from core.database import AsyncSessionLocal, Transaction


async def get_period_comparison(batch_id: str, compare_months: int = 1) -> dict:
    """
    Compare current period spending against previous periods by category.

    Splits transactions into current and previous periods and computes
    percentage change in spending per category plus overall trend.

    Args:
        batch_id: The UUID of the upload batch to analyze.
        compare_months: Number of months to use as one period (default 1).

    Returns:
        A dictionary with current_period, previous_period totals, and
        category_changes showing percentage deltas.
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Transaction).where(Transaction.batch_id == batch_id)
            )
            transactions = result.scalars().all()

        if not transactions:
            return {"error": "No transactions found", "tool": "get_period_comparison"}

        # Parse dates and find midpoint
        dated = []
        for t in transactions:
            try:
                d = datetime.strptime(t.date, "%Y-%m-%d")
                dated.append((d, t))
            except ValueError:
                pass

        if not dated:
            return {"error": "No valid dates", "tool": "get_period_comparison"}

        dated.sort(key=lambda x: x[0])
        all_dates = [d for d, _ in dated]
        min_date, max_date = all_dates[0], all_dates[-1]
        total_days = (max_date - min_date).days

        if total_days < 2:
            return {"error": "Not enough date range for comparison", "tool": "get_period_comparison"}

        midpoint = min_date + (max_date - min_date) / 2

        # Split into two halves
        current_txns = [(d, t) for d, t in dated if d >= midpoint]
        previous_txns = [(d, t) for d, t in dated if d < midpoint]

        def aggregate(txn_list):
            totals: dict[str, float] = defaultdict(float)
            income = 0.0
            for _, t in txn_list:
                if t.amount < 0:
                    cat = t.category or "Uncategorized"
                    totals[cat] += abs(t.amount)
                else:
                    income += t.amount
            return totals, income

        curr_cats, curr_income = aggregate(current_txns)
        prev_cats, prev_income = aggregate(previous_txns)

        curr_total = sum(curr_cats.values())
        prev_total = sum(prev_cats.values())

        # Category-level changes
        all_cats = set(curr_cats.keys()) | set(prev_cats.keys())
        category_changes = []
        for cat in all_cats:
            curr = curr_cats.get(cat, 0)
            prev = prev_cats.get(cat, 0)
            if prev > 0:
                pct_change = ((curr - prev) / prev) * 100
            elif curr > 0:
                pct_change = 100.0
            else:
                pct_change = 0.0

            category_changes.append({
                "category": cat,
                "current": round(curr, 2),
                "previous": round(prev, 2),
                "change_pct": round(pct_change, 1),
                "trend": "up" if pct_change > 5 else "down" if pct_change < -5 else "stable",
            })

        category_changes.sort(key=lambda x: abs(x["change_pct"]), reverse=True)

        overall_change_pct = ((curr_total - prev_total) / prev_total * 100) if prev_total > 0 else 0

        return {
            "current_period": {
                "date_from": midpoint.strftime("%Y-%m-%d"),
                "date_to": max_date.strftime("%Y-%m-%d"),
                "total_expenses": round(curr_total, 2),
                "total_income": round(curr_income, 2),
            },
            "previous_period": {
                "date_from": min_date.strftime("%Y-%m-%d"),
                "date_to": midpoint.strftime("%Y-%m-%d"),
                "total_expenses": round(prev_total, 2),
                "total_income": round(prev_income, 2),
            },
            "overall_change_pct": round(overall_change_pct, 1),
            "overall_trend": "up" if overall_change_pct > 5 else "down" if overall_change_pct < -5 else "stable",
            "category_changes": category_changes[:10],
        }

    except Exception as e:
        return {"error": str(e), "tool": "get_period_comparison"}
