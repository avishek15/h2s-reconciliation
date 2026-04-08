from __future__ import annotations

import json
from typing import Any

from mcp.server.auth.settings import AuthSettings
from mcp.server.fastmcp import FastMCP

from core.auth import get_owned_batch
from core.config import settings
from core.database import AsyncSessionLocal, UploadBatch
from core.health_score import get_batch_health_report
from core.mcp_auth import AppJwtTokenVerifier, current_mcp_user_id


async def _get_owned_batch_for_mcp(batch_id: str) -> UploadBatch:
    user_id = current_mcp_user_id()
    async with AsyncSessionLocal() as db:
        batch = await get_owned_batch(db, batch_id, user_id)
        if not batch:
            raise PermissionError("Batch not found or access denied")
        return batch


async def _get_health_payload(batch_id: str) -> dict[str, Any]:
    _ = await _get_owned_batch_for_mcp(batch_id)
    return await get_batch_health_report(batch_id)


health_mcp = FastMCP(
    name="H2S Finance Health MCP",
    instructions=(
        "Batch-level financial health analysis tools for the H2S finance "
        "productivity agent. All tools require the app JWT bearer token and "
        "enforce batch ownership."
    ),
    host="0.0.0.0",
    mount_path="/mcp/health",
    streamable_http_path="/",
    stateless_http=True,
    json_response=True,
    auth=AuthSettings(
        issuer_url=settings.app_base_url,
        resource_server_url=None,
        required_scopes=["health:read"],
    ),
    token_verifier=AppJwtTokenVerifier(["health:read"]),
)


@health_mcp.tool()
async def get_batch_health(batch_id: str) -> dict[str, Any]:
    """Return the full health report for a transaction batch."""
    return await _get_health_payload(batch_id)


@health_mcp.resource(
    "health://batches/{batch_id}",
    mime_type="application/json",
)
async def health_batch_resource(batch_id: str) -> str:
    """MCP resource for the batch health report."""
    return json.dumps(await _get_health_payload(batch_id))


health_mcp_app = health_mcp.streamable_http_app()
