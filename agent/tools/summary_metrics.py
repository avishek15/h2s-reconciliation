from collections import defaultdict

from sqlalchemy import select

from core.database import AsyncSessionLocal, Transaction


async def get_summary_metrics(batch_id: str) -> dict:
    """
    Calculate summary financial metrics for a batch of transactions.

    Returns total income, total expenses, net cash flow, transaction count,
    top spending categories, date range, and average daily spend.

    Args:
        batch_id: The UUID of the upload batch to analyze.

    Returns:
        A dictionary with keys: total_income, total_expenses, net_cash_flow,
        transaction_count, top_categories, date_range, avg_daily_spend.
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Transaction).where(Transaction.batch_id == batch_id)
            )
            transactions = result.scalars().all()

        if not transactions:
            return {"error": f"No transactions found for batch_id: {batch_id}"}

        amounts = [t.amount for t in transactions]
        dates = sorted([t.date for t in transactions if t.date])

        total_income = sum(a for a in amounts if a > 0)
        total_expenses = abs(sum(a for a in amounts if a < 0))
        net_cash_flow = total_income - total_expenses

        # Category breakdown
        category_totals: dict[str, float] = defaultdict(float)
        for t in transactions:
            if t.amount < 0:
                cat = t.category or "Uncategorized"
                category_totals[cat] += abs(t.amount)

        top_categories = sorted(
            [
                {
                    "category": cat,
                    "amount": round(amt, 2),
                    "pct": round(amt / total_expenses * 100, 1) if total_expenses > 0 else 0,
                }
                for cat, amt in category_totals.items()
            ],
            key=lambda x: x["amount"],
            reverse=True,
        )[:5]

        # Date range and avg daily spend
        date_range = {"from": dates[0], "to": dates[-1]} if dates else {}
        avg_daily_spend = 0.0
        if len(dates) >= 2:
            from datetime import datetime
            try:
                d1 = datetime.strptime(dates[0], "%Y-%m-%d")
                d2 = datetime.strptime(dates[-1], "%Y-%m-%d")
                days = max((d2 - d1).days, 1)
                avg_daily_spend = round(total_expenses / days, 2)
            except ValueError:
                pass

        return {
            "total_income": round(total_income, 2),
            "total_expenses": round(total_expenses, 2),
            "net_cash_flow": round(net_cash_flow, 2),
            "transaction_count": len(transactions),
            "top_categories": top_categories,
            "date_range": date_range,
            "avg_daily_spend": avg_daily_spend,
        }

    except Exception as e:
        return {"error": str(e), "tool": "get_summary_metrics"}
