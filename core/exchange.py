"""
Currency exchange rate utilities.
Fetches live rates from frankfurter.app (ECB-based, no API key required).
"""
import asyncio

import httpx

# Module-level cache — rates fetched once per process lifetime
_eur_rates: dict[str, float] | None = None

# Fallback approximate rates (early 2026) if the API is unreachable
_FALLBACK: dict[str, float] = {
    "EUR": 1.0,
    "USD": 1.08,
    "HKD": 8.42,
    "INR": 90.5,
    "GBP": 0.85,
    "JPY": 157.0,
    "CNY": 7.82,
    "SGD": 1.46,
    "AUD": 1.67,
    "CAD": 1.49,
    "CHF": 0.97,
    "MYR": 5.08,
    "PHP": 63.2,
    "THB": 38.5,
    "IDR": 17500,
    "AED": 3.97,
}


async def _fetch_eur_rates() -> dict[str, float]:
    """
    Return EUR-based rates from frankfurter.app.
    Response shape: {"base": "EUR", "rates": {"USD": 1.08, "HKD": 8.42, ...}}
    """
    global _eur_rates
    if _eur_rates is not None:
        return _eur_rates

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get("https://api.frankfurter.app/latest")
            resp.raise_for_status()
            data = resp.json()
            rates = data.get("rates", {})
            rates["EUR"] = 1.0
            _eur_rates = rates
            return rates
    except Exception:
        return _FALLBACK


async def to_usd(amount: float, currency: str) -> float:
    """
    Convert an amount in the given ISO 4217 currency to USD.
    Preserves sign. Returns the original amount if currency is unknown.
    """
    if not currency:
        return amount

    cur = currency.strip().upper()
    if cur in ("USD", "US", ""):
        return amount

    rates = await _fetch_eur_rates()
    usd_per_eur = rates.get("USD", 1.08)
    cur_per_eur = rates.get(cur)

    if cur_per_eur is None or cur_per_eur == 0:
        return amount  # unknown — pass through unchanged

    # Cross-rate: amount_usd = amount * (USD/EUR) / (CUR/EUR)
    return amount * usd_per_eur / cur_per_eur


async def batch_to_usd(transactions: list[dict]) -> list[dict]:
    """
    Convert all transaction amounts to USD in place.
    Adds 'amount_usd', preserves 'amount' (original) and 'currency'.
    """
    # Prefetch rates once for all transactions
    rates = await _fetch_eur_rates()
    usd_per_eur = rates.get("USD", 1.08)

    for txn in transactions:
        cur = str(txn.get("currency") or "USD").strip().upper()
        orig = float(txn.get("amount", 0))
        txn["original_currency"] = cur
        txn["original_amount"]   = orig

        if cur in ("USD", ""):
            txn["amount_usd"] = orig
        else:
            cur_per_eur = rates.get(cur)
            txn["amount_usd"] = orig * usd_per_eur / cur_per_eur if cur_per_eur else orig

    return transactions
