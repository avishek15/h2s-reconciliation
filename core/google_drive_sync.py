"""
Service for monitoring Google Drive folders and auto-triggering reconciliation.
"""

import asyncio
import base64
import json
from datetime import datetime
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import Profile, UploadBatch, BatchFile, Transaction, get_db, AsyncSessionLocal
from core.google_drive import GoogleDriveService
from agent.money_story_agent import run_agent
from core.ingestion import extract_text, normalize_to_transactions
from core.exchange import batch_to_usd


class GoogleDriveSyncService:
    """Service for syncing files from Google Drive and triggering reconciliation."""

    SUPPORTED_FILE_TYPES = [".csv", ".xlsx", ".xls", ".pdf"]

    @staticmethod
    async def sync_profile_files(profile_id: str, db: Optional[AsyncSession] = None):
        """
        Sync files from a profile's Google Drive folder and create an upload batch.
        Auto-triggers reconciliation if files are found.
        
        Args:
            profile_id: Profile ID to sync
            db: Database session (creates new if not provided)
        """
        if db is None:
            db = AsyncSessionLocal()

        try:
            # Get profile
            result = await db.execute(
                select(Profile).where(Profile.id == profile_id)
            )
            profile = result.scalar_one_or_none()

            if not profile or not profile.google_drive_access_token:
                print(f"Profile {profile_id} not found or missing Google Drive token")
                return

            # Initialize Google Drive service
            gd_service = GoogleDriveService(
                profile.google_drive_access_token,
                profile.google_drive_refresh_token,
            )

            # List files in folder
            files = await gd_service.list_files_in_folder(
                profile.google_drive_folder_id,
                GoogleDriveSyncService.SUPPORTED_FILE_TYPES,
            )

            if not files:
                print(f"No files found in profile {profile_id}")
                return

            print(f"Found {len(files)} files in profile {profile_id}")

            # Create upload batch
            batch = UploadBatch(
                profile_id=profile_id,
                file_count=len(files),
                status="processing",
            )
            db.add(batch)
            await db.commit()
            await db.refresh(batch)

            # Download and store files
            file_count = 0
            for file_meta in files:
                try:
                    file_content = await gd_service.download_file(
                        file_meta["id"],
                        file_meta["name"],
                    )

                    if file_content:
                        # Encode to base64
                        file_b64 = base64.b64encode(file_content).decode("utf-8")

                        batch_file = BatchFile(
                            batch_id=batch.batch_id,
                            filename=file_meta["name"],
                            mime_type=file_meta.get("mimeType", "application/octet-stream"),
                            content_b64=file_b64,
                        )
                        db.add(batch_file)
                        file_count += 1

                except Exception as e:
                    print(f"Error downloading file {file_meta['name']}: {e}")

            await db.commit()

            # Update batch with actual file count
            await db.execute(
                update(UploadBatch)
                .where(UploadBatch.batch_id == batch.batch_id)
                .values(file_count=file_count)
            )
            await db.commit()

            # Auto-trigger pipeline asynchronously (don't block sync)
            print(f"Auto-triggering reconciliation for batch {batch.batch_id}")
            # Run pipeline in background to avoid blocking
            asyncio.create_task(GoogleDriveSyncService.auto_trigger_pipeline(batch.batch_id))

            # Update profile's last_synced timestamp
            await db.execute(
                update(Profile)
                .where(Profile.id == profile_id)
                .values(last_synced=datetime.utcnow())
            )
            await db.commit()

        except Exception as e:
            print(f"Error syncing profile {profile_id}: {e}")
            try:
                batch_result = await db.execute(
                    select(UploadBatch).where(UploadBatch.profile_id == profile_id).order_by(UploadBatch.created_at.desc()).limit(1)
                )
                latest_batch = batch_result.scalar_one_or_none()
                if latest_batch:
                    await db.execute(
                        update(UploadBatch)
                        .where(UploadBatch.batch_id == latest_batch.batch_id)
                        .values(status="failed")
                    )
                    await db.commit()
            except Exception as inner:
                print(f"Error marking batch failed for profile {profile_id}: {inner}")
        finally:
            if db:
                await db.close()

    @staticmethod
    async def auto_trigger_pipeline(batch_id: str):
        """
        Auto-trigger the full pipeline for a batch:
        1. Ingest transactions
        2. Run reconciliation
        3. Generate narrative
        
        Args:
            batch_id: Batch ID to process
        """
        db = AsyncSessionLocal()  # Create own session since running asynchronously

        try:
            print(f"Starting auto pipeline for batch {batch_id}")
            
            # Get batch
            result = await db.execute(
                select(UploadBatch).where(UploadBatch.batch_id == batch_id)
            )
            batch = result.scalar_one_or_none()

            if not batch:
                print(f"Batch {batch_id} not found")
                return

            print(f"Processing {batch.file_count} files for batch {batch_id}")

            # Get files
            files_result = await db.execute(
                select(BatchFile).where(BatchFile.batch_id == batch_id)
            )
            files = files_result.scalars().all()

            if not files:
                print(f"No files found for batch {batch_id}")
                return

            total = 0
            for f in files:
                print(f"Processing file: {f.filename}")
                # Phase 1 — extract text
                text = await extract_text(f.filename, f.mime_type, f.content_b64)
                print(f"Extracted {len(text)} characters from {f.filename}")

                # Phase 2 — normalize to transactions
                txns = await normalize_to_transactions(f.filename, text)
                txns = await batch_to_usd(txns)
                print(f"Normalized {len(txns)} transactions from {f.filename}")

                for txn in txns:
                    try:
                        amount = float(txn.get("amount", 0))
                    except (TypeError, ValueError):
                        amount = 0.0

                    usd_amount = float(txn.get("amount_usd", amount))

                    transaction = Transaction(
                        batch_id=batch_id,
                        date=txn.get("date"),
                        amount=usd_amount,
                        description=txn.get("description", ""),
                        original_amount=amount,
                        original_currency=txn.get("original_currency", txn.get("currency", "USD")),
                        category=txn.get("category", "uncategorized"),
                    )
                    db.add(transaction)
                    total += 1

            await db.commit()
            print(f"Committed {total} transactions for batch {batch_id}")

            # Phase 3 — generate narrative
            print(f"Generating narrative for batch {batch_id}")
            narrative = await run_agent(batch_id)
            print(f"Narrative generated for batch {batch_id}")

            # Save narrative to AIReport
            from core.database import AIReport
            ai_report = AIReport(
                batch_id=batch_id,
                narrative=json.dumps(narrative) if not isinstance(narrative, str) else narrative,
            )
            db.add(ai_report)
            await db.commit()

            # Update batch status
            await db.execute(
                update(UploadBatch)
                .where(UploadBatch.batch_id == batch_id)
                .values(status="completed")
            )
            await db.commit()

            print(f"Pipeline completed for batch {batch_id}, {total} transactions processed")

        except Exception as e:
            print(f"Error in auto-trigger pipeline for {batch_id}: {e}")
            import traceback
            traceback.print_exc()
            try:
                await db.execute(
                    update(UploadBatch)
                    .where(UploadBatch.batch_id == batch_id)
                    .values(status="failed")
                )
                await db.commit()
                print(f"Marked batch {batch_id} as failed")
            except Exception as inner:
                print(f"Error marking batch {batch_id} as failed: {inner}")
        finally:
            if db:
                await db.close()

    @staticmethod
    async def sync_all_profiles():
        """
        Sync all user profiles (can be called periodically).
        """
        db = AsyncSessionLocal()
        try:
            result = await db.execute(select(Profile))
            profiles = result.scalars().all()

            for profile in profiles:
                await GoogleDriveSyncService.sync_profile_files(profile.id, db)

        except Exception as e:
            print(f"Error syncing all profiles: {e}")
        finally:
            await db.close()
