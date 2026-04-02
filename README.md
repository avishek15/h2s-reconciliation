# Money Reconciliation Agent

> AI-powered personal finance reconciliation using **Google ADK + Gemini**, deployed on **Cloud Run**.

**H2S Track 1 Submission** — Build and deploy an AI agent using ADK, Gemini, and Cloud Run.

---

## What It Does

Upload bank or credit card statements (CSV), and the agent:

1. **Parses & normalizes** transactions from multiple sources
2. **Detects anomalies** — duplicates, large outliers, missing categories
3. **Finds recurring patterns** — subscriptions, regular bills, habits
4. **Generates a financial narrative** via the `MoneyStoryAgent` (ADK + Gemini 2.0 Flash)

The AI agent produces a structured response with:
- Plain-English narrative of the financial period
- Specific, actionable insights with exact dollar amounts
- Prioritized action items (HIGH / MEDIUM / LOW)
- Risk flags that need attention

---

## Architecture

```
POST /api/v1/uploads          ← Upload CSV files
POST /api/v1/pipeline/reconcile ← Detect anomalies & patterns
POST /api/v1/agent/narrative  ← ADK + Gemini analysis ← CORE ENDPOINT
GET  /api/v1/reports/summary  ← Summary metrics
GET  /api/v1/reports/recurring ← Recurring patterns
GET  /api/v1/transactions     ← Paginated transaction list
POST /api/v1/demo/seed        ← Load demo data instantly
```

**Stack:** FastAPI · Google ADK · Gemini 2.0 Flash · SQLite · Cloud Run

---

## Quickstart (Local)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set your Gemini API key
cp .env.example .env
# Edit .env and set GOOGLE_API_KEY=your_key_here

# 3. Run
uvicorn main:app --reload

# 4. Open Swagger UI
open http://localhost:8000/docs
```

### Try the demo flow

```bash
BASE=http://localhost:8000

# Load synthetic demo data
curl -X POST $BASE/api/v1/demo/seed
# → {"batch_id": "uuid-here", ...}

# Run reconciliation
curl -X POST $BASE/api/v1/pipeline/reconcile \
  -H "Content-Type: application/json" \
  -d '{"batch_id": "PASTE_BATCH_ID"}'

# Get AI narrative (calls ADK + Gemini)
curl -X POST $BASE/api/v1/agent/narrative \
  -H "Content-Type: application/json" \
  -d '{"batch_id": "PASTE_BATCH_ID", "query": "Where did my money go and what should I do?"}'
```

---

## Deploy to Cloud Run

### Prerequisites

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com aiplatform.googleapis.com
```

### Deploy (source deploy — no Docker needed locally)

```bash
export PROJECT_ID=your-project-id
export REGION=us-central1
export SERVICE=money-reconciliation-agent

gcloud run deploy $SERVICE \
  --source . \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --min-instances 1 \
  --set-env-vars "GOOGLE_API_KEY=your_gemini_key_here,APP_ENV=production"
```

### Verify

```bash
# Get the service URL
gcloud run services describe $SERVICE --region $REGION --format='value(status.url)'

# Health check
curl https://YOUR_SERVICE_URL.run.app/health
```

---

## Environment Variables

| Variable | Description | Required |
|---|---|---|
| `GOOGLE_API_KEY` | Gemini API key from [AI Studio](https://aistudio.google.com/apikey) | Yes |
| `GOOGLE_CLOUD_PROJECT` | GCP project ID | For Vertex AI |
| `GOOGLE_CLOUD_LOCATION` | Region (default: `us-central1`) | No |
| `DATABASE_URL` | SQLite path (auto-set for Cloud Run) | No |
| `APP_ENV` | `development` or `production` | No |

---

## ADK Agent: MoneyStoryAgent

The core of this submission is `agent/money_story_agent.py` — an ADK `Agent` wrapping Gemini 2.0 Flash with 4 tools:

| Tool | Description |
|---|---|
| `get_summary_metrics` | Total income/expenses, cash flow, top categories |
| `get_reconciliation_flags` | Duplicates, anomalies, missing categories |
| `get_recurring_patterns` | Subscriptions and recurring payment detection |
| `get_period_comparison` | Spending trend vs previous period |

The agent is orchestrated by ADK's `Runner` and `InMemorySessionService`, invoked via `POST /api/v1/agent/narrative`.
