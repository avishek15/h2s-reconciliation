from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


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
    google_drive_folder_id: Optional[str] = None
    google_drive_folder_name: Optional[str] = None


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


# ── Workflows ────────────────────────────────────────────────────────────────

class WorkflowBaseRequest(BaseModel):
    profile_id: str
    user_request: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MonthlyReviewWorkflowRequest(WorkflowBaseRequest):
    pass


class GoalPlanningWorkflowRequest(WorkflowBaseRequest):
    goal_type: Optional[str] = None
    title: Optional[str] = None
    target_amount: Optional[float] = None
    currency: Optional[str] = None
    cadence: Optional[str] = None
    start_date: Optional[str] = None


class MemoryCaptureWorkflowRequest(WorkflowBaseRequest):
    capture_type: Optional[str] = None
    fact_type: Optional[str] = None
    content: Optional[str] = None
    linked_transaction_id: Optional[str] = None
    match_type: Optional[str] = None
    match_value: Optional[str] = None
    category: Optional[str] = None
    clean_name: Optional[str] = None
    transaction_id: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    description: Optional[str] = None


class WorkflowRunResponse(BaseModel):
    workflow_run_id: str
    profile_id: str
    workflow_type: str
    status: str
    result_summary: Optional[str]
    next_step: str
    started_at: str
    completed_at: Optional[str]
    metadata: dict[str, Any] = Field(default_factory=dict)


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
    #Added fields for health score and insights
    health_score: Optional[int] = None
    health_status: Optional[str] = None
    insights: Optional[list[str]] = None

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
