import re
import statistics
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select

from core.database import AsyncSessionLocal, Transaction


def _normalize_description(desc: str) -> str:
    """Strip dates, order numbers, and IDs from descriptions for grouping."""
    desc = desc.lower().strip()
    # Remove date-like patterns
    desc = re.sub(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", "", desc)
    # Remove order numbers and reference IDs
    desc = re.sub(r"#[\w-]+", "", desc)
    desc = re.sub(r"\border\s+\w+", "", desc)
    # Remove trailing/leading whitespace
    desc = re.sub(r"\s+", " ", desc).strip()
    return desc


def _classify_frequency(median_days: float) -> str:
    if median_days <= 8:
        return "weekly"
    elif median_days <= 16:
        return "biweekly"
    elif median_days <= 35:
        return "monthly"
    elif median_days <= 95:
        return "quarterly"
    elif median_days <= 380:
        return "annual"
    return "irregular"


async def get_recurring_patterns(batch_id: str) -> dict:
    """
    Detect recurring payments and subscriptions in the transaction history.

    Groups transactions by normalized description, computes median interval in days,
    classifies frequency (weekly/monthly/annual), and projects next expected date.

    Args:
        batch_id: The UUID of the upload batch to analyze.

    Returns:
        A dictionary with a 'patterns' list. Each pattern includes description,
        avg_amount, frequency_label, next_expected_date, and confidence_score.
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Transaction).where(Transaction.batch_id == batch_id)
            )
            transactions = result.scalars().all()

        if not transactions:
            return {"patterns": [], "total_patterns": 0}

        # Group expense transactions by normalized description
        groups: dict[str, list[Transaction]] = defaultdict(list)
        for t in transactions:
            if t.amount < 0:
                key = _normalize_description(t.description)
                groups[key].append(t)

        patterns = []
        for norm_desc, txns in groups.items():
            if len(txns) < 2:
                continue

            # Sort by date
            dated = []
            for t in txns:
                try:
                    d = datetime.strptime(t.date, "%Y-%m-%d")
                    dated.append((d, t))
                except ValueError:
                    pass

            if len(dated) < 2:
                continue

            dated.sort(key=lambda x: x[0])

            # Compute intervals between consecutive occurrences
            intervals = []
            for i in range(1, len(dated)):
                delta = (dated[i][0] - dated[i - 1][0]).days
                intervals.append(delta)

            median_interval = statistics.median(intervals)
            amounts = [abs(t.amount) for _, t in dated]
            avg_amount = statistics.mean(amounts)
            amount_variance = statistics.stdev(amounts) / avg_amount if len(amounts) > 1 and avg_amount > 0 else 0

            # Confidence: low variance in interval and amount = high confidence
            interval_variance = statistics.stdev(intervals) / median_interval if len(intervals) > 1 and median_interval > 0 else 0
            confidence = max(0.0, min(1.0, 1.0 - (interval_variance * 0.5 + amount_variance * 0.5)))

            last_date = dated[-1][0]
            next_expected = (last_date + timedelta(days=median_interval)).strftime("%Y-%m-%d")

            freq_label = _classify_frequency(median_interval)

            # Use the most common actual description for display
            desc_counts: dict[str, int] = defaultdict(int)
            for _, t in dated:
                desc_counts[t.description] += 1
            display_desc = max(desc_counts, key=lambda k: desc_counts[k])

            patterns.append({
                "description": display_desc,
                "normalized_key": norm_desc,
                "avg_amount": round(avg_amount, 2),
                "frequency_label": freq_label,
                "frequency_days": round(median_interval, 1),
                "occurrence_count": len(dated),
                "last_seen": last_date.strftime("%Y-%m-%d"),
                "next_expected_date": next_expected,
                "confidence_score": round(confidence, 2),
                "is_subscription": freq_label in ("monthly", "annual", "weekly") and amount_variance < 0.05,
            })

        # Sort by avg_amount descending (biggest recurring costs first)
        patterns.sort(key=lambda x: x["avg_amount"], reverse=True)

        subscriptions = [p for p in patterns if p["is_subscription"]]
        subscription_total = sum(p["avg_amount"] for p in subscriptions)

        return {
            "patterns": patterns,
            "total_patterns": len(patterns),
            "subscription_count": len(subscriptions),
            "monthly_subscription_cost": round(subscription_total, 2),
        }

    except Exception as e:
        return {"error": str(e), "tool": "get_recurring_patterns"}
