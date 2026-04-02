from fastapi import APIRouter, Depends
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import (
    AIReport,
    BatchFile,
    ReconciliationResult,
    RecurringPattern,
    Transaction,
    UploadBatch,
    get_db,
)

router = APIRouter()


@router.post("/reset", tags=["admin"])
async def reset_all(db: AsyncSession = Depends(get_db)):
    """
    Wipe all session data from every table.
    Use to clear the database between demo sessions.
    """
    await db.execute(delete(AIReport))
    await db.execute(delete(ReconciliationResult))
    await db.execute(delete(RecurringPattern))
    await db.execute(delete(Transaction))
    await db.execute(delete(BatchFile))
    await db.execute(delete(UploadBatch))
    await db.commit()
    return {"status": "wiped", "message": "All session data cleared."}
