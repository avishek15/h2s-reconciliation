import uuid
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import SeedResponse
from core.database import Transaction, UploadBatch, get_db
from db.seed_data import get_seed_transactions

router = APIRouter()


@router.post("/demo/seed", response_model=SeedResponse, tags=["demo"])
async def seed_demo_data(db: AsyncSession = Depends(get_db)):
    """
    Load 75 synthetic transactions for instant demo/judging purposes.
    Returns a batch_id ready to use with all other endpoints.
    No file upload needed.
    """
    batch_id = str(uuid.uuid4())
    rows = get_seed_transactions()

    batch = UploadBatch(
        batch_id=batch_id,
        created_at=datetime.utcnow(),
        status="parsed",
        file_count=0,
        transaction_count=len(rows),
    )
    db.add(batch)
    await db.flush()

    for row in rows:
        txn = Transaction(
            batch_id=batch_id,
            date=row["date"],
            amount=row["amount"],
            description=row["description"],
            category=row.get("category"),
            source_account=row.get("source_account"),
            transaction_type=row.get("transaction_type"),
            raw_row=row.get("raw_row", ""),
        )
        db.add(txn)

    await db.commit()

    return SeedResponse(
        batch_id=batch_id,
        transaction_count=len(rows),
        message=(
            f"Demo data loaded. Use batch_id '{batch_id}' with "
            "/api/v1/pipeline/reconcile and /api/v1/agent/narrative."
        ),
    )
