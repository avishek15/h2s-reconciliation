# H2S Finance Productivity Agent

> Cross-border finance productivity agent using **FastAPI**, **Google ADK + Gemini**, and a real **Drive MCP** endpoint on **Cloud Run**.

**H2S Track 1 Submission** — Build and deploy an AI system that coordinates agents, tools, and structured data to complete real finance workflows.

---

## What It Does

The app is evolving from statement reconciliation into a finance productivity copilot for freelancers and solopreneurs with multi-bank, multi-currency activity.

Current capabilities:

- username/password app login with profile-scoped data
- Google OAuth connection for profile Drive folders
- Drive-backed statement ingestion and sync
- multi-bank and multi-currency transaction consolidation
- anomaly, recurring-pattern, and narrative analysis via ADK + Gemini
- workflow foundation for monthly review, goal planning, and memory capture
- real Streamable HTTP Drive MCP mounted at `/mcp/drive`

The user-facing goal is simple: users log in through the UI, connect Google Drive once, and then trigger finance actions without handling MCP tokens or API keys.

---

## Architecture

```
GET  /ui                              ← Static app UI
POST /api/v1/auth/signup              ← App signup
POST /api/v1/auth/login               ← App login
POST /api/v1/profiles                 ← Profile creation
GET  /api/v1/auth/google/start        ← Start Google OAuth for Drive
POST /api/v1/workflows/monthly-review ← Workflow shell, Drive-first
POST /api/v1/workflows/goal-planning  ← Persist explicit financial goals
POST /api/v1/workflows/memory-capture ← Persist explicit memory/rules/cash tags
POST /mcp/drive                       ← Streamable HTTP Drive MCP endpoint
```

Drive MCP tools:

- `drive_list_profile_files(profile_id)`
- `drive_sync_profile(profile_id)`
- `drive_get_latest_batch(profile_id)`

Drive MCP resources:

- `drive://profiles/{profile_id}/folder`
- `drive://profiles/{profile_id}/latest-batch`

**Stack:** FastAPI · Google ADK · Gemini · MCP Python SDK / FastMCP · SQLAlchemy · SQLite for smoke deploy · Cloud Run

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

### Try the UI flow

Open:

```bash
open http://localhost:8000/ui
```

Then:

1. Sign up or log in.
2. Create a profile.
3. Connect a Google Drive folder.
4. Sync Drive or run a workflow from the UI.

MCP authentication is intentionally hidden from users. The UI uses the app JWT behind the scenes.

### Try the legacy demo flow

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
  drive.googleapis.com \
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
  --set-env-vars "GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=global,GOOGLE_GENAI_USE_VERTEXAI=TRUE,MODEL=gemini-2.5-flash,APP_ENV=production"
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
  --set-env-vars "GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=global,GOOGLE_GENAI_USE_VERTEXAI=TRUE,MODEL=gemini-2.5-flash,APP_ENV=production"
```

### 6. Configure Google Drive OAuth

After the first deploy, get the service URL:

```bash
export REGION=us-central1
export SERVICE=money-reconciliation-agent
URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')
echo "$URL"
```

In Google Cloud Console:

- Go to `APIs & Services -> OAuth consent screen`.
- Add yourself as a test user if the app is still in testing mode.
- Add the Drive readonly scope:
  - `https://www.googleapis.com/auth/drive.readonly`
- Go to `APIs & Services -> Credentials`.
- Create a `Web application` OAuth client.
- Add this authorized redirect URI:
  - `${URL}/api/v1/auth/google/callback`

Redeploy or update the service with the OAuth settings:

```bash
export GOOGLE_DRIVE_CLIENT_ID="your-oauth-client-id"

gcloud run deploy "$SERVICE" \
  --project "$PROJECT_ID" \
  --source . \
  --platform managed \
  --region "$REGION" \
  --allow-unauthenticated \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --min-instances 1 \
  --max-instances 3 \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=global,GOOGLE_GENAI_USE_VERTEXAI=TRUE,MODEL=gemini-2.5-flash,APP_ENV=production,APP_BASE_URL=${URL},GOOGLE_DRIVE_REDIRECT_URI=${URL}/api/v1/auth/google/callback,GOOGLE_DRIVE_CLIENT_ID=${GOOGLE_DRIVE_CLIENT_ID}"
```

Set `GOOGLE_DRIVE_CLIENT_SECRET` as a secret or env var for testing. Secret Manager is recommended for anything beyond a smoke test.

### 7. Verify

```bash
export REGION=us-central1
export SERVICE=money-reconciliation-agent

URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')
echo "$URL"
curl -sS "${URL}/health"
```

Open `${URL}/docs` for Swagger UI or `${URL}/ui` for the static UI.

Verify the MCP route is deployed:

```bash
curl -sS -i -X POST "${URL}/mcp/drive" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"curl","version":"0.1"}}}'
```

Expected unauthenticated result:

```text
HTTP/2 401
{"error": "invalid_token", "error_description": "Authentication required"}
```

After logging in through the UI or `/api/v1/auth/login`, use the returned app JWT:

```bash
export TOKEN="paste-app-access-token"

curl -sS -X POST "${URL}/mcp/drive" \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25","capabilities":{},"clientInfo":{"name":"curl","version":"0.1"}}}'
```

---

## Environment Variables

| Variable | Description | Local | Cloud Run |
|---|---|---|---|
| `GOOGLE_CLOUD_PROJECT` | GCP project ID (Vertex) | Set in `.env` for the agent | **Required** at deploy (`--set-env-vars`) |
| `GOOGLE_CLOUD_LOCATION` | Vertex region (e.g. `us-central1`) | Optional in `.env` | Set in Dockerfile / deploy vars |
| `GOOGLE_GENAI_USE_VERTEXAI` | Use Vertex AI backend for Gemini | Optional | Set `TRUE` |
| `GOOGLE_API_KEY` | Gemini via AI Studio | Optional; not used by Vertex path in container | Not required when using Vertex image defaults |
| `DATABASE_URL` | SQLite URL | Default file path | Dockerfile sets writable `/tmp/reconciliation.db` |
| `APP_ENV` | `development` or `production` | Optional | Set `production` in deploy |
| `APP_BASE_URL` | Public app URL used by MCP auth metadata | `http://127.0.0.1:8000` | Cloud Run service URL |
| `GOOGLE_DRIVE_CLIENT_ID` | Google OAuth client ID for Drive | Required for Drive connection | Required for Drive connection |
| `GOOGLE_DRIVE_CLIENT_SECRET` | Google OAuth client secret for Drive | Required for Drive connection | Use Secret Manager |
| `GOOGLE_DRIVE_REDIRECT_URI` | OAuth callback URL | Local callback | `${URL}/api/v1/auth/google/callback` |
| `JWT_SECRET_KEY` | App JWT signing secret | Optional for local only | Required; use Secret Manager |
| `MODEL` | Gemini model id | Optional (`agent/money_story_agent.py`) | Optional override |
| `LOG_LEVEL` | Logging verbosity | Optional | Optional |

### Persistence Caveat

The current Cloud Run Dockerfile uses SQLite at `/tmp/reconciliation.db`. This is acceptable for smoke demos, but it is not durable across instance replacement. Use AlloyDB/Postgres before relying on persisted users, profiles, tokens, workflow runs, or transaction history in production.

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
