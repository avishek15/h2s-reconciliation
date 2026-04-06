from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()

from core.database import init_db
from core.drive_mcp import drive_mcp, drive_mcp_app
from api.routes import (
    uploads,
    pipeline,
    reports,
    agent,
    transactions,
    demo,
    admin,
    auth,
    google_drive,
    workflows,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    async with drive_mcp.session_manager.run():
        yield


app = FastAPI(
    title="Money Reconciliation Agent",
    description=(
        "AI-powered personal finance reconciliation using Google ADK + Gemini. "
        "Upload bank statements, detect anomalies, identify subscriptions, and get "
        "an AI-generated financial narrative with actionable recommendations."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(uploads.router, prefix="/api/v1")
app.include_router(google_drive.router, prefix="/api/v1")
app.include_router(workflows.router, prefix="/api/v1/workflows")
app.include_router(pipeline.router, prefix="/api/v1/pipeline")
app.include_router(reports.router, prefix="/api/v1/reports")
app.include_router(agent.router, prefix="/api/v1/agent")
app.include_router(transactions.router, prefix="/api/v1")
app.include_router(demo.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1/admin")

app.mount("/mcp", drive_mcp_app)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/ui", include_in_schema=False)
async def ui():
    return FileResponse("static/index.html")


@app.get("/health", tags=["system"])
async def health():
    return {"status": "ok", "service": "money-reconciliation-agent", "version": "1.0.0"}


@app.get("/", tags=["system"])
async def root():
    return {
        "service": "Money Reconciliation Agent",
        "description": "AI financial analysis powered by Google ADK + Gemini",
        "docs": "/docs",
        "health": "/health",
        "quickstart": {
            "step_1": "POST /api/v1/demo/seed  → get a batch_id with demo data",
            "step_2": "POST /api/v1/pipeline/reconcile  → detect anomalies and patterns",
            "step_3": "POST /api/v1/agent/narrative  → get AI financial analysis",
            "step_4": "GET  /api/v1/reports/summary?batch_id=...  → view metrics",
        },
    }
