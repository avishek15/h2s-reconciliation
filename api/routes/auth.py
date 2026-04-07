from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import (
    AuthResponse,
    CreateProfileRequest,
    LoginRequest,
    ProfileResponse,
    SignupRequest,
    UserProfilesResponse,
)
from core.auth import (
    create_access_token,
    get_current_user,
    get_owned_profile,
    hash_password,
    verify_password,
)
from core.database import (
    AIReport,
    Account,
    AgentInstructionAsset,
    BatchFile,
    Budget,
    CashAllocation,
    CategorizationRule,
    FinancialGoal,
    MemoryFact,
    Profile,
    ReconciliationResult,
    RecurringCommitment,
    RecurringPattern,
    ToolSyncState,
    Transaction,
    UploadBatch,
    User,
    WorkflowRun,
    get_db,
)

router = APIRouter(tags=["auth"])


# ── Authentication Routes ───────────────────────────────────────────────────

@router.post("/auth/signup", response_model=AuthResponse)
async def signup(request: SignupRequest, db: AsyncSession = Depends(get_db)):
    """
    Register a new user with username, email, and password.
    """
    # Check if user already exists
    result = await db.execute(
        select(User).where(
            (User.username == request.username) | (User.email == request.email)
        )
    )
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username or email already exists",
        )

    # Create new user
    user = User(
        username=request.username,
        email=request.email,
        password_hash=hash_password(request.password),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    # Generate token
    access_token = create_access_token(user.id, user.username)

    return AuthResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=user.id,
        username=user.username,
    )


