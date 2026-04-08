from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.models import (
    GoalPlanningWorkflowRequest,
    MemoryCaptureWorkflowRequest,
    MonthlyReviewWorkflowRequest,
    WorkflowBaseRequest,
    WorkflowRunResponse,
)
from core.auth import get_current_user, get_owned_profile
from core.database import Profile, Transaction, User, WorkflowRun, _iso, get_db
from core.services.profile_data import (
    create_cash_allocation,
    create_categorization_rule,
    create_financial_goal,
    create_memory_fact,
    create_workflow_run,
    mark_workflow_run_completed,
)


router = APIRouter(tags=["workflows"])


def workflow_response(workflow_run: WorkflowRun, *, next_step: str) -> WorkflowRunResponse:
    return WorkflowRunResponse(
        workflow_run_id=workflow_run.id,
        profile_id=workflow_run.profile_id,
        workflow_type=workflow_run.workflow_type,
        status=workflow_run.status,
        result_summary=workflow_run.result_summary,
        next_step=next_step,
        started_at=_iso(workflow_run.started_at),
        completed_at=_iso(workflow_run.completed_at),
        metadata=workflow_run.metadata_json or {},
    )


async def create_workflow_shell(
    *,
    workflow_type: str,
    request: WorkflowBaseRequest,
    next_step: str,
    current_user: User,
    db: AsyncSession,
    metadata: dict[str, Any] | None = None,
    require_drive_connection: bool = False,
) -> tuple[Profile, WorkflowRun]:
    profile = await get_owned_profile(db, request.profile_id, current_user.id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Profile not found or access denied",
        )
    if require_drive_connection and (
        not profile.google_drive_access_token or not profile.google_drive_folder_id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Monthly finance review requires a connected Google Drive folder",
        )

    merged_metadata = {
        "implementation_phase": "milestone_2b_shell",
        "next_step": next_step,
        **(request.metadata or {}),
        **(metadata or {}),
    }

    workflow_run = await create_workflow_run(
        db,
        profile_id=request.profile_id,
        workflow_type=workflow_type,
        user_request=request.user_request,
        metadata_json=merged_metadata,
    )
    workflow_run.status = "pending"
    workflow_run.result_summary = "Workflow shell created. Execution implementation is pending."

    return profile, workflow_run


async def require_profile_transaction(
    *,
    db: AsyncSession,
    profile_id: str,
    transaction_id: str,
) -> Transaction:
    result = await db.execute(
        select(Transaction)
        .where(
            (Transaction.id == transaction_id)
            & (Transaction.profile_id == profile_id)
        )
        .limit(1)
    )
    transaction = result.scalar_one_or_none()
    if not transaction:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found or access denied",
        )
    return transaction


@router.post("/monthly-review", response_model=WorkflowRunResponse)
async def start_monthly_review(
    request: MonthlyReviewWorkflowRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a monthly-review workflow run shell for a profile."""
    next_step = "Wire this run to Drive sync, reconciliation, review note creation, and calendar reminders."
    _, workflow_run = await create_workflow_shell(
        workflow_type="monthly_review",
        request=request,
        next_step=next_step,
        current_user=current_user,
        db=db,
        metadata={"drive_only": True},
        require_drive_connection=True,
    )
    await db.commit()
    await db.refresh(workflow_run)
    return workflow_response(workflow_run, next_step=next_step)


@router.post("/goal-planning", response_model=WorkflowRunResponse)
async def start_goal_planning(
    request: GoalPlanningWorkflowRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a goal-planning workflow run shell for a profile."""
    next_step = "Wire this run to budget retrieval, goal persistence, planning analysis, and reminder creation."
    _, workflow_run = await create_workflow_shell(
        workflow_type="goal_planning",
        request=request,
        next_step=next_step,
        current_user=current_user,
        db=db,
        metadata={
            "goal_type": request.goal_type,
            "title": request.title,
            "target_amount": request.target_amount,
            "currency": request.currency,
            "cadence": request.cadence,
            "start_date": request.start_date,
        },
    )

    if request.goal_type and request.title:
        goal = await create_financial_goal(
            db,
            profile_id=request.profile_id,
            goal_type=request.goal_type,
            title=request.title,
            target_amount=request.target_amount,
            currency=request.currency,
            cadence=request.cadence,
            start_date=request.start_date,
        )
        metadata = dict(workflow_run.metadata_json or {})
        metadata["created_resources"] = [
            {"type": "financial_goal", "id": goal.id, "title": goal.title}
        ]
        mark_workflow_run_completed(
            workflow_run,
            result_summary=f"Stored financial goal: {goal.title}",
            metadata_json=metadata,
        )

    await db.commit()
    await db.refresh(workflow_run)
    return workflow_response(workflow_run, next_step=next_step)


@router.post("/memory-capture", response_model=WorkflowRunResponse)
async def start_memory_capture(
    request: MemoryCaptureWorkflowRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a memory-capture workflow run shell for a profile."""
    next_step = "Wire this run to explicit memory fact writes, categorization rules, and cash allocations."
    _, workflow_run = await create_workflow_shell(
        workflow_type="memory_capture",
        request=request,
        next_step=next_step,
        current_user=current_user,
        db=db,
        metadata={
            "capture_type": request.capture_type,
            "fact_type": request.fact_type,
            "content": request.content,
            "linked_transaction_id": request.linked_transaction_id,
            "match_type": request.match_type,
            "match_value": request.match_value,
            "category": request.category,
            "clean_name": request.clean_name,
            "transaction_id": request.transaction_id,
            "amount": request.amount,
            "currency": request.currency,
            "description": request.description,
        },
    )

    created_resources = []
    memory_fact_id = None

    if request.linked_transaction_id:
        await require_profile_transaction(
            db=db,
            profile_id=request.profile_id,
            transaction_id=request.linked_transaction_id,
        )

    if request.fact_type and request.content:
        fact = await create_memory_fact(
            db,
            profile_id=request.profile_id,
            fact_type=request.fact_type,
            content=request.content,
            currency=request.currency,
            linked_transaction_id=request.linked_transaction_id,
        )
        memory_fact_id = fact.id
        created_resources.append({"type": "memory_fact", "id": fact.id})

    if request.match_type and request.match_value and request.category:
        rule = await create_categorization_rule(
            db,
            profile_id=request.profile_id,
            match_type=request.match_type,
            match_value=request.match_value,
            category=request.category,
            clean_name=request.clean_name,
            confidence=1.0,
            source_memory_fact_id=memory_fact_id,
        )
        created_resources.append({"type": "categorization_rule", "id": rule.id})

    if request.transaction_id and request.category:
        await require_profile_transaction(
            db=db,
            profile_id=request.profile_id,
            transaction_id=request.transaction_id,
        )
        allocation = await create_cash_allocation(
            db,
            profile_id=request.profile_id,
            transaction_id=request.transaction_id,
            category=request.category,
            amount=request.amount,
            currency=request.currency,
            description=request.description or request.content,
        )
        created_resources.append({"type": "cash_allocation", "id": allocation.id})

    if created_resources:
        metadata = dict(workflow_run.metadata_json or {})
        metadata["created_resources"] = created_resources
        mark_workflow_run_completed(
            workflow_run,
            result_summary=f"Stored {len(created_resources)} memory resource(s).",
            metadata_json=metadata,
        )

    await db.commit()
    await db.refresh(workflow_run)
    return workflow_response(workflow_run, next_step=next_step)
