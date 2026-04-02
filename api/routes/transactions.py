from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import TransactionItem, TransactionListResponse
from core.database import Transaction, UploadBatch, get_db

router = APIRouter()


@router.get("/transactions", response_model=TransactionListResponse, tags=["transactions"])
async def list_transactions(
    batch_id: str = Query(..., description="The batch UUID"),
    limit: int = Query(50, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """Return paginated transactions for a batch."""
    result = await db.execute(
        select(UploadBatch).where(UploadBatch.batch_id == batch_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")

    count_result = await db.execute(
        select(func.count()).select_from(Transaction).where(Transaction.batch_id == batch_id)
    )
    total = count_result.scalar_one()

    txn_result = await db.execute(
        select(Transaction)
        .where(Transaction.batch_id == batch_id)
        .order_by(Transaction.date.desc())
        .offset(offset)
        .limit(limit)
    )
    txns = txn_result.scalars().all()

    return TransactionListResponse(
        batch_id=batch_id,
        total=total,
        offset=offset,
        limit=limit,
        transactions=[
            TransactionItem(
                id=t.id,
                date=t.date,
                amount=t.amount,
                original_amount=t.original_amount,
                original_currency=t.original_currency,
                description=t.description,
                clean_name=t.clean_name,
                category=t.category,
                source_account=t.source_account,
                transaction_type=t.transaction_type,
            )
            for t in txns
        ],
    )
