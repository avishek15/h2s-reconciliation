from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import SummaryReportResponse, RecurringReportResponse
from core.database import UploadBatch, get_db
from agent.tools.summary_metrics import get_summary_metrics
from agent.tools.recurring_patterns import get_recurring_patterns

router = APIRouter()


@router.get("/summary", response_model=SummaryReportResponse, tags=["reports"])
async def get_summary(
    batch_id: str = Query(..., description="The batch UUID to report on"),
    db: AsyncSession = Depends(get_db),
):
    """Return summary financial metrics for a batch."""
    result = await db.execute(
        select(UploadBatch).where(UploadBatch.batch_id == batch_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")

    data = await get_summary_metrics(batch_id)
    return SummaryReportResponse(batch_id=batch_id, data=data)


@router.get("/recurring", response_model=RecurringReportResponse, tags=["reports"])
async def get_recurring(
    batch_id: str = Query(..., description="The batch UUID to report on"),
    db: AsyncSession = Depends(get_db),
):
    """Return recurring payment patterns detected for a batch."""
    result = await db.execute(
        select(UploadBatch).where(UploadBatch.batch_id == batch_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Batch {batch_id} not found")

    data = await get_recurring_patterns(batch_id)
    return RecurringReportResponse(batch_id=batch_id, data=data)
