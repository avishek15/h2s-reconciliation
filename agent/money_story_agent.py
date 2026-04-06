"""
MoneyStoryAgent — ADK + Gemini agent for financial analysis.
Reads real transaction data from the DB (populated by the normalization pipeline)
via four tools and synthesizes a structured financial narrative.
"""
import json
import os
import re
from typing import Optional, Callable

from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types as genai_types
from sqlalchemy.ext.asyncio import AsyncSession

from agent.tools.summary_metrics import get_summary_metrics
from agent.tools.reconciliation_flags import get_reconciliation_flags
from agent.tools.recurring_patterns import get_recurring_patterns
from agent.tools.period_comparison import get_period_comparison

model_id   = os.getenv("MODEL", "gemini-2.5-flash")

AGENT_INSTRUCTION = """
You are MoneyStoryAgent, an expert AI financial analyst. Your job is to analyze
personal and small business transaction data and produce clear, actionable
financial narratives.

When you receive a request to analyze a batch_id, call ALL four tools in order:
1. get_summary_metrics(batch_id)    — overall income / expenses / categories
2. get_reconciliation_flags(batch_id) — anomalies and issues
3. get_recurring_patterns(batch_id)   — subscriptions and habits
4. get_period_comparison(batch_id)    — spending trends

After collecting ALL tool results, synthesize them into a single JSON response
with EXACTLY these keys:

{
  "narrative": "2-3 paragraph plain English story. Lead with net cash flow, then spending patterns, then concerns.",
  "insights": ["3-5 specific insights with exact dollar amounts and percentages"],
  "action_items": [
    {"priority": "HIGH",   "action": "Specific recommended action with amount"},
    {"priority": "MEDIUM", "action": "Another recommendation"},
    {"priority": "LOW",    "action": "Nice-to-have action"}
  ],
  "risk_flags": ["Specific risk issues from reconciliation flags, each as a plain string with amount and description"],
  "summary_stats": {
    "total_income": 0.0,
    "total_expenses": 0.0,
    "net_cash_flow": 0.0,
    "savings_rate_pct": 0.0,
    "subscription_monthly_cost": 0.0,
    "largest_expense_category": "string",
    "spending_trend": "up/down/stable"
  }
}

CRITICAL RULES:
- Respond with RAW JSON ONLY. No markdown. No code blocks. No text outside the JSON.
- risk_flags must be an array of STRINGS, not objects.
- Be specific with numbers. Reference actual dollar amounts from tool results.
- If a tool returns an error, note it but proceed with available data.
"""


def create_money_story_agent() -> Agent:
    return Agent(
        name="MoneyStoryAgent",
        model=model_id,
        description="Analyzes financial transactions and produces reconciliation narratives",
        instruction=AGENT_INSTRUCTION,
        tools=[
            get_summary_metrics,
            get_reconciliation_flags,
            get_recurring_patterns,
            get_period_comparison,
        ],
    )


async def run_agent(
    batch_id: str,
    user_query: str | None = None,
    db: Optional[AsyncSession] = None,
    status_callback: Optional[Callable[[str], None]] = None,
) -> dict:
    """
    Run the MoneyStoryAgent for a given batch.
    
    Args:
        batch_id: Batch ID to analyze
        user_query: Optional custom query/prompt
        db: Optional database session (for future extensions)
        status_callback: Optional callback for status updates
    
    Returns:
        dict: Agent response with narrative, insights, actions, risk_flags, summary_stats
    """
    agent = create_money_story_agent()
    session_service = InMemorySessionService()

    runner = Runner(
        agent=agent,
        app_name="money-reconciliation",
        session_service=session_service,
    )

    session = await session_service.create_session(
        app_name="money-reconciliation",
        user_id="api_user",
    )

    base = f"Analyze financial transactions for batch_id: {batch_id}."
    prompt = f"{base} {user_query}" if user_query else (
        f"{base} Call all tools and give me a complete financial story with insights and action items."
    )

    message = genai_types.Content(
        role="user",
        parts=[genai_types.Part(text=prompt)],
    )

    final_response = None
    async for event in runner.run_async(
        user_id="api_user",
        session_id=session.id,
        new_message=message,
    ):
        if event.is_final_response():
            if event.content and event.content.parts:
                final_response = event.content.parts[0].text
            break

    if not final_response:
        return {
            "narrative": "Agent did not produce a response. Please try again.",
            "insights": [],
            "action_items": [],
            "risk_flags": [],
            "summary_stats": {},
            "error": "No response from agent",
        }

    try:
        return json.loads(final_response)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", final_response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return {
            "narrative": final_response,
            "insights": [],
            "action_items": [],
            "risk_flags": [],
            "summary_stats": {},
            "raw_response": True,
        }
