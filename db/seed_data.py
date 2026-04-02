"""
Seed data helper — wraps the synthetic transaction generator in core/parser.py.
Called by the /api/v1/demo/seed endpoint.
"""
from core.parser import _synthetic_transactions


def get_seed_transactions() -> list[dict]:
    return _synthetic_transactions()
