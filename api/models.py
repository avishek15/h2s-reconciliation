from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel


# ── Auth (Login & Registration) ─────────────────────────────────────────────

class SignupRequest(BaseModel):
    username: str
    email: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str


# ── Profile Management ──────────────────────────────────────────────────────

class CreateProfileRequest(BaseModel):
    profile_name: str
    google_drive_folder_id: str
    google_drive_folder_name: str


class ProfileResponse(BaseModel):
    id: str
    profile_name: str
    google_drive_folder_name: Optional[str]
    connected: bool
    created_at: str
    last_synced: Optional[str]


class UserProfilesResponse(BaseModel):
    user_id: str
    username: str
    profiles: list[ProfileResponse]


# ── Upload ──────────────────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    batch_id: str
    file_count: int
    transaction_count: int
    status: str
    created_at: str


# ── Pipeline ────────────────────────────────────────────────────────────────

class ReconcileRequest(BaseModel):
    batch_id: str


class ReconcileResponse(BaseModel):
    batch_id: str
    flags_found: int
    patterns_found: int
    transaction_count: int = 0
    status: str


# ── Agent ───────────────────────────────────────────────────────────────────

class NarrativeRequest(BaseModel):
    batch_id: str
    query: Optional[str] = None


class NarrativeResponse(BaseModel):
    batch_id: str
    report_id: str
    narrative: dict[str, Any]
    created_at: str


# ── Reports ─────────────────────────────────────────────────────────────────

class SummaryReportResponse(BaseModel):
    batch_id: str
    data: dict[str, Any]


class RecurringReportResponse(BaseModel):
    batch_id: str
    data: dict[str, Any]


# ── Transactions ─────────────────────────────────────────────────────────────

class TransactionItem(BaseModel):
    id: str
    date: str
    amount: float                         # USD
    original_amount: Optional[float] = None
    original_currency: Optional[str] = None
    description: str
    clean_name: Optional[str] = None      # human-readable merchant name
    category: Optional[str]
    source_account: Optional[str]
    transaction_type: Optional[str]


class TransactionListResponse(BaseModel):
    batch_id: str
    total: int
    offset: int
    limit: int
    transactions: list[TransactionItem]


# ── Chat ─────────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str   # "user" or "assistant"
    content: str


class ChatRequest(BaseModel):
    batch_id: str
    query: str
    history: list[ChatMessage] = []


class ChatResponse(BaseModel):
    batch_id: str
    response: str


# ── Demo seed ────────────────────────────────────────────────────────────────

class SeedResponse(BaseModel):
    batch_id: str
    transaction_count: int
    message: str
