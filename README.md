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

## Deploy to Google Cloud Run (CLI)

The container image is built for **Vertex AI** (see `Dockerfile`: `GOOGLE_GENAI_USE_VERTEXAI=1`, SQLite under `/tmp`). The `MoneyStoryAgent` uses `google.genai` with `vertexai=True`, so the Cloud Run service account must be allowed to call Vertex AI and `GOOGLE_CLOUD_PROJECT` must be set at deploy time.

### 1. Prerequisites

Install the [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) and authenticate:

```bash
gcloud auth login
gcloud auth application-default login   # optional; helps local Vertex / ADC tooling
gcloud config set project YOUR_PROJECT_ID
```

Replace `YOUR_PROJECT_ID` with your GCP project ID (`gcloud projects list`).

### 2. Enable APIs (one time per project)

```bash
export PROJECT_ID=$(gcloud config get-value project)

gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  aiplatform.googleapis.com \
  --project "$PROJECT_ID"
```

### 3. Grant Vertex AI access to the Cloud Run runtime (one time)

Cloud Run defaults to the Compute Engine default service account. It needs permission to use Vertex AI:

```bash
export PROJECT_ID=$(gcloud config get-value project)
export PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')
export RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/aiplatform.user"
```

If you deploy with `--service-account`, grant `roles/aiplatform.user` to **that** account instead.

### 4. Deploy from source (recommended)

From the **repository root** (same directory as `Dockerfile`). Cloud Build will build the image (using `Dockerfile` when present) and deploy to Cloud Run:

```bash
export PROJECT_ID=$(gcloud config get-value project)
export REGION=us-central1
export SERVICE=money-reconciliation-agent

gcloud run deploy "$SERVICE" \
  --project "$PROJECT_ID" \
  --source . \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --min-instances 0 \
  --max-instances 10 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=us-central1,APP_ENV=production"
```

- Use `--min-instances 1` if you want to avoid cold starts (adds cost).
- Omit `--allow-unauthenticated` if you only want IAM-authenticated access; then callers need a Google identity + `roles/run.invoker`.

### 5. Deploy a pre-built image (optional)

Use this when you want an explicit image tag in Artifact Registry (e.g. CI/CD):

```bash
export PROJECT_ID=$(gcloud config get-value project)
export REGION=us-central1
export SERVICE=money-reconciliation-agent
export REPO=h2s-reconciliation
export IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}/${SERVICE}:$(git rev-parse --short HEAD 2>/dev/null || echo manual)"

gcloud artifacts repositories describe "$REPO" --location "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1 || \
  gcloud artifacts repositories create "$REPO" \
    --repository-format=docker \
    --location "$REGION" \
    --project "$PROJECT_ID" \
    --description="Images for ${SERVICE}"

gcloud builds submit --project "$PROJECT_ID" --tag "$IMAGE" .

gcloud run deploy "$SERVICE" \
  --project "$PROJECT_ID" \
  --image "$IMAGE" \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=us-central1,APP_ENV=production"
```

### 6. Verify

```bash
export REGION=us-central1
export SERVICE=money-reconciliation-agent

URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')
echo "$URL"
curl -sS "${URL}/health"
```

Open `${URL}/docs` for Swagger UI or `${URL}/ui` for the static UI.

---

## Environment Variables

| Variable | Description | Local | Cloud Run |
|---|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | GCP project ID (Vertex) | Set in `.env` for the agent | **Required** at deploy (`--set-env-vars`) |
| `GOOGLE_CLOUD_LOCATION` | Vertex region (e.g. `us-central1`) | Optional in `.env` | Set in Dockerfile / deploy vars |
| `GOOGLE_API_KEY` | Gemini via AI Studio | Optional; not used by Vertex path in container | Not required when using Vertex image defaults |
| `DATABASE_URL` | SQLite URL | Default file path | Dockerfile sets writable `/tmp/reconciliation.db` |
| `APP_ENV` | `development` or `production` | Optional | Set `production` in deploy |
| `MODEL` | Gemini model id | Optional (`agent/money_story_agent.py`) | Optional override |
| `LOG_LEVEL` | Logging verbosity | Optional | Optional |

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
