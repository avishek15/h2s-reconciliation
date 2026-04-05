import base64
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import UploadResponse
from core.auth import get_current_user
from core.database import UploadBatch, BatchFile, User, Profile, get_db

router = APIRouter()

MIME_MAP = {
    ".pdf":  "application/pdf",
    ".csv":  "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls":  "application/vnd.ms-excel",
    ".txt":  "text/plain",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
}


@router.post("/uploads", response_model=UploadResponse, tags=["uploads"])
async def upload_files(
    profile_id: str,
    files: list[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload one or more bank statement files (PDF, CSV, images) for a specific profile.
    Stores raw file bytes for direct Gemini multimodal analysis.
    Returns a batch_id to use in subsequent agent calls.
    Requires authentication.
    """
    # Verify profile belongs to user
    result = await db.execute(
        select(Profile).where(
            (Profile.id == profile_id) & (Profile.user_id == current_user.id)
        )
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found or access denied",
        )

    batch_id = str(uuid.uuid4())

    batch = UploadBatch(
        batch_id=batch_id,
        profile_id=profile_id,
        created_at=datetime.utcnow(),
        status="uploaded",
        file_count=len(files),
        transaction_count=0,
    )
    db.add(batch)
    await db.flush()

    for file in files:
        content = await file.read()
        fname = file.filename or "upload.bin"
        ext = ("." + fname.rsplit(".", 1)[-1].lower()) if "." in fname else ""
        mime_type = MIME_MAP.get(ext, "application/octet-stream")

        bf = BatchFile(
            id=str(uuid.uuid4()),
            batch_id=batch_id,
            filename=fname,
            mime_type=mime_type,
            content_b64=base64.b64encode(content).decode(),
        )
        db.add(bf)

    await db.commit()

    return UploadResponse(
        batch_id=batch_id,
        file_count=len(files),
        transaction_count=len(files),  # actual count comes from Gemini analysis
        status="uploaded",
        created_at=batch.created_at.isoformat(),
    )
