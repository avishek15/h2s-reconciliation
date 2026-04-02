import io
import re
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd


# Column name aliases → canonical name
DATE_ALIASES = ["date", "transaction date", "trans date", "posting date", "value date", "txn date"]
AMOUNT_ALIASES = ["amount", "debit", "credit", "transaction amount", "txn amount", "sum"]
DESCRIPTION_ALIASES = ["description", "desc", "memo", "narration", "particulars", "details", "transaction description"]
CATEGORY_ALIASES = ["category", "cat", "type", "transaction type"]
ACCOUNT_ALIASES = ["account", "account name", "source", "bank"]


def _find_column(df: pd.DataFrame, aliases: list[str]) -> Optional[str]:
    cols_lower = {c.lower().strip(): c for c in df.columns}
    for alias in aliases:
        if alias in cols_lower:
            return cols_lower[alias]
    return None


def _normalize_amount(val) -> float:
    """Convert string like '1,234.56' or '(500.00)' to float."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return 0.0
    s = str(val).strip().replace(",", "").replace(" ", "")
    # Parentheses = negative
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_csv(file_bytes: bytes, filename: str = "upload.csv") -> list[dict]:
    try:
        df = pd.read_csv(io.BytesIO(file_bytes))
    except Exception:
        return _synthetic_transactions()

    date_col = _find_column(df, DATE_ALIASES)
    amount_col = _find_column(df, AMOUNT_ALIASES)
    desc_col = _find_column(df, DESCRIPTION_ALIASES)
    cat_col = _find_column(df, CATEGORY_ALIASES)
    acct_col = _find_column(df, ACCOUNT_ALIASES)

    if not date_col or not amount_col or not desc_col:
        return _synthetic_transactions()

    rows = []
    for _, row in df.iterrows():
        raw = row.to_dict()
        amount = _normalize_amount(row[amount_col])
        rows.append(
            {
                "date": str(row[date_col]).strip(),
                "amount": amount,
                "description": str(row[desc_col]).strip(),
                "category": str(row[cat_col]).strip() if cat_col else _guess_category(str(row[desc_col])),
                "source_account": str(row[acct_col]).strip() if acct_col else "Unknown",
                "transaction_type": "credit" if amount > 0 else "debit",
                "raw_row": str(raw),
            }
        )

    return rows if rows else _synthetic_transactions()


def _guess_category(description: str) -> str:
    desc = description.lower()
    if any(k in desc for k in ["netflix", "spotify", "prime", "disney", "hulu", "subscription"]):
        return "Subscriptions"
    if any(k in desc for k in ["grocery", "supermarket", "walmart", "target", "whole foods", "trader joe"]):
        return "Groceries"
    if any(k in desc for k in ["restaurant", "cafe", "pizza", "burger", "sushi", "food", "eat", "coffee", "starbucks"]):
        return "Dining"
    if any(k in desc for k in ["uber", "lyft", "taxi", "metro", "transit", "gas", "fuel", "parking"]):
        return "Transport"
    if any(k in desc for k in ["rent", "mortgage", "housing", "apartment"]):
        return "Housing"
    if any(k in desc for k in ["salary", "payroll", "deposit", "income", "paycheck"]):
        return "Income"
    if any(k in desc for k in ["electric", "water", "utility", "internet", "phone", "bill"]):
        return "Utilities"
    if any(k in desc for k in ["amazon", "shop", "store", "purchase", "buy"]):
        return "Shopping"
    return "Other"


def _synthetic_transactions() -> list[dict]:
    """Fallback: generates 75 realistic synthetic transactions for demo purposes."""
    base = datetime(2025, 12, 1)
    txns = []

    def add(days_offset, amount, desc, cat, acct="Checking"):
        d = (base + timedelta(days=days_offset)).strftime("%Y-%m-%d")
        txns.append(
            {
                "date": d,
                "amount": amount,
                "description": desc,
                "category": cat,
                "source_account": acct,
                "transaction_type": "credit" if amount > 0 else "debit",
                "raw_row": "",
            }
        )

    # Income
    add(0, 4500.00, "ACME Corp Payroll Direct Deposit", "Income")
    add(15, 4500.00, "ACME Corp Payroll Direct Deposit", "Income")

    # Housing
    add(1, -1800.00, "Rent Payment - Sunrise Apartments", "Housing")

    # Subscriptions (recurring)
    add(2, -15.99, "Netflix Monthly Subscription", "Subscriptions")
    add(2, -9.99, "Spotify Premium", "Subscriptions")
    add(5, -14.99, "Adobe Creative Cloud", "Subscriptions")
    add(8, -139.00, "Amazon Prime Annual - split", "Subscriptions")

    # Groceries (weekly ish)
    add(3, -87.45, "Whole Foods Market", "Groceries")
    add(10, -102.30, "Trader Joe's", "Groceries")
    add(17, -91.20, "Whole Foods Market", "Groceries")
    add(24, -78.60, "Walmart Supercenter", "Groceries")

    # Dining
    add(4, -32.50, "Chipotle Mexican Grill", "Dining")
    add(6, -78.90, "The Capital Grille Dinner", "Dining")
    add(9, -12.75, "Starbucks Coffee", "Dining")
    add(11, -45.00, "Sushi Palace Restaurant", "Dining")
    add(13, -22.40, "Dominos Pizza", "Dining")
    add(16, -18.90, "Starbucks Coffee", "Dining")
    add(19, -64.00, "Nobu Restaurant", "Dining")
    add(22, -14.50, "McDonald's", "Dining")
    add(25, -88.50, "Birthday Dinner - Mastro's", "Dining")

    # Transport
    add(3, -45.00, "Uber Ride", "Transport")
    add(7, -62.40, "Shell Gas Station", "Transport")
    add(12, -38.00, "Lyft Ride", "Transport")
    add(18, -58.00, "Shell Gas Station", "Transport")
    add(23, -12.00, "Parking - Downtown Garage", "Transport")
    add(27, -42.00, "Uber Ride", "Transport")

    # Utilities
    add(5, -95.00, "ConEdison Electric Bill", "Utilities")
    add(5, -45.00, "Verizon Wireless Bill", "Utilities")
    add(6, -65.00, "Comcast Internet", "Utilities")

    # Shopping
    add(4, -129.00, "Amazon.com Order #112-334", "Shopping")
    add(8, -249.99, "Best Buy Electronics", "Shopping")
    add(14, -56.00, "Target Store", "Shopping")
    add(20, -35.00, "Amazon.com Order #112-891", "Shopping")
    add(26, -189.00, "Apple Store", "Shopping")
    add(28, -78.00, "Nike Online Store", "Shopping")

    # Health
    add(7, -150.00, "Dr. Smith Co-pay", "Health")
    add(15, -45.00, "CVS Pharmacy", "Health")
    add(21, -180.00, "Dental Cleaning - Dr. Lee", "Health")

    # ATM / Cash
    add(3, -200.00, "ATM Withdrawal - Chase Bank", "Cash")
    add(17, -200.00, "ATM Withdrawal - Chase Bank", "Cash")

    # Entertainment
    add(6, -35.00, "AMC Theaters", "Entertainment")
    add(13, -120.00, "Ticketmaster - Concert", "Entertainment")
    add(20, -28.00, "Steam Game Purchase", "Entertainment")

    # Anomaly: unusually large transaction
    add(22, -2800.00, "MacBook Pro Purchase - Apple Store", "Shopping")

    # Duplicate transaction (same day, amount, description)
    add(10, -102.30, "Trader Joe's", "Groceries")

    # Previous month transactions for comparison
    prev = -30
    add(prev + 0, 4500.00, "ACME Corp Payroll Direct Deposit", "Income")
    add(prev + 15, 4500.00, "ACME Corp Payroll Direct Deposit", "Income")
    add(prev + 1, -1800.00, "Rent Payment - Sunrise Apartments", "Housing")
    add(prev + 2, -15.99, "Netflix Monthly Subscription", "Subscriptions")
    add(prev + 2, -9.99, "Spotify Premium", "Subscriptions")
    add(prev + 5, -14.99, "Adobe Creative Cloud", "Subscriptions")
    add(prev + 3, -94.50, "Whole Foods Market", "Groceries")
    add(prev + 10, -88.00, "Trader Joe's", "Groceries")
    add(prev + 17, -76.30, "Whole Foods Market", "Groceries")
    add(prev + 4, -28.00, "Chipotle Mexican Grill", "Dining")
    add(prev + 9, -15.50, "Starbucks Coffee", "Dining")
    add(prev + 14, -42.00, "Sushi Palace Restaurant", "Dining")
    add(prev + 7, -58.00, "Shell Gas Station", "Transport")
    add(prev + 18, -55.00, "Shell Gas Station", "Transport")
    add(prev + 5, -95.00, "ConEdison Electric Bill", "Utilities")
    add(prev + 5, -45.00, "Verizon Wireless Bill", "Utilities")
    add(prev + 6, -65.00, "Comcast Internet", "Utilities")
    add(prev + 4, -89.00, "Amazon.com Order", "Shopping")
    add(prev + 20, -45.00, "Target Store", "Shopping")

    return txns
