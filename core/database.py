import json
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
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


class UploadBatch(Base):
    __tablename__ = "upload_batches"

    batch_id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    profile_id = Column(String(36), ForeignKey("profiles.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
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

    batch = relationship("UploadBatch", back_populates="transactions")


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
            await conn.run_sync(_migrate)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
