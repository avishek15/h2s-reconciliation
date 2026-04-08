"""
Routes for Google Drive OAuth and file sync management.
"""

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import HTMLResponse
from sqlalchemy import update, select
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from api.models import ProfileResponse
from core.auth import get_current_user, get_owned_profile
from core.config import settings
from core.database import User, Profile, get_db
from core.google_drive import GoogleDriveOAuthFlow, GoogleDriveService
from core.google_drive_sync import GoogleDriveSyncService

router = APIRouter(tags=["google-drive"])


class GoogleDriveAuthStartResponse(BaseModel):
    authorization_url: str
    state: str


class SyncStatusResponse(BaseModel):
    profile_id: str
    status: str
    message: str


# ── OAuth Flow Routes ───────────────────────────────────────────────────────

@router.get("/auth/google/start")
async def start_google_oauth(
    profile_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Start Google Drive OAuth flow - returns authorization URL.
    """
    # Check if Google Drive credentials are configured
    if not settings.google_drive_client_id or not settings.google_drive_client_secret:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Google Drive OAuth not configured. Please set GOOGLE_DRIVE_CLIENT_ID and GOOGLE_DRIVE_CLIENT_SECRET in your environment.",
        )

    # Verify profile belongs to user
    profile = await get_owned_profile(db, profile_id, current_user.id)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )

    try:
        auth_url, state = GoogleDriveOAuthFlow.get_authorization_url(profile_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OAuth flow error: {str(e)}",
        )
    
    return GoogleDriveAuthStartResponse(
        authorization_url=auth_url,
        state=state,
    )


@router.get("/auth/google/callback")
async def google_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Google OAuth callback - exchange code for tokens and save to profile.
    """
    # Extract profile_id from state
    try:
        profile_id, _, _ = state.split(':', 2)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid state parameter",
        )

    result = await db.execute(
        select(Profile).where(Profile.id == profile_id)
    )
    profile = result.scalar_one_or_none()

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )

    # Exchange code for tokens
    try:
        tokens = await GoogleDriveOAuthFlow.exchange_code_for_tokens(code, state)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to exchange code for tokens: {str(e)}",
        )

    # Update profile with tokens
    await db.execute(
        update(Profile)
        .where(Profile.id == profile_id)
        .values(
            google_drive_access_token=tokens.get("access_token"),
            google_drive_refresh_token=tokens.get("refresh_token"),
        )
    )
    await db.commit()

    # Return HTML page that closes the popup
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Google Drive Connected</title>
        <style>
            body { font-family: Arial, sans-serif; text-align: center; padding: 50px; }
            .success { color: #28a745; font-size: 24px; margin-bottom: 20px; }
        </style>
    </head>
    <body>
        <div class="success">✓ Google Drive Connected Successfully!</div>
        <p>You can now close this window and return to the application.</p>
        <script>
            // Close the window after a short delay
            setTimeout(function() {
                window.close();
            }, 2000);
        </script>
    </body>
    </html>
    """)


# ── File Sync Routes ────────────────────────────────────────────────────────

@router.post("/profiles/{profile_id}/sync", response_model=SyncStatusResponse)
async def sync_profile(
    profile_id: str,
    current_user: User = Depends(get_current_user),
    background_tasks: BackgroundTasks = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Manually trigger file sync from Google Drive for a profile.
    Returns immediately and processes in background.
    """
    # Verify profile belongs to user
    profile = await get_owned_profile(db, profile_id, current_user.id)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )

    if not profile.google_drive_folder_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile is missing a Google Drive folder ID",
        )

    if not profile.google_drive_access_token:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile not connected to Google Drive",
        )

    # Add background task to sync files
    if background_tasks:
        background_tasks.add_task(
            GoogleDriveSyncService.sync_profile_files,
            profile_id,
        )

    return SyncStatusResponse(
        profile_id=profile_id,
        status="syncing",
        message="File sync started in background",
    )


@router.post("/sync-all", response_model=dict)
async def sync_all_profiles(
    current_user: User = Depends(get_current_user),
    background_tasks: BackgroundTasks = None,
):
    """
    Manually trigger file sync for all user profiles.
    Returns immediately and processes in background.
    """
    if background_tasks:
        background_tasks.add_task(GoogleDriveSyncService.sync_all_profiles, current_user.id)

    return {
        "status": "syncing",
        "message": "All profiles sync started in background",
    }


# ── Profile Google Drive Info Routes ────────────────────────────────────────

@router.get("/profiles/{profile_id}/drive-info")
async def get_drive_folder_info(
    profile_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get information about the Google Drive folder for a profile.
    """
    profile = await get_owned_profile(db, profile_id, current_user.id)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )

    if not profile.google_drive_access_token or not profile.google_drive_folder_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile not connected to Google Drive",
        )

    gd_service = GoogleDriveService(profile.google_drive_access_token)
    
    try:
        folder_meta = await gd_service.get_folder_metadata(profile.google_drive_folder_id)
        files = await gd_service.list_files_in_folder(
            profile.google_drive_folder_id,
            GoogleDriveSyncService.SUPPORTED_FILE_TYPES,
        )

        return {
            "folder_id": profile.google_drive_folder_id,
            "folder_name": folder_meta.get("name") if folder_meta else profile.google_drive_folder_name,
            "file_count": len(files),
            "files": files,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to fetch folder info: {str(e)}",
        )
