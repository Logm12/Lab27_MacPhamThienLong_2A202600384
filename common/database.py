"""SQLite helpers: connection + audit-event writer + checkpoint saver.

The `audit_events` table lives in the same .db file as the LangGraph
SQLite checkpointer tables — different schemas, same file.

This centralizes both operational SQLite connection provisioning and the 
async LangGraph state checkpointer logic.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from common.schemas import AuditEntry


SCHEMA_FILE = Path(__file__).resolve().parent.parent / "audit" / "schema.sql"


def db_path() -> str:
    """Return the SQLite file path (override with DATABASE_URL or HITL_DB_PATH env vars)."""
    url = os.environ.get("DATABASE_URL")
    if url:
        # Strip standard sqlite connection prefix if present for aiosqlite compatibility
        if url.startswith("sqlite:///"):
            return url[10:]
        return url
    return os.environ.get("HITL_DB_PATH", "hitl_audit.db")


async def _ensure_schema(conn: aiosqlite.Connection) -> None:
    """Ensure audit trail schema exists and is indexed for scale."""
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_events'"
    ) as cur:
        if await cur.fetchone() is not None:
            # Ensure scale index exists on upgrade scenarios
            await conn.execute("CREATE INDEX IF NOT EXISTS idx_thread_time ON audit_events (thread_id, timestamp)")
            await conn.commit()
            return
    await conn.executescript(SCHEMA_FILE.read_text())
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_thread_time ON audit_events (thread_id, timestamp)")
    await conn.commit()


@asynccontextmanager
async def db_conn() -> AsyncIterator[aiosqlite.Connection]:
    """Open an aiosqlite connection, applying schema if first use."""
    conn = await aiosqlite.connect(db_path())
    conn.row_factory = aiosqlite.Row
    try:
        await _ensure_schema(conn)
        yield conn
    finally:
        await conn.close()


async def write_audit_event(
    *,
    thread_id: str,
    pr_url: str,
    entry: AuditEntry,
) -> None:
    """Append one structured audit row.

    `thread_id` and `pr_url` are session-context columns (used for grouping
    and filtering); all other fields come from the `AuditEntry` so they map
    1-to-1 with first-class SQL columns.
    """
    async with db_conn() as conn:
        await conn.execute(
            """
            INSERT INTO audit_events (
                timestamp, thread_id, pr_url,
                agent_id, action, confidence, risk_level,
                reviewer_id, decision, reason, execution_time_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry.timestamp.isoformat(), thread_id, pr_url,
                entry.agent_id, entry.action, entry.confidence, entry.risk_level,
                entry.reviewer_id, entry.decision, entry.reason, entry.execution_time_ms,
            ),
        )
        await conn.commit()


async def replay_events(thread_id: str) -> list[dict[str, Any]]:
    """Return every event for a thread, ordered by time. Used by audit/replay.py."""
    async with db_conn() as conn:
        async with conn.execute(
            """
            SELECT id, timestamp, agent_id, action, confidence, risk_level,
                   reviewer_id, decision, reason, execution_time_ms
              FROM audit_events
             WHERE thread_id = ?
             ORDER BY id
            """,
            (thread_id,),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


@asynccontextmanager
async def get_checkpointer() -> AsyncIterator[AsyncSqliteSaver]:
    """Provide an active, pre-setup AsyncSqliteSaver checkpointer.
    
    Usage:
        async with get_checkpointer() as cp:
            graph = build_graph(cp)
            # use graph
    """
    async with AsyncSqliteSaver.from_conn_string(db_path()) as cp:
        await cp.setup()
        yield cp
