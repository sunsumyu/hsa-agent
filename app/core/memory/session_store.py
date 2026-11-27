"""
app/core/memory/session_store.py
================================
SQLite-backed conversation session metadata store with three-stage title
management (T0 fallback, T1 async LLM refinement, T2 manual rename lock)
and multi-tenant isolation.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from loguru import logger

from app.core.container import LazyProxy
from app.core.context import tenant_context
from app.core.memory.pii_scrubber import pii_scrubber
from app.core.memory.session_title_generator import (
    SessionTitleGenerator,
    build_fallback_title,
    is_substantive_message,
    sanitize_title,
    session_title_generator,
)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_tenant(tenant_id: Optional[str]) -> str:
    if tenant_id and str(tenant_id).strip():
        return str(tenant_id).strip()
    return tenant_context.get() or "default"


def _validate_session_id(session_id: str) -> str:
    cleaned = (session_id or "").strip()
    if not cleaned:
        raise ValueError("session_id 不能为空")
    return cleaned


def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "session_id": row["session_id"],
        "tenant_id": row["tenant_id"],
        "domain": row["domain"],
        "title": row["title"],
        "title_source": row["title_source"],
        "last_message_preview": row["last_message_preview"],
        "message_count": int(row["message_count"]),
        "pinned": bool(row["pinned"]),
        "archived": bool(row["archived"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


class SessionStore:
    """Persistent SQLite index for multi-session conversation metadata."""

    def __init__(
        self,
        db_path: str = "data/history/sessions.db",
        title_generator: Optional[SessionTitleGenerator] = None,
    ):
        self.db_path = db_path
        self._title_generator = title_generator or session_title_generator
        parent = os.path.dirname(os.path.abspath(self.db_path))
        if parent:
            os.makedirs(parent, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_sessions (
                    session_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL DEFAULT 'default',
                    domain TEXT NOT NULL DEFAULT 'audit',
                    title TEXT NOT NULL,
                    title_source TEXT NOT NULL DEFAULT 'fallback',
                    last_message_preview TEXT NOT NULL DEFAULT '',
                    message_count INTEGER NOT NULL DEFAULT 0,
                    pinned INTEGER NOT NULL DEFAULT 0,
                    archived INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_tenant_sort "
                "ON chat_sessions(tenant_id, archived, pinned, updated_at)"
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_domain ON chat_sessions(domain)")
            conn.commit()

    def _fetch_row(self, session_id: str, tenant_id: Optional[str] = None) -> Optional[sqlite3.Row]:
        with self._connect() as conn:
            if tenant_id is None:
                return conn.execute("SELECT * FROM chat_sessions WHERE session_id = ?", (session_id,)).fetchone()
            return conn.execute(
                "SELECT * FROM chat_sessions WHERE session_id = ? AND tenant_id = ?",
                (session_id, tenant_id),
            ).fetchone()

    def record_turn(
        self,
        session_id: str,
        user_message: str,
        ai_reply: str,
        *,
        domain: str = "audit",
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upsert session metadata for a completed turn and indicate T1 refinement need."""
        sid = _validate_session_id(session_id)
        tenant = _resolve_tenant(tenant_id)
        now = _utc_now_iso()
        preview = pii_scrubber.mask_sensitive_data(user_message or "").replace("\n", " ").strip()[:120]
        substantive = is_substantive_message(user_message)
        fallback_title = build_fallback_title(user_message)

        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM chat_sessions WHERE session_id = ?", (sid,)
            ).fetchone()
            if existing is None:
                conn.execute(
                    """
                    INSERT INTO chat_sessions (
                        session_id, tenant_id, domain, title, title_source,
                        last_message_preview, message_count, pinned, archived, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'fallback', ?, 2, 0, 0, ?, ?)
                    """,
                    (sid, tenant, domain, fallback_title, preview, now, now),
                )
            else:
                new_title = (
                    fallback_title
                    if existing["title_source"] == "fallback" and existing["title"] == "新对话" and substantive
                    else existing["title"]
                )
                conn.execute(
                    """
                    UPDATE chat_sessions
                    SET title = ?, last_message_preview = ?, message_count = message_count + 2, updated_at = ?
                    WHERE session_id = ?
                    """,
                    (new_title, preview, now, sid),
                )
            conn.commit()
            row = conn.execute("SELECT * FROM chat_sessions WHERE session_id = ?", (sid,)).fetchone()

        result = _row_to_dict(row)
        result["should_refine_title"] = bool(result["title_source"] == "fallback" and substantive)
        return result

    def update_title_from_llm(self, session_id: str, title: str, *, force: bool = False) -> bool:
        """Persist T1 LLM title unless user manually locked the session title."""
        sid = _validate_session_id(session_id)
        cleaned = sanitize_title(title, max_len=20)
        if not cleaned:
            return False
        lock_clause = "" if force else " AND title_source != 'manual'"
        with self._connect() as conn:
            cursor = conn.execute(
                f"UPDATE chat_sessions SET title = ?, title_source = 'llm', updated_at = ? WHERE session_id = ?{lock_clause}",
                (cleaned, _utc_now_iso(), sid),
            )
            conn.commit()
            return cursor.rowcount > 0

    def get_session(self, session_id: str, *, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieve session metadata scoped by tenant."""
        sid = _validate_session_id(session_id)
        row = self._fetch_row(sid, _resolve_tenant(tenant_id))
        return _row_to_dict(row) if row is not None else None

    def list_sessions(
        self,
        *,
        tenant_id: Optional[str] = None,
        domain: Optional[str] = None,
        query: Optional[str] = None,
        include_archived: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """List paginated sessions ordered by pinned status and recent activity."""
        clauses: List[str] = ["tenant_id = ?"]
        params: List[Any] = [_resolve_tenant(tenant_id)]
        if not include_archived:
            clauses.append("archived = 0")
        if domain:
            clauses.append("domain = ?")
            params.append(domain)
        if query and query.strip():
            like_kw = f"%{query.strip()}%"
            clauses.append("(title LIKE ? OR last_message_preview LIKE ?)")
            params.extend([like_kw, like_kw])

        where_sql = " AND ".join(clauses)
        with self._connect() as conn:
            total = conn.execute(f"SELECT COUNT(*) FROM chat_sessions WHERE {where_sql}", params).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM chat_sessions WHERE {where_sql} "
                "ORDER BY pinned DESC, updated_at DESC LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
        return {"items": [_row_to_dict(r) for r in rows], "total": int(total), "limit": limit, "offset": offset}

    def update_session(
        self,
        session_id: str,
        *,
        title: Optional[str] = None,
        pinned: Optional[bool] = None,
        archived: Optional[bool] = None,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Update session title (locking as manual), pinned flag, or archived flag."""
        sid = _validate_session_id(session_id)
        tenant = _resolve_tenant(tenant_id)
        if self._fetch_row(sid, tenant) is None:
            raise KeyError(sid)

        sets: List[str] = ["updated_at = ?"]
        params: List[Any] = [_utc_now_iso()]
        if title is not None:
            cleaned = sanitize_title(title, max_len=40)
            if not cleaned:
                raise ValueError("会话标题不能为空")
            sets.extend(["title = ?", "title_source = 'manual'"])
            params.append(cleaned)
        if pinned is not None:
            sets.append("pinned = ?")
            params.append(int(bool(pinned)))
        if archived is not None:
            sets.append("archived = ?")
            params.append(int(bool(archived)))

        params.extend([sid, tenant])
        with self._connect() as conn:
            conn.execute(f"UPDATE chat_sessions SET {', '.join(sets)} WHERE session_id = ? AND tenant_id = ?", params)
            conn.commit()
            updated = conn.execute("SELECT * FROM chat_sessions WHERE session_id = ?", (sid,)).fetchone()
        return _row_to_dict(updated)

    def delete_session(
        self,
        session_id: str,
        *,
        tenant_id: Optional[str] = None,
        history_mgr=None,
    ) -> bool:
        """Delete session metadata and optional JSON message history."""
        sid = _validate_session_id(session_id)
        tenant = _resolve_tenant(tenant_id)
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM chat_sessions WHERE session_id = ? AND tenant_id = ?",
                (sid, tenant),
            )
            conn.commit()
            deleted = cursor.rowcount > 0
        if deleted and history_mgr is not None:
            history_mgr.delete_history(sid)
        return deleted

    async def delete_session_cascade(
        self,
        session_id: str,
        *,
        tenant_id: Optional[str] = None,
        history_mgr=None,
        checkpointer=None,
    ) -> bool:
        """Delete session metadata, message history, and LangGraph checkpointer thread."""
        deleted = self.delete_session(session_id, tenant_id=tenant_id, history_mgr=history_mgr)
        if deleted and checkpointer is not None and hasattr(checkpointer, "adelete_thread"):
            try:
                await checkpointer.adelete_thread(session_id)
            except Exception as exc:
                logger.warning(f"[SessionStore] Failed to delete checkpointer thread {session_id}: {exc}")
        return deleted

    async def refine_title_in_background(
        self,
        session_id: str,
        user_message: str,
        ai_reply: str,
        *,
        domain: str = "audit",
        force: bool = False,
    ) -> Optional[str]:
        """Run T1 async LLM title refinement and persist unless manually locked."""
        row = self._fetch_row(_validate_session_id(session_id))
        if row is None:
            return None
        if not force and row["title_source"] != "fallback":
            return None
        refined = await self._title_generator.generate_llm_title(user_message, ai_reply, domain=domain)
        if not refined:
            return None
        if self.update_title_from_llm(session_id, refined, force=force):
            return refined
        return None


session_store = LazyProxy("session_store")
