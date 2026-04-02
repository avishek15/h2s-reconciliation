FROM python:3.12-slim

WORKDIR /app

# Install system dependencies needed for some Python packages
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Cloud Run injects PORT env var; default to 8080
ENV PORT=8080
# Use /tmp for SQLite — guaranteed writable on Cloud Run
ENV DATABASE_URL=sqlite+aiosqlite:////tmp/reconciliation.db
# Use Vertex AI backend (authenticates via Cloud Run service account)
ENV GOOGLE_GENAI_USE_VERTEXAI=1
ENV GOOGLE_CLOUD_LOCATION=us-central1

EXPOSE $PORT

# Single worker required for SQLite file consistency
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port $PORT --workers 1"]
