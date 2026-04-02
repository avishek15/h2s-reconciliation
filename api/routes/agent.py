import asyncio
import json
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from google import genai
from google.genai import types as genai_types

from api.models import ChatRequest, ChatResponse, NarrativeRequest, NarrativeResponse
from core.database import AIReport, Transaction, UploadBatch, get_db
from agent.money_story_agent import run_agent

router = APIRouter()

_project  = os.getenv("GOOGLE_CLOUD_PROJECT")
_location = os.getenv("GOOGLE_CLOUD_LOCATION", "global")
_model    = os.getenv("MODEL", "gemini-2.5-flash")
_client   = genai.Client(vertexai=True, project=_project, location=_location)


@router.post("/narrative", response_model=NarrativeResponse, tags=["agent"])
async def generate_narrative(request: NarrativeRequest, db: AsyncSession = Depends(get_db)):
    """
    Phase 3: Run the MoneyStoryAgent (ADK + Gemini) against the normalized
    transaction data to produce a financial narrative.
    """
    result = await db.execute(
        select(UploadBatch).where(UploadBatch.batch_id == request.batch_id)
    )
    batch = result.scalar_one_or_none()
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch {request.batch_id} not found")

    agent_result = await run_agent(request.batch_id, request.query)

    report_id = str(uuid.uuid4())
    report = AIReport(
        id=report_id,
        batch_id=request.batch_id,
        created_at=datetime.utcnow(),
        narrative=json.dumps(agent_result),
    )
    db.add(report)
    await db.commit()

    return NarrativeResponse(
        batch_id=request.batch_id,
        report_id=report_id,
        narrative=agent_result,
        created_at=report.created_at.isoformat(),
    )


@router.post("/chat", response_model=ChatResponse, tags=["agent"])
async def chat(request: ChatRequest, db: AsyncSession = Depends(get_db)):
    """
    Q&A chat using the full transaction dataset for this session as context.
    Direct Gemini call — no ADK overhead needed for conversational Q&A.
    Session-scoped: only transactions for request.batch_id are included.
    """
    result = await db.execute(
        select(UploadBatch).where(UploadBatch.batch_id == request.batch_id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail=f"Batch {request.batch_id} not found")

    # Load all transactions for this session
    txn_result = await db.execute(
        select(Transaction)
        .where(Transaction.batch_id == request.batch_id)
        .order_by(Transaction.date)
    )
    transactions = txn_result.scalars().all()

    if not transactions:
        return ChatResponse(
            batch_id=request.batch_id,
            response="No transaction data found for this session. Please upload and process your statements first.",
        )

    # Pre-compute authoritative totals so Gemini never re-derives them inconsistently
    total_income   = round(sum(t.amount for t in transactions if t.amount > 0), 2)
    total_expenses = round(abs(sum(t.amount for t in transactions if t.amount < 0)), 2)
    net_cash_flow  = round(total_income - total_expenses, 2)

    # Category breakdown (expenses only, USD)
    from collections import defaultdict
    cat_totals: dict[str, float] = defaultdict(float)
    for t in transactions:
        if t.amount < 0:
            cat_totals[t.category or "Other"] += abs(t.amount)
    top_cats = sorted(cat_totals.items(), key=lambda x: x[1], reverse=True)
    cat_summary = ", ".join(f"{c}: ${round(v,2)}" for c, v in top_cats[:8])

    # Serialize transactions as context
    txn_rows = [
        {
            "date": t.date,
            "description": t.description,
            "amount_usd": round(t.amount, 2),
            "original_amount": t.original_amount,
            "original_currency": t.original_currency or "USD",
            "type": t.transaction_type,
            "category": t.category,
        }
        for t in transactions
    ]
    context = json.dumps(txn_rows, indent=2)

    # Build conversation history block
    history_lines = []
    for msg in request.history:
        prefix = "User" if msg.role == "user" else "Assistant"
        history_lines.append(f"{prefix}: {msg.content}")
    history_block = "\n".join(history_lines)

    prompt = f"""You are a financial assistant for this session. The user has uploaded bank statements from multiple accounts in various currencies (HKD, INR, USD, etc.). All amounts have been converted to USD.

PRE-COMPUTED SUMMARY (authoritative — do not recalculate):
  Total income:   ${total_income}
  Total expenses: ${total_expenses}
  Net cash flow:  ${net_cash_flow}
  Top categories: {cat_summary}

FULL TRANSACTION LIST (this session only, {len(transactions)} transactions):
{context}

{"CONVERSATION HISTORY:" + chr(10) + history_block + chr(10) if history_block else ""}
User: {request.query}

Answer using the pre-computed summary for totals and aggregate questions. Use the full transaction list for specific lookups. Always answer in USD unless asked for original currency. Be concise and direct."""

    def _call():
        return _client.models.generate_content(
            model=_model,
            contents=[genai_types.Part(text=prompt)],
        )

    try:
        resp = await asyncio.to_thread(_call)
        answer = resp.text or "I couldn't generate a response. Please try again."
    except Exception as exc:
        answer = f"Error: {exc}"

    return ChatResponse(batch_id=request.batch_id, response=answer)
