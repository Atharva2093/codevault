"""Configuration via environment variables (copy .env.example to .env first).

ceiling: analysis and clone paths under CAUSALCODE_DATA_DIR are never cleaned
up automatically by the app; delete them manually when you are done.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
ENV = os.getenv("APP_ENV", "development")
DEBUG = os.getenv("APP_DEBUG", "false").lower() == "true"

# Storage root (SQLite + per-session git clones)
DATA_DIR = Path(os.getenv("CAUSALCODE_DATA_DIR", BASE_DIR / "data"))
DB_PATH = DATA_DIR / "causalcode.db"

# Analysis limits. 200 is a hard ceiling (Phase 1 constraint), not a feature.
MAX_COMMITS_HARD = 200
DEFAULT_MAX_COMMITS = 100

# Product model configuration. The AI client reads the key at request time.
GEMMA_MODEL = os.getenv("GEMMA_MODEL", "gemma-4-26b-a4b-it")
GEMMA_API_KEY = os.getenv("GEMINI_API_KEY")

# GitHub URLs that we are happy to touch. SSH-style git@github.com: URLs are
# accepted too, but no other host is whitelisted in Phase 1.
PUBLIC_GIT_HOSTS = {"github.com", "gitlab.com", "bitbucket.org"}
