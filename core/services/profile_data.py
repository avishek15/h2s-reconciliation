from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import (
    Account,
    AgentInstructionAsset,
    Budget,
    CashAllocation,
    CategorizationRule,
    FinancialGoal,
    MemoryFact,
    RecurringCommitment,
    ToolSyncState,
    WorkflowRun,
)


async def get_or_create_account(
    db: AsyncSession,
    *,
    profile_id: str,
    account_name: str,
    currency: Optional[str] = None,
    institution_name: Optional[str] = None,
    account_type: Optional[str] = None,
    external_ref: Optional[str] = None,
) -> Account:
    """Find or stage-create a profile account without committing the transaction."""
    normalized_name = account_name.strip() or "Unknown Account"
    normalized_currency = currency.upper().strip() if currency else None

    query = select(Account).where(Account.profile_id == profile_id)
    if external_ref:
        query = query.where(Account.external_ref == external_ref)
    else:
        query = query.where(Account.account_name == normalized_name)

    result = await db.execute(query.limit(1))
    account = result.scalar_one_or_none()
    if account:
        if normalized_currency and not account.currency:
            account.currency = normalized_currency
        if institution_name and not account.institution_name:
            account.institution_name = institution_name
        if account_type and not account.account_type:
            account.account_type = account_type
        return account

    account = Account(
        profile_id=profile_id,
        account_name=normalized_name,
        institution_name=institution_name,
        account_type=account_type,
        currency=normalized_currency,
        external_ref=external_ref,
    )
    db.add(account)
    await db.flush()
    return account


async def create_budget(
    db: AsyncSession,
    *,
    profile_id: str,
    name: str,
    scope: str,
    amount: float,
    currency: str,
    cadence: str,
    category: Optional[str] = None,
    status: str = "active",
) -> Budget:
    budget = Budget(
        profile_id=profile_id,
        name=name,
        scope=scope,
        category=category,
        amount=amount,
        currency=currency.upper(),
        cadence=cadence,
        status=status,
    )
    db.add(budget)
    await db.flush()
    return budget


async def create_financial_goal(
    db: AsyncSession,
    *,
    profile_id: str,
    goal_type: str,
    title: str,
    target_amount: Optional[float] = None,
    currency: Optional[str] = None,
    cadence: Optional[str] = None,
    start_date: Optional[str] = None,
    status: str = "active",
) -> FinancialGoal:
    goal = FinancialGoal(
        profile_id=profile_id,
        goal_type=goal_type,
        title=title,
        target_amount=target_amount,
        currency=currency.upper() if currency else None,
        cadence=cadence,
        start_date=start_date,
        status=status,
    )
    db.add(goal)
    await db.flush()
    return goal


async def create_memory_fact(
    db: AsyncSession,
    *,
    profile_id: str,
    fact_type: str,
    content: str,
    currency: Optional[str] = None,
    effective_date: Optional[str] = None,
    linked_transaction_id: Optional[str] = None,
    status: str = "active",
) -> MemoryFact:
    fact = MemoryFact(
        profile_id=profile_id,
        fact_type=fact_type,
        content=content,
        currency=currency.upper() if currency else None,
        effective_date=effective_date,
        linked_transaction_id=linked_transaction_id,
        status=status,
    )
    db.add(fact)
    await db.flush()
    return fact


async def create_categorization_rule(
    db: AsyncSession,
    *,
    profile_id: str,
    match_type: str,
    match_value: str,
    category: str,
    clean_name: Optional[str] = None,
    confidence: Optional[float] = None,
    source_memory_fact_id: Optional[str] = None,
    status: str = "active",
) -> CategorizationRule:
    rule = CategorizationRule(
        profile_id=profile_id,
        match_type=match_type,
        match_value=match_value,
        category=category,
        clean_name=clean_name,
        confidence=confidence,
        source_memory_fact_id=source_memory_fact_id,
        status=status,
    )
    db.add(rule)
    await db.flush()
    return rule


