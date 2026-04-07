import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import ReconcileRequest, ReconcileResponse
from core.auth import get_current_user, get_owned_batch
from core.database import BatchFile, Transaction, User, get_db
from core.exchange import batch_to_usd
from core.ingestion import extract_text, normalize_to_transactions, process_files_concurrently
from core.services.profile_data import get_or_create_account

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/reconcile", response_model=ReconcileResponse, tags=["pipeline"])
async def reconcile(
    request: ReconcileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Phase 1 + 2 of the pipeline.

    For each uploaded file:
      - Extract raw text (CSV decoded directly; PDF/image via Gemini vision)
      - Call Gemini to parse text into structured transactions
      - Store results in the transactions table, scoped to batch_id

    Session isolation: all queries are filtered by batch_id.
    """
    import time
    t0 = time.time()

    logger.info(f"[RECONCILE] === START batch_id={request.batch_id} user={current_user.id} ===")

    batch = await get_owned_batch(db, request.batch_id, current_user.id)
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Batch {request.batch_id} not found or access denied",
        )

    files_result = await db.execute(
        select(BatchFile).where(BatchFile.batch_id == request.batch_id)
    )
    files = files_result.scalars().all()

    if not files:
        raise HTTPException(
            status_code=422,
            detail="No files found for this batch. Please re-upload your statements.",
        )

    logger.info(f"[RECONCILE] Found {len(files)} files: {[f.filename for f in files]}")

    batch.status = "processing"
    batch.completed_at = None
    await db.commit()

    total = 0
    try:
        file_args = [(f.filename, f.mime_type, f.content_b64) for f in files]

        t1 = time.time()
        logger.info(f"[RECONCILE] Starting file processing ({len(file_args)} files)...")
        all_txn_batches = await process_files_concurrently(file_args, max_concurrent=2)
        logger.info(f"[RECONCILE] File processing done in {time.time()-t1:.2f}s")

        t2 = time.time()
        for f, transactions in zip(files, all_txn_batches):
            logger.info(f"[RECONCILE] File {f.filename}: {len(transactions)} raw transactions")

            transactions = await batch_to_usd(transactions)
            logger.info(f"[RECONCILE] Currency conversion done for {f.filename}")

            account = None
            if batch.profile_id:
                account_currency = next(
                    (
                        str(txn.get("original_currency", txn.get("currency", ""))).upper()
                        for txn in transactions
                        if txn.get("original_currency") or txn.get("currency")
                    ),
                    None,
                )
                t3 = time.time()
                account = await get_or_create_account(
                    db,
                    profile_id=batch.profile_id,
                    account_name=f.filename,
                    currency=account_currency,
                    external_ref=f.filename,
                )
                logger.info(f"[RECONCILE] Account resolved for {f.filename} in {time.time()-t3:.2f}s")

            for txn in transactions:
                try:
                    amount = float(txn.get("amount", 0))
                except (TypeError, ValueError):
                    amount = 0.0

                usd_amount = float(txn.get("amount_usd", amount))

                t = Transaction(
                    id=str(uuid.uuid4()),
                    batch_id=request.batch_id,
                    profile_id=batch.profile_id,
                    account_id=account.id if account else None,
                    date=str(txn.get("date", "")).strip() or "unknown",
                    amount=usd_amount,
                    original_amount=amount,
                    original_currency=str(txn.get("original_currency", "USD")).upper(),
                    description=str(txn.get("description", "")).strip() or "—",
                    clean_name=str(txn.get("clean_name", "")).strip() or None,
                    category=str(txn.get("category", "Other")).strip(),
                    source_account=f.filename,
                    transaction_type=str(
                        txn.get("type", "debit" if amount < 0 else "credit")
                    ).strip(),
                    raw_row=str(txn),
                )
                db.add(t)
                total += 1

        logger.info(f"[RECONCILE] DB inserts done in {time.time()-t2:.2f}s, {total} transactions")

        batch.transaction_count = total
        batch.status = "completed"
        batch.completed_at = datetime.now(timezone.utc)
        await db.commit()

        elapsed = time.time() - t0
        logger.info(f"[RECONCILE] === COMPLETE batch_id={request.batch_id} in {elapsed:.2f}s — {total} transactions ===")

        return ReconcileResponse(
            batch_id=request.batch_id,
            flags_found=0,
            patterns_found=0,
            transaction_count=total,
            status="complete",
        )
    except Exception as e:
        elapsed = time.time() - t0
        logger.error(f"[RECONCILE] === FAILED batch_id={request.batch_id} after {elapsed:.2f}s: {e} ===")
        batch.status = "failed"
        batch.completed_at = datetime.now(timezone.utc)
        await db.commit()
        raise
