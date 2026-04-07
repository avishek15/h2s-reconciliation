import uuid
from datetime import datetime, timezone


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()

from sqlalchemy import (
    Boolean,
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship

from core.config import settings

engine = create_async_engine(settings.database_url, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(100), unique=True, nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    profiles = relationship("Profile", back_populates="user", lazy="select")


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    profile_name = Column(String(100), nullable=False)
    
    # Google Drive credentials (OAuth tokens)
    google_drive_access_token = Column(String(500), nullable=True)
    google_drive_refresh_token = Column(String(500), nullable=True)
    google_drive_folder_id = Column(String(100), nullable=True)
    google_drive_folder_name = Column(String(255), nullable=True)
    
    # Profile metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_synced = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="profiles")
    upload_batches = relationship("UploadBatch", back_populates="profile", lazy="select")
    accounts = relationship("Account", back_populates="profile", lazy="select")
    transactions = relationship("Transaction", back_populates="profile", lazy="select")
    budgets = relationship("Budget", back_populates="profile", lazy="select")
    financial_goals = relationship("FinancialGoal", back_populates="profile", lazy="select")
    memory_facts = relationship("MemoryFact", back_populates="profile", lazy="select")
    categorization_rules = relationship("CategorizationRule", back_populates="profile", lazy="select")
    cash_allocations = relationship("CashAllocation", back_populates="profile", lazy="select")
    recurring_commitments = relationship("RecurringCommitment", back_populates="profile", lazy="select")
    workflow_runs = relationship("WorkflowRun", back_populates="profile", lazy="select")
    tool_sync_states = relationship("ToolSyncState", back_populates="profile", lazy="select")
    agent_instruction_assets = relationship("AgentInstructionAsset", back_populates="profile", lazy="select")


class Account(Base):
    __tablename__ = "accounts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id = Column(String(36), ForeignKey("profiles.id"), nullable=False)
    account_name = Column(String(255), nullable=False)
    institution_name = Column(String(255), nullable=True)
    account_type = Column(String(100), nullable=True)
    currency = Column(String(10), nullable=True)
    external_ref = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    profile = relationship("Profile", back_populates="accounts")
    transactions = relationship("Transaction", back_populates="account", lazy="select")


class UploadBatch(Base):
    __tablename__ = "upload_batches"

    batch_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id = Column(String(36), ForeignKey("profiles.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    status = Column(String(50), default="pending")
    file_count = Column(Integer, default=0)
    transaction_count = Column(Integer, default=0)

    profile = relationship("Profile", back_populates="upload_batches")
    files = relationship("BatchFile", back_populates="batch", lazy="select")
    transactions = relationship("Transaction", back_populates="batch", lazy="select")
    reconciliation_results = relationship("ReconciliationResult", back_populates="batch", lazy="select")
    recurring_patterns = relationship("RecurringPattern", back_populates="batch", lazy="select")
    ai_reports = relationship("AIReport", back_populates="batch", lazy="select")


class BatchFile(Base):
    __tablename__ = "batch_files"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    batch_id = Column(String(36), ForeignKey("upload_batches.batch_id"), nullable=False)
    filename = Column(String(255), nullable=False)
    mime_type = Column(String(100), nullable=False)
    content_b64 = Column(Text, nullable=False)  # base64-encoded raw file bytes

    batch = relationship("UploadBatch", back_populates="files")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    batch_id = Column(String(36), ForeignKey("upload_batches.batch_id"), nullable=False)
    profile_id = Column(String(36), ForeignKey("profiles.id"), nullable=True)
    account_id = Column(String(36), ForeignKey("accounts.id"), nullable=True)
    date = Column(String(20), nullable=False)
    amount = Column(Float, nullable=False)           # USD-converted amount
    original_amount = Column(Float, nullable=True)   # amount in original currency
    original_currency = Column(String(10), nullable=True)  # e.g. HKD, INR, USD
    description = Column(Text, nullable=False)
    clean_name = Column(String(100), nullable=True)   # human-readable merchant name
    category = Column(String(100), nullable=True)
    source_account = Column(String(100), nullable=True)
    transaction_type = Column(String(20), nullable=True)  # debit / credit
    raw_row = Column(Text, nullable=True)
    user_note = Column(Text, nullable=True)

    batch = relationship("UploadBatch", back_populates="transactions")
    profile = relationship("Profile", back_populates="transactions")
    account = relationship("Account", back_populates="transactions")


class Budget(Base):
    __tablename__ = "budgets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id = Column(String(36), ForeignKey("profiles.id"), nullable=False)
    name = Column(String(255), nullable=False)
    scope = Column(String(100), nullable=False)
    category = Column(String(100), nullable=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(10), nullable=False)
    cadence = Column(String(50), nullable=False)
    status = Column(String(50), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    profile = relationship("Profile", back_populates="budgets")


class FinancialGoal(Base):
    __tablename__ = "financial_goals"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id = Column(String(36), ForeignKey("profiles.id"), nullable=False)
    goal_type = Column(String(100), nullable=False)
    title = Column(String(255), nullable=False)
    target_amount = Column(Float, nullable=True)
    currency = Column(String(10), nullable=True)
    cadence = Column(String(50), nullable=True)
    start_date = Column(String(20), nullable=True)
    status = Column(String(50), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    profile = relationship("Profile", back_populates="financial_goals")


class MemoryFact(Base):
    __tablename__ = "memory_facts"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id = Column(String(36), ForeignKey("profiles.id"), nullable=False)
    fact_type = Column(String(100), nullable=False)
    content = Column(Text, nullable=False)
    currency = Column(String(10), nullable=True)
    effective_date = Column(String(20), nullable=True)
    linked_transaction_id = Column(String(36), ForeignKey("transactions.id"), nullable=True)
    status = Column(String(50), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    profile = relationship("Profile", back_populates="memory_facts")


class CategorizationRule(Base):
    __tablename__ = "categorization_rules"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id = Column(String(36), ForeignKey("profiles.id"), nullable=False)
    match_type = Column(String(100), nullable=False)
    match_value = Column(Text, nullable=False)
    category = Column(String(100), nullable=False)
    clean_name = Column(String(100), nullable=True)
    confidence = Column(Float, nullable=True)
    source_memory_fact_id = Column(String(36), ForeignKey("memory_facts.id"), nullable=True)
    status = Column(String(50), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    profile = relationship("Profile", back_populates="categorization_rules")


class CashAllocation(Base):
    __tablename__ = "cash_allocations"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id = Column(String(36), ForeignKey("profiles.id"), nullable=False)
    transaction_id = Column(String(36), ForeignKey("transactions.id"), nullable=False)
    category = Column(String(100), nullable=False)
    amount = Column(Float, nullable=True)
    currency = Column(String(10), nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    profile = relationship("Profile", back_populates="cash_allocations")


class RecurringCommitment(Base):
    __tablename__ = "recurring_commitments"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id = Column(String(36), ForeignKey("profiles.id"), nullable=False)
    name = Column(String(255), nullable=False)
    merchant_pattern = Column(Text, nullable=True)
    amount = Column(Float, nullable=True)
    currency = Column(String(10), nullable=True)
    cadence = Column(String(50), nullable=True)
    next_expected_date = Column(String(20), nullable=True)
    status = Column(String(50), default="active")
    source = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    profile = relationship("Profile", back_populates="recurring_commitments")


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id = Column(String(36), ForeignKey("profiles.id"), nullable=False)
    workflow_type = Column(String(100), nullable=False)
    status = Column(String(50), default="pending")
    user_request = Column(Text, nullable=True)
    result_summary = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    metadata_json = Column("metadata", JSON, nullable=True)

    profile = relationship("Profile", back_populates="workflow_runs")


class ToolSyncState(Base):
    __tablename__ = "tool_sync_state"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id = Column(String(36), ForeignKey("profiles.id"), nullable=False)
    tool_name = Column(String(100), nullable=False)
    connection_status = Column(String(50), default="disconnected")
    external_account_ref = Column(String(255), nullable=True)
    resource_ref = Column(String(255), nullable=True)
    last_synced_at = Column(DateTime, nullable=True)
    sync_cursor = Column(Text, nullable=True)
    metadata_json = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    profile = relationship("Profile", back_populates="tool_sync_states")


class AgentInstructionAsset(Base):
    __tablename__ = "agent_instruction_assets"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id = Column(String(36), ForeignKey("profiles.id"), nullable=False)
    asset_type = Column(String(100), nullable=False)
    title = Column(String(255), nullable=False)
    google_file_id = Column(String(255), nullable=True)
    summary = Column(Text, nullable=True)
    topics = Column(JSON, nullable=True)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    profile = relationship("Profile", back_populates="agent_instruction_assets")


class ReconciliationResult(Base):
    __tablename__ = "reconciliation_results"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    batch_id = Column(String(36), ForeignKey("upload_batches.batch_id"), nullable=False)
    flag_type = Column(String(100), nullable=False)
    severity = Column(String(20), nullable=False)  # HIGH / MEDIUM / LOW
    description = Column(Text, nullable=False)
    transaction_ids = Column(Text, nullable=True)  # JSON array stored as text
    amount_discrepancy = Column(Float, nullable=True)

    batch = relationship("UploadBatch", back_populates="reconciliation_results")


class RecurringPattern(Base):
    __tablename__ = "recurring_patterns"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    batch_id = Column(String(36), ForeignKey("upload_batches.batch_id"), nullable=False)
    description_pattern = Column(Text, nullable=False)
    avg_amount = Column(Float, nullable=False)
    frequency_days = Column(Float, nullable=True)
    frequency_label = Column(String(50), nullable=True)  # weekly / monthly / etc.
    last_seen = Column(String(20), nullable=True)
    next_expected = Column(String(20), nullable=True)
    confidence_score = Column(Float, nullable=True)
    occurrence_count = Column(Integer, default=0)

    batch = relationship("UploadBatch", back_populates="recurring_patterns")


class AIReport(Base):
    __tablename__ = "ai_reports"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    batch_id = Column(String(36), ForeignKey("upload_batches.batch_id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    narrative = Column(Text, nullable=True)  # JSON stored as text
    tokens_used = Column(Integer, nullable=True)

    batch = relationship("UploadBatch", back_populates="ai_reports")


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Ensure existing SQLite schema includes new columns added later
        if engine.dialect.name == "sqlite":
            def _migrate(conn):
                result = conn.execute(text("PRAGMA table_info(upload_batches)"))
                columns = [row[1] for row in result]
                if "profile_id" not in columns:
                    conn.execute(text("ALTER TABLE upload_batches ADD COLUMN profile_id VARCHAR(36)"))
                if "completed_at" not in columns:
                    conn.execute(text("ALTER TABLE upload_batches ADD COLUMN completed_at DATETIME"))

                result = conn.execute(text("PRAGMA table_info(transactions)"))
                columns = [row[1] for row in result]
                if "profile_id" not in columns:
                    conn.execute(text("ALTER TABLE transactions ADD COLUMN profile_id VARCHAR(36)"))
                if "account_id" not in columns:
                    conn.execute(text("ALTER TABLE transactions ADD COLUMN account_id VARCHAR(36)"))
                if "user_note" not in columns:
                    conn.execute(text("ALTER TABLE transactions ADD COLUMN user_note TEXT"))
            await conn.run_sync(_migrate)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