async def create_cash_allocation(
    db: AsyncSession,
    *,
    profile_id: str,
    transaction_id: str,
    category: str,
    amount: Optional[float] = None,
    currency: Optional[str] = None,
    description: Optional[str] = None,
) -> CashAllocation:
    allocation = CashAllocation(
        profile_id=profile_id,
        transaction_id=transaction_id,
        category=category,
        amount=amount,
        currency=currency.upper() if currency else None,
        description=description,
    )
    db.add(allocation)
    await db.flush()
    return allocation


async def create_recurring_commitment(
    db: AsyncSession,
    *,
    profile_id: str,
    name: str,
    merchant_pattern: Optional[str] = None,
    amount: Optional[float] = None,
    currency: Optional[str] = None,
    cadence: Optional[str] = None,
    next_expected_date: Optional[str] = None,
    status: str = "active",
    source: Optional[str] = None,
) -> RecurringCommitment:
    commitment = RecurringCommitment(
        profile_id=profile_id,
        name=name,
        merchant_pattern=merchant_pattern,
        amount=amount,
        currency=currency.upper() if currency else None,
        cadence=cadence,
        next_expected_date=next_expected_date,
        status=status,
        source=source,
    )
    db.add(commitment)
    await db.flush()
    return commitment


async def create_workflow_run(
    db: AsyncSession,
    *,
    profile_id: str,
    workflow_type: str,
    user_request: Optional[str] = None,
    metadata_json: Optional[dict[str, Any]] = None,
) -> WorkflowRun:
    workflow_run = WorkflowRun(
        profile_id=profile_id,
        workflow_type=workflow_type,
        status="running",
        user_request=user_request,
        metadata_json=metadata_json,
    )
    db.add(workflow_run)
    await db.flush()
    return workflow_run


def mark_workflow_run_completed(
    workflow_run: WorkflowRun,
    *,
    result_summary: Optional[str] = None,
    metadata_json: Optional[dict[str, Any]] = None,
) -> WorkflowRun:
    workflow_run.status = "completed"
    workflow_run.completed_at = datetime.utcnow()
    workflow_run.result_summary = result_summary
    if metadata_json is not None:
        workflow_run.metadata_json = metadata_json
    return workflow_run


def mark_workflow_run_failed(
    workflow_run: WorkflowRun,
    *,
    result_summary: Optional[str] = None,
    metadata_json: Optional[dict[str, Any]] = None,
) -> WorkflowRun:
    workflow_run.status = "failed"
    workflow_run.completed_at = datetime.utcnow()
    workflow_run.result_summary = result_summary
    if metadata_json is not None:
        workflow_run.metadata_json = metadata_json
    return workflow_run


async def upsert_tool_sync_state(
    db: AsyncSession,
    *,
    profile_id: str,
    tool_name: str,
    connection_status: str,
    external_account_ref: Optional[str] = None,
    resource_ref: Optional[str] = None,
    sync_cursor: Optional[str] = None,
    metadata_json: Optional[dict[str, Any]] = None,
    last_synced_at: Optional[datetime] = None,
) -> ToolSyncState:
    result = await db.execute(
        select(ToolSyncState)
        .where(
            (ToolSyncState.profile_id == profile_id)
            & (ToolSyncState.tool_name == tool_name)
        )
        .limit(1)
    )
    state = result.scalar_one_or_none()

    if not state:
        state = ToolSyncState(profile_id=profile_id, tool_name=tool_name)
        db.add(state)

    state.connection_status = connection_status
    state.external_account_ref = external_account_ref
    state.resource_ref = resource_ref
    state.sync_cursor = sync_cursor
    state.metadata_json = metadata_json
    if last_synced_at is not None:
        state.last_synced_at = last_synced_at

    await db.flush()
    return state


async def create_agent_instruction_asset(
    db: AsyncSession,
    *,
    profile_id: str,
    asset_type: str,
    title: str,
    google_file_id: Optional[str] = None,
    summary: Optional[str] = None,
    topics: Optional[list[str]] = None,
    version: int = 1,
    is_active: bool = True,
) -> AgentInstructionAsset:
    asset = AgentInstructionAsset(
        profile_id=profile_id,
        asset_type=asset_type,
        title=title,
        google_file_id=google_file_id,
        summary=summary,
        topics=topics or [],
        version=version,
        is_active=is_active,
    )
    db.add(asset)
    await db.flush()
    return asset
