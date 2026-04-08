from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import Profile, UploadBatch, User, get_db


# ── Models ──────────────────────────────────────────────────────────────────

class TokenData(BaseModel):
    user_id: str
    username: str
    exp: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str


# ── Password Hashing ───────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a password against a hash."""
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


# ── JWT Token Management ────────────────────────────────────────────────────

def create_access_token(user_id: str, username: str) -> str:
    """Create a JWT access token."""
    exp = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expiration_hours)
    payload = {
        "user_id": user_id,
        "username": username,
        "exp": exp.timestamp(),
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token


def verify_token(token: str) -> TokenData:
    """Verify and decode a JWT token."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        user_id = payload.get("user_id")
        username = payload.get("username")
        exp_timestamp = payload.get("exp")

        if user_id is None or username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

        exp = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
        return TokenData(user_id=user_id, username=username, exp=exp)
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
        )


# ── Dependency: Current User ────────────────────────────────────────────────

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Dependency to get the current authenticated user from JWT token."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing",
        )
    
    token = credentials.credentials
    token_data = verify_token(token)

    result = await db.execute(
        select(User).where(User.id == token_data.user_id)
    )
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    return user


async def get_owned_profile(db: AsyncSession, profile_id: str, user_id: str) -> Optional[Profile]:
    """Return a profile only if it belongs to the given user."""
    result = await db.execute(
        select(Profile).where(
            (Profile.id == profile_id) & (Profile.user_id == user_id)
        )
    )
    return result.scalar_one_or_none()


async def get_owned_batch(db: AsyncSession, batch_id: str, user_id: str) -> Optional[UploadBatch]:
    """Return a batch only if it belongs to one of the user's profiles."""
    result = await db.execute(
        select(UploadBatch)
        .join(Profile, UploadBatch.profile_id == Profile.id)
        .where(
            (UploadBatch.batch_id == batch_id) & (Profile.user_id == user_id)
        )
    )
    return result.scalar_one_or_none()
