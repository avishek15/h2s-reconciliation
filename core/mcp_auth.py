from __future__ import annotations

from typing import Optional, Sequence

from fastapi import HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.auth.provider import AccessToken

from core.auth import verify_token as verify_app_token


class AppJwtTokenVerifier:
    """Expose the app's JWTs as MCP bearer tokens."""

    def __init__(self, scopes: Sequence[str]):
        self._scopes = list(scopes)

    async def verify_token(self, token: str) -> Optional[AccessToken]:
        try:
            token_data = verify_app_token(token)
        except HTTPException:
            return None

        return AccessToken(
            token=token,
            client_id=token_data.user_id,
            scopes=self._scopes,
            expires_at=int(token_data.exp.timestamp()),
        )


def current_mcp_user_id() -> str:
    access_token = get_access_token()
    if not access_token:
        raise PermissionError("MCP request is missing a valid bearer token")
    return access_token.client_id