@router.post("/auth/login", response_model=AuthResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """
    Authenticate with username and password, returns JWT token.
    """
    result = await db.execute(
        select(User).where(
            (User.username == request.username) | (User.email == request.username)
        )
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Generate token
    access_token = create_access_token(user.id, user.username)

    return AuthResponse(
        access_token=access_token,
        token_type="bearer",
        user_id=user.id,
        username=user.username,
    )


# ── Profile Management Routes ───────────────────────────────────────────────

@router.post("/profiles", response_model=ProfileResponse)
async def create_profile(
    request: CreateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new profile with Google Drive folder information.
    """
    profile_name = request.profile_name.strip()
    folder_id = (request.google_drive_folder_id or "").strip() or None
    folder_name = (request.google_drive_folder_name or "").strip() or None

    if not profile_name:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Profile name is required",
        )

    if bool(folder_id) != bool(folder_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide both Google Drive folder ID and folder name, or leave both blank",
        )

    profile = Profile(
        user_id=current_user.id,
        profile_name=profile_name,
        google_drive_folder_id=folder_id,
        google_drive_folder_name=folder_name,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)

    return ProfileResponse(
        id=profile.id,
        profile_name=profile.profile_name,
        google_drive_folder_name=profile.google_drive_folder_name,
        connected=profile.google_drive_access_token is not None,
        created_at=profile.created_at.isoformat(),
        last_synced=profile.last_synced.isoformat() if profile.last_synced else None,
    )


@router.get("/profiles", response_model=UserProfilesResponse)
async def get_profiles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all profiles for the current user.
    """
    result = await db.execute(
        select(Profile).where(Profile.user_id == current_user.id)
    )
    profiles = result.scalars().all()

    profile_responses = [
        ProfileResponse(
            id=p.id,
            profile_name=p.profile_name,
            google_drive_folder_name=p.google_drive_folder_name,
            connected=p.google_drive_access_token is not None,
            created_at=p.created_at.isoformat(),
            last_synced=p.last_synced.isoformat() if p.last_synced else None,
        )
        for p in profiles
    ]

    return UserProfilesResponse(
        user_id=current_user.id,
        username=current_user.username,
        profiles=profile_responses,
    )


@router.get("/profiles/{profile_id}", response_model=ProfileResponse)
async def get_profile(
    profile_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a specific profile by ID (only if owned by current user).
    """
    profile = await get_owned_profile(db, profile_id, current_user.id)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )

    return ProfileResponse(
        id=profile.id,
        profile_name=profile.profile_name,
        google_drive_folder_name=profile.google_drive_folder_name,
        connected=profile.google_drive_access_token is not None,
        created_at=profile.created_at.isoformat(),
        last_synced=profile.last_synced.isoformat() if profile.last_synced else None,
    )


@router.get("/me", response_model=UserProfilesResponse)
async def get_current_user_info(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current user info with all their profiles.
    """
    result = await db.execute(
        select(Profile).where(Profile.user_id == current_user.id)
    )
    profiles = result.scalars().all()

    profile_responses = [
        ProfileResponse(
            id=p.id,
            profile_name=p.profile_name,
            google_drive_folder_name=p.google_drive_folder_name,
            connected=p.google_drive_access_token is not None,
            created_at=p.created_at.isoformat(),
            last_synced=p.last_synced.isoformat() if p.last_synced else None,
        )
        for p in profiles
    ]

    return UserProfilesResponse(
        user_id=current_user.id,
        username=current_user.username,
        profiles=profile_responses,
    )


@router.get("/profiles/{profile_id}/latest-batch")
async def get_latest_batch_for_profile(
    profile_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the latest batch for a profile (only if owned by current user).
    """
    # Verify profile belongs to user
    profile = await get_owned_profile(db, profile_id, current_user.id)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )

    # Get latest batch for profile
    batch_result = await db.execute(
        select(UploadBatch)
        .where(UploadBatch.profile_id == profile_id)
        .order_by(UploadBatch.created_at.desc())
        .limit(1)
    )
    batch = batch_result.scalar_one_or_none()

    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No batches found for this profile",
        )

    return {
        "batch_id": batch.batch_id,
        "status": batch.status,
        "file_count": batch.file_count,
        "transaction_count": batch.transaction_count,
        "created_at": batch.created_at.isoformat(),
        "completed_at": batch.completed_at.isoformat() if batch.completed_at else None,
    }


@router.delete("/profiles/{profile_id}")
async def delete_profile(
    profile_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a profile and all associated batch data for the current user.
    """
    profile = await get_owned_profile(db, profile_id, current_user.id)

    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found",
        )

    batch_ids_result = await db.execute(
        select(UploadBatch.batch_id).where(UploadBatch.profile_id == profile_id)
    )
    batch_ids = [row[0] for row in batch_ids_result.all()]

    await db.execute(delete(CashAllocation).where(CashAllocation.profile_id == profile_id))
    await db.execute(
        delete(CategorizationRule).where(CategorizationRule.profile_id == profile_id)
    )
    await db.execute(delete(MemoryFact).where(MemoryFact.profile_id == profile_id))
    await db.execute(delete(FinancialGoal).where(FinancialGoal.profile_id == profile_id))
    await db.execute(delete(Budget).where(Budget.profile_id == profile_id))
    await db.execute(
        delete(RecurringCommitment).where(RecurringCommitment.profile_id == profile_id)
    )
    await db.execute(delete(WorkflowRun).where(WorkflowRun.profile_id == profile_id))
    await db.execute(delete(ToolSyncState).where(ToolSyncState.profile_id == profile_id))
    await db.execute(
        delete(AgentInstructionAsset).where(AgentInstructionAsset.profile_id == profile_id)
    )

    if batch_ids:
        await db.execute(delete(AIReport).where(AIReport.batch_id.in_(batch_ids)))
        await db.execute(
            delete(ReconciliationResult).where(
                ReconciliationResult.batch_id.in_(batch_ids)
            )
        )
        await db.execute(
            delete(RecurringPattern).where(RecurringPattern.batch_id.in_(batch_ids))
        )
        await db.execute(delete(Transaction).where(Transaction.batch_id.in_(batch_ids)))
        await db.execute(delete(BatchFile).where(BatchFile.batch_id.in_(batch_ids)))
        await db.execute(delete(UploadBatch).where(UploadBatch.batch_id.in_(batch_ids)))

    await db.execute(delete(Transaction).where(Transaction.profile_id == profile_id))
    await db.execute(delete(Account).where(Account.profile_id == profile_id))

    await db.execute(delete(Profile).where(Profile.id == profile_id))
    await db.commit()

    return {
        "status": "deleted",
        "profile_id": profile_id,
        "message": "Profile and associated data deleted",
    }
