"""FastAPI application entry point.

Mounts API routes, initializes DB schema, serves health check.
"""
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import DATA_DIR
from backend.db import db as _db
from backend.api.endpoints import repos
from backend.api.endpoints import decisions
from backend.api.endpoints import insights
from backend.api.endpoints import repository
from backend.api.endpoints import archaeology
from backend.api.endpoints import issues


@asynccontextmanager
async def lifespan(app: FastAPI):
    _db.init_schema()
    yield


app = FastAPI(
    title="CausalCode API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(repos.router)
app.include_router(decisions.router)
app.include_router(insights.router)
app.include_router(repository.router)
app.include_router(archaeology.router)
app.include_router(issues.router)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


@app.get("/", include_in_schema=False)
def frontend() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/admin/cleanup")
def cleanup_all():
    """Delete all cloned repos and reset DB. Dev-only."""
    clones = DATA_DIR / "clones"
    if clones.exists():
        shutil.rmtree(clones)
    _db.reset()
    return {"cleaned": True}