"""FastAPI application entry point.

Mounts API routes, initializes DB schema, serves health check.
"""
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import DATA_DIR
from backend.db import db as _db
from backend.api.endpoints import repos
from backend.api.endpoints import decisions


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