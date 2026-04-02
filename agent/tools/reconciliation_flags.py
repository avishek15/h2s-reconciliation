import statistics
from collections import defaultdict
from datetime import datetime

from sqlalchemy import select

from core.database import AsyncSessionLocal, Transaction


async def get_reconciliation_flags(batch_id: str) -> dict:
    """
    Identify financial anomalies and reconciliation issues in the transaction data.

    Detects: duplicate transactions, unusually large transactions, round-number
    concentration, missing categories, and weekend large transactions.

    Args:
        batch_id: The UUID of the upload batch to analyze.

    Returns:
        A dictionary with a 'flags' list. Each flag has: flag_type, severity
        (HIGH/MEDIUM/LOW), description, and optionally affected_transactions.
    """
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Transaction).where(Transaction.batch_id == batch_id)
            )
            transactions = result.scalars().all()

        if not transactions:
            return {"flags": [], "total_flags": 0}

        flags = []
        amounts = [abs(t.amount) for t in transactions if t.amount < 0]

        # 1. Duplicate detection: same date + amount + description
        seen = defaultdict(list)
        for t in transactions:
            key = (t.date, round(t.amount, 2), t.description.lower().strip())
            seen[key].append(t.id)

        for key, ids in seen.items():
            if len(ids) > 1:
                flags.append({
                    "flag_type": "DUPLICATE_TRANSACTION",
                    "severity": "HIGH",
                    "description": (
                        f"Duplicate transaction detected: '{key[1]}' amount {key[1]} on {key[0]}. "
                        f"Appears {len(ids)} times."
                    ),
                    "affected_transactions": ids,
                    "amount": key[1],
                })

        # 2. Large transaction anomaly (>2 std devs from mean)
        if len(amounts) > 3:
            mean = statistics.mean(amounts)
            stdev = statistics.stdev(amounts)
            threshold = mean + 2 * stdev
            for t in transactions:
                if t.amount < 0 and abs(t.amount) > threshold:
                    flags.append({
                        "flag_type": "LARGE_TRANSACTION_ANOMALY",
                        "severity": "HIGH",
                        "description": (
                            f"Unusually large transaction: '{t.description}' — "
                            f"${abs(t.amount):.2f} on {t.date} "
                            f"(threshold: ${threshold:.2f}, mean: ${mean:.2f})"
                        ),
                        "affected_transactions": [t.id],
                        "amount": abs(t.amount),
                    })

        # 3. Round number concentration (>30% of transactions are exact round hundreds)
        debit_txns = [t for t in transactions if t.amount < 0]
        if debit_txns:
            round_count = sum(1 for t in debit_txns if abs(t.amount) % 100 == 0)
            round_pct = round_count / len(debit_txns)
            if round_pct > 0.30:
                flags.append({
                    "flag_type": "ROUND_NUMBER_CONCENTRATION",
                    "severity": "MEDIUM",
                    "description": (
                        f"{round_pct:.0%} of expense transactions are round-number amounts "
                        f"({round_count}/{len(debit_txns)}). This may indicate manual entries."
                    ),
                    "affected_transactions": [],
                })

        # 4. Missing categories
        uncategorized = [t for t in transactions if not t.category or t.category in ("", "None", "Other")]
        if len(uncategorized) > 0:
            flags.append({
                "flag_type": "MISSING_CATEGORIES",
                "severity": "LOW",
                "description": (
                    f"{len(uncategorized)} transaction(s) have no category assigned. "
                    "This may affect spending analysis accuracy."
                ),
                "affected_transactions": [t.id for t in uncategorized[:5]],
            })

        # 5. Weekend large transactions
        weekend_large = []
        for t in transactions:
            if t.amount < 0 and abs(t.amount) > 500:
                try:
                    d = datetime.strptime(t.date, "%Y-%m-%d")
                    if d.weekday() >= 5:  # Saturday=5, Sunday=6
                        weekend_large.append(t)
                except ValueError:
                    pass

        if weekend_large:
            total = sum(abs(t.amount) for t in weekend_large)
            flags.append({
                "flag_type": "WEEKEND_LARGE_TRANSACTIONS",
                "severity": "MEDIUM",
                "description": (
                    f"{len(weekend_large)} high-value transaction(s) occurred on weekends "
                    f"totaling ${total:.2f}. Review for unusual activity."
                ),
                "affected_transactions": [t.id for t in weekend_large],
            })

        return {
            "flags": flags,
            "total_flags": len(flags),
            "high_severity": sum(1 for f in flags if f["severity"] == "HIGH"),
            "medium_severity": sum(1 for f in flags if f["severity"] == "MEDIUM"),
            "low_severity": sum(1 for f in flags if f["severity"] == "LOW"),
        }

    except Exception as e:
        return {"error": str(e), "tool": "get_reconciliation_flags"}
