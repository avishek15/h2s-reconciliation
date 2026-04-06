"""
Batch Orchestrator Tool — Coordinates multi-agent analysis pipeline.
Handles transaction ingestion, status tracking, and agent orchestration.
Can be triggered from Google Drive sync or any other workflow.
"""

import json
from datetime import datetime
from typing import Optional, Callable

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import (
    UploadBatch,
    BatchFile,
    Transaction,
    AIReport,
    AsyncSessionLocal,
)
from core.ingestion import extract_text, normalize_to_transactions
from core.exchange import batch_to_usd
from core.services.profile_data import get_or_create_account
from agent.money_story_agent import run_agent


class BatchOrchestratorTool:
    """Orchestrates batch processing and multi-agent analysis."""

    @staticmethod
    async def process_batch(
        batch_id: str,
        db: Optional[AsyncSession] = None,
        status_callback: Optional[Callable[[str], None]] = None,
    ) -> dict:
        """
        Process a batch end-to-end:
        1. Extract text from files
        2. Normalize to transactions
        3. Convert to USD
        4. Run multi-agent analysis
        5. Store results

        Args:
            batch_id: Batch ID to process
            db: Database session (creates new if not provided)
            status_callback: Optional callback to report status updates

        Returns:
            dict: Pipeline result with narrative, insights, actions, etc.
        """
        owns_db = db is None
        if owns_db:
            db = AsyncSessionLocal()

        try:
            # Get batch
            result = await db.execute(
                select(UploadBatch).where(UploadBatch.batch_id == batch_id)
            )
            batch = result.scalar_one_or_none()

            if not batch:
                raise ValueError(f"Batch {batch_id} not found")

            print(f"[BatchOrchestrator] Starting pipeline for batch {batch_id}")
            if status_callback:
                await status_callback("extracting")

            # Get files
            files_result = await db.execute(
                select(BatchFile).where(BatchFile.batch_id == batch_id)
            )
            files = files_result.scalars().all()

            if not files:
                raise ValueError(f"No files found for batch {batch_id}")

            print(f"[BatchOrchestrator] Processing {len(files)} files")

            # Phase 1 & 2: Extract text and normalize to transactions
            total_transactions = 0
            for f in files:
                print(f"[BatchOrchestrator] Extracting: {f.filename}")

                # Extract text
                text = await extract_text(f.filename, f.mime_type, f.content_b64)
                print(f"[BatchOrchestrator] Extracted {len(text)} chars from {f.filename}")

                # Normalize to transactions
                txns = await normalize_to_transactions(f.filename, text)
                print(f"[BatchOrchestrator] Normalized {len(txns)} raw transactions")

                # Convert to USD
                txns = await batch_to_usd(txns)
                print(f"[BatchOrchestrator] After USD conversion: {len(txns)} transactions")

                account = None
                if batch.profile_id:
                    account_currency = next(
                        (
                            str(txn.get("original_currency", txn.get("currency", ""))).upper()
                            for txn in txns
                            if txn.get("original_currency") or txn.get("currency")
                        ),
                        None,
                    )
                    account = await get_or_create_account(
                        db,
                        profile_id=batch.profile_id,
                        account_name=f.filename,
                        currency=account_currency,
                        external_ref=f.filename,
                    )

                # Persist transactions
                for txn in txns:
                    try:
                        amount = float(txn.get("amount", 0))
                    except (TypeError, ValueError):
                        amount = 0.0

                    usd_amount = float(txn.get("amount_usd", amount))

                    transaction = Transaction(
                        batch_id=batch_id,
                        profile_id=batch.profile_id,
                        account_id=account.id if account else None,
                        date=str(txn.get("date", "")).strip() or "unknown",
                        amount=usd_amount,
                        description=str(txn.get("description", "")).strip() or "—",
                        clean_name=str(txn.get("clean_name", "")).strip() or None,
                        original_amount=amount,
                        original_currency=txn.get(
                            "original_currency", txn.get("currency", "USD")
                        ),
                        category=str(txn.get("category", "Other")).strip(),
                        source_account=f.filename,
                        transaction_type=str(
                            txn.get("type", "debit" if amount < 0 else "credit")
                        ).strip(),
                        raw_row=str(txn),
                    )
                    db.add(transaction)
                    total_transactions += 1

            await db.commit()
            print(f"[BatchOrchestrator] Persisted {total_transactions} transactions")

            # Update batch transaction count
            await db.execute(
                update(UploadBatch)
                .where(UploadBatch.batch_id == batch_id)
                .values(
                    status="reconciled",
                    transaction_count=total_transactions,
                )
            )
            await db.commit()

            if status_callback:
                await status_callback("reconciled")

            # Phase 3: Run multi-agent analysis
            print(f"[BatchOrchestrator] Starting multi-agent analysis for batch {batch_id}")
            if status_callback:
                await status_callback("multi-agent-analysis")

            narrative = await run_agent(batch_id, db=db, status_callback=status_callback)
            print(f"[BatchOrchestrator] Multi-agent analysis complete")

            if status_callback:
                await status_callback("narrative-synthesis")

            # Phase 4: Persist results
            print(f"[BatchOrchestrator] Storing AI report")
            ai_report = AIReport(
                batch_id=batch_id,
                narrative=(
                    json.dumps(narrative)
                    if not isinstance(narrative, str)
                    else narrative
                ),
            )
            db.add(ai_report)
            await db.commit()

            # Mark batch as completed
            await db.execute(
                update(UploadBatch)
                .where(UploadBatch.batch_id == batch_id)
                .values(
                    status="completed",
                )
            )
            await db.commit()

            print(f"[BatchOrchestrator] Pipeline completed: {total_transactions} transactions")
            if status_callback:
                await status_callback("completed")

            return {
                "batch_id": batch_id,
                "transaction_count": total_transactions,
                "narrative": narrative,
                "status": "success",
            }

        except Exception as e:
            print(f"[BatchOrchestrator] Error processing batch {batch_id}: {e}")
            import traceback

            traceback.print_exc()

            # Mark batch as failed
            try:
                await db.execute(
                    update(UploadBatch)
                    .where(UploadBatch.batch_id == batch_id)
                    .values(status="failed")
                )
                await db.commit()
            except Exception as inner:
                print(f"[BatchOrchestrator] Error marking batch failed: {inner}")

            if status_callback:
                await status_callback("failed")

            return {
                "batch_id": batch_id,
                "status": "failed",
                "error": str(e),
            }

        finally:
            if owns_db and db:
                await db.close()
