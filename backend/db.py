"""SQLite persistence level.

Minimal, no ORM. One schema, parameterized queries everywhere.
"""
import os
import shutil
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from .config import DB_PATH


SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    repo_url TEXT NOT NULL,
    repo_name TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    max_commits INTEGER NOT NULL,
    analyzed_commits INTEGER NOT NULL DEFAULT 0,
    clone_path TEXT,
    error TEXT
);

CREATE TABLE IF NOT EXISTS commits (
    session_id TEXT NOT NULL,
    commit_hash TEXT NOT NULL,
    author_name TEXT,
    author_email TEXT,
    timestamp TEXT NOT NULL,
    message TEXT,
    parent_hashes TEXT,
    change_type TEXT,
    PRIMARY KEY (session_id, commit_hash),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS file_changes (
    session_id TEXT NOT NULL,
    commit_hash TEXT NOT NULL,
    path TEXT NOT NULL,
    status TEXT NOT NULL,
    additions INTEGER NOT NULL,
    deletions INTEGER NOT NULL,
    FOREIGN KEY (session_id, commit_hash) REFERENCES commits(session_id, commit_hash)
);

CREATE TABLE IF NOT EXISTS dependency_events (
    session_id TEXT NOT NULL,
    commit_hash TEXT NOT NULL,
    dep_name TEXT NOT NULL,
    kind TEXT NOT NULL,
    manifest_file TEXT NOT NULL,
    action TEXT NOT NULL,
    version TEXT,
    line_number INTEGER,
    raw_line TEXT,
    diff_line TEXT,
    FOREIGN KEY (session_id, commit_hash) REFERENCES commits(session_id, commit_hash)
);

CREATE TABLE IF NOT EXISTS decision_analyses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    target TEXT NOT NULL,
    model_name TEXT NOT NULL,
    decision TEXT NOT NULL,
    reason TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    affected_files_json TEXT NOT NULL,
    current_validity TEXT NOT NULL,
    confidence TEXT NOT NULL,
    uncertainty TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS repository_synopses (
    session_id TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    synopsis_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS issue_analyses (
    session_id TEXT NOT NULL,
    issue_number INTEGER NOT NULL,
    model_name TEXT NOT NULL,
    analysis_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (session_id, issue_number),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
"""


class SQLiteEngine:
    """Thin wrapper around sqlite3 with row factories and lifecycle helpers."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()
        finally:
            conn.close()

    def init_schema(self) -> None:
        with self.connection() as conn:
            conn.executescript(SCHEMA)

    def reset(self) -> None:
        """Delete the DB file and re-init. Dev/test helper."""
        if self.path.exists():
            self.path.unlink()
        self.init_schema()

    # ---- sessions ----

    def create_session(self, session_id: str, repo_url: str, repo_name: str,
                       clone_path: str, max_commits: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO sessions
                   (id, repo_url, repo_name, status, created_at, analyzed_commits,
                    clone_path, max_commits, error)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, repo_url, repo_name, "PENDING", now, 0, clone_path,
                 max_commits, None),
            )

    def set_failed(self, session_id: str, error: str) -> None:
        with self.connection() as conn:
            conn.execute(
                "UPDATE sessions SET status = ?, error = ? WHERE id = ?",
                ("FAILED", error, session_id),
            )

    def set_done(self, session_id: str, analyzed_commits: int) -> None:
        with self.connection() as conn:
            conn.execute(
                "UPDATE sessions SET status = ?, analyzed_commits = ? WHERE id = ?",
                ("ANALYZED", analyzed_commits, session_id),
            )

    def get_session(self, session_id: str) -> Optional[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()

    # ---- commits / file changes ----

    def store_commits(self, session_id: str, rows: List[tuple]) -> None:
        with self.connection() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO commits
                   (session_id, commit_hash, author_name, author_email, timestamp,
                    message, parent_hashes, change_type)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )

    def store_file_changes(self, session_id: str, rows: List[tuple]) -> None:
        with self.connection() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO file_changes
                   (session_id, commit_hash, path, status, additions, deletions)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                rows,
            )

    def list_commits(self, session_id: str) -> List[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                """SELECT * FROM commits WHERE session_id = ?
                   ORDER BY timestamp DESC LIMIT 50""",
                (session_id,),
            ).fetchall()

    # ---- dependency events ----

    def store_dependency_events(self, session_id: str, rows: List[tuple]) -> None:
        with self.connection() as conn:
            conn.executemany(
                """INSERT OR REPLACE INTO dependency_events
                   (session_id, commit_hash, dep_name, kind, manifest_file,
                    action, version, line_number, raw_line, diff_line)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                rows,
            )

    def list_dependency_events(self, session_id: str) -> List[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                """SELECT * FROM dependency_events
                   WHERE session_id = ?
                   ORDER BY commit_hash DESC""",
                (session_id,),
            ).fetchall()

    def list_file_changes(self, session_id: str) -> List[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                """SELECT * FROM file_changes WHERE session_id = ?
                   ORDER BY commit_hash DESC, path ASC""",
                (session_id,),
            ).fetchall()

    # ---- decision analyses ----

    def store_decision_analysis(self, session_id: str, target: str, model_name: str,
                                decision: str, reason: str, evidence_json: str,
                                affected_files_json: str, current_validity: str,
                                confidence: str, uncertainty: str) -> int:
        with self.connection() as conn:
            cursor = conn.execute(
                """INSERT INTO decision_analyses
                   (session_id, target, model_name, decision, reason, evidence_json,
                    affected_files_json, current_validity, confidence, uncertainty, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (session_id, target, model_name, decision, reason, evidence_json,
                 affected_files_json, current_validity, confidence, uncertainty,
                 datetime.now(timezone.utc).isoformat()),
            )
            return int(cursor.lastrowid)

    def list_decision_analyses(self, session_id: str) -> List[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                """SELECT * FROM decision_analyses WHERE session_id = ?
                   ORDER BY created_at DESC""",
                (session_id,),
            ).fetchall()

    def store_repository_synopsis(self, session_id: str, model_name: str, synopsis_json: str) -> None:
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO repository_synopses (session_id, model_name, synopsis_json, created_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(session_id) DO UPDATE SET model_name = excluded.model_name,
                   synopsis_json = excluded.synopsis_json, created_at = excluded.created_at""",
                (session_id, model_name, synopsis_json, datetime.now(timezone.utc).isoformat()),
            )

    def get_repository_synopsis(self, session_id: str) -> Optional[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                "SELECT * FROM repository_synopses WHERE session_id = ?", (session_id,)
            ).fetchone()

    def store_issue_analysis(self, session_id: str, issue_number: int,
                             model_name: str, analysis_json: str) -> None:
        with self.connection() as conn:
            conn.execute(
                """INSERT INTO issue_analyses
                   (session_id, issue_number, model_name, analysis_json, created_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(session_id, issue_number) DO UPDATE SET
                   model_name = excluded.model_name, analysis_json = excluded.analysis_json,
                   created_at = excluded.created_at""",
                (session_id, issue_number, model_name, analysis_json,
                 datetime.now(timezone.utc).isoformat()),
            )

    def get_issue_analysis(self, session_id: str, issue_number: int) -> Optional[sqlite3.Row]:
        with self.connection() as conn:
            return conn.execute(
                """SELECT * FROM issue_analyses
                   WHERE session_id = ? AND issue_number = ?""",
                (session_id, issue_number),
            ).fetchone()


# Module-level singleton shared by main.py and the API layer.
db = SQLiteEngine(DB_PATH)