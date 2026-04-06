import json
from typing import Any, Optional

from fastapi import HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP
from sqlalchemy import select

from core.auth import get_owned_profile, verify_token as verify_app_token
from core.config import settings
from core.database import AsyncSessionLocal, Profile, UploadBatch
from core.google_drive import GoogleDriveService
from core.google_drive_sync import GoogleDriveSyncService


class AppJwtTokenVerifier:
    """Expose the app's JWTs as MCP bearer tokens."""

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        try:
            token_data = verify_app_token(token)
        except HTTPException:
            return None

        return AccessToken(
            token=token,
            client_id=token_data.user_id,
            scopes=["drive:read", "drive:sync"],
            expires_at=int(token_data.exp.timestamp()),
        )


def _current_mcp_user_id() -> str:
    access_token = get_access_token()
    if not access_token:
        raise PermissionError("MCP request is missing a valid bearer token")
    return access_token.client_id


async def _get_owned_drive_profile(profile_id: str) -> Profile:
    user_id = _current_mcp_user_id()
    async with AsyncSessionLocal() as db:
        profile = await get_owned_profile(db, profile_id, user_id)
        if not profile:
            raise PermissionError("Profile not found or access denied")
        if not profile.google_drive_access_token or not profile.google_drive_folder_id:
            raise ValueError("Profile is not connected to Google Drive")
        return profile


async def _latest_batch_payload(profile_id: str) -> dict[str, Any]:
    user_id = _current_mcp_user_id()
    async with AsyncSessionLocal() as db:
        profile = await get_owned_profile(db, profile_id, user_id)
        if not profile:
            raise PermissionError("Profile not found or access denied")

        result = await db.execute(
            select(UploadBatch)
            .where(UploadBatch.profile_id == profile_id)
            .order_by(UploadBatch.created_at.desc())
            .limit(1)
        )
        batch = result.scalar_one_or_none()

    if not batch:
        return {
            "status": "not_found",
            "profile_id": profile_id,
            "message": "No Drive sync batches found for this profile",
        }

    return {
        "status": "found",
        "profile_id": profile_id,
        "batch_id": batch.batch_id,
        "batch_status": batch.status,
        "file_count": batch.file_count,
        "transaction_count": batch.transaction_count,
        "created_at": batch.created_at.isoformat() if batch.created_at else None,
    }


drive_mcp = FastMCP(
    name="H2S Finance Drive MCP",
    instructions=(
        "Drive-backed statement ingestion tools for the H2S finance productivity "
        "agent. All tools require the app JWT bearer token and enforce profile ownership."
    ),
    host="0.0.0.0",
    streamable_http_path="/drive",
    stateless_http=True,
    json_response=True,
    auth=AuthSettings(
        issuer_url=settings.app_base_url,
        resource_server_url=None,
        required_scopes=["drive:read"],
    ),
    token_verifier=AppJwtTokenVerifier(),
)


@drive_mcp.tool()
async def drive_list_profile_files(profile_id: str) -> dict[str, Any]:
    """List supported statement files in the profile's connected Drive folder."""
    profile = await _get_owned_drive_profile(profile_id)
    drive = GoogleDriveService(
        profile.google_drive_access_token,
        profile.google_drive_refresh_token,
    )

    folder_meta = await drive.get_folder_metadata(profile.google_drive_folder_id)
    files = await drive.list_files_in_folder(
        profile.google_drive_folder_id,
        GoogleDriveSyncService.SUPPORTED_FILE_TYPES,
    )
    return {
        "status": "ok",
        "profile_id": profile_id,
        "folder_id": profile.google_drive_folder_id,
        "folder_name": (
            folder_meta.get("name")
            if folder_meta
            else profile.google_drive_folder_name
        ),
        "file_count": len(files),
        "supported_file_types": GoogleDriveSyncService.SUPPORTED_FILE_TYPES,
        "files": files,
    }


@drive_mcp.tool()
async def drive_sync_profile(profile_id: str) -> dict[str, Any]:
    """Sync the profile's Drive folder and start reconciliation for the synced batch."""
    _ = await _get_owned_drive_profile(profile_id)
    sync_result = await GoogleDriveSyncService.sync_profile_files(profile_id)
    return sync_result or {
        "status": "unknown",
        "profile_id": profile_id,
        "message": "Drive sync finished without a result payload",
    }


@drive_mcp.tool()
async def drive_get_latest_batch(profile_id: str) -> dict[str, Any]:
    """Return the latest Drive-created batch for a profile."""
    return await _latest_batch_payload(profile_id)


@drive_mcp.resource(
    "drive://profiles/{profile_id}/folder",
    mime_type="application/json",
)
async def drive_profile_folder_resource(profile_id: str) -> str:
    """MCP resource for the profile Drive folder and supported statement files."""
    return json.dumps(await drive_list_profile_files(profile_id))


@drive_mcp.resource(
    "drive://profiles/{profile_id}/latest-batch",
    mime_type="application/json",
)
async def drive_latest_batch_resource(profile_id: str) -> str:
    """MCP resource for the latest Drive sync batch."""
    return json.dumps(await _latest_batch_payload(profile_id))


drive_mcp_app = drive_mcp.streamable_http_app()
