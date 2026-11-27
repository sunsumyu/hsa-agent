"""
app/core/memory/session_store.py
================================
SQLite-backed conversation session metadata store with three-stage title
management (T0 fallback, T1 async LLM refinement, T2 manual rename lock)
and multi-tenant isolation.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage
from loguru import logger

from app.core.container import LazyProxy
from app.core.context import tenant_context
from app.core.memory.conversation_organizer import (
    ConversationOrganizer,
    OrganizedSession,
    conversation_organizer,
    extract_turns,
)
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
        "parent_session_id": row["parent_session_id"] if "parent_session_id" in row.keys() else None,
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
                    parent_session_id TEXT DEFAULT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            cols = {row[1] for row in conn.execute("PRAGMA table_info(chat_sessions)").fetchall()}
            if "parent_session_id" not in cols:
                conn.execute("ALTER TABLE chat_sessions ADD COLUMN parent_session_id TEXT DEFAULT NULL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_organizers (
                    session_id TEXT PRIMARY KEY,
                    source_message_count INTEGER NOT NULL DEFAULT 0,
                    mode TEXT NOT NULL DEFAULT 'heuristic',
                    topics_json TEXT NOT NULL DEFAULT '[]',
                    noise_turns_json TEXT NOT NULL DEFAULT '[]',
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
            deleted = cursor.rowcount > 0
            if deleted:
                conn.execute("DELETE FROM session_organizers WHERE session_id = ?", (sid,))
            conn.commit()
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

    def get_organized_topics(self, session_id: str, *, tenant_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Retrieve cached topic/noise organization for an existing tenant session."""
        sid = _validate_session_id(session_id)
        session = self.get_session(sid, tenant_id=tenant_id)
        if session is None:
            raise KeyError(sid)
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM session_organizers WHERE session_id = ?", (sid,)).fetchone()
        if row is None:
            return None
        return {
            "session_id": sid,
            "mode": row["mode"],
            "source_message_count": int(row["source_message_count"]),
            "is_stale": int(row["source_message_count"]) != session["message_count"],
            "topics": json.loads(row["topics_json"]),
            "noise_turns": json.loads(row["noise_turns_json"]),
            "updated_at": row["updated_at"],
        }

    def save_organized_topics(
        self,
        session_id: str,
        organized: OrganizedSession,
        source_message_count: int,
    ) -> Dict[str, Any]:
        """Persist organized topic clusters and noise entries in SQLite cache."""
        sid = _validate_session_id(session_id)
        now = _utc_now_iso()
        topics_payload = [t.model_dump() for t in organized.topics]
        noise_payload = [n.model_dump() for n in organized.noise_turns]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO session_organizers (
                    session_id, source_message_count, mode, topics_json, noise_turns_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    source_message_count = excluded.source_message_count,
                    mode = excluded.mode,
                    topics_json = excluded.topics_json,
                    noise_turns_json = excluded.noise_turns_json,
                    updated_at = excluded.updated_at
                """,
                (sid, source_message_count, organized.mode, json.dumps(topics_payload, ensure_ascii=False), json.dumps(noise_payload, ensure_ascii=False), now),
            )
            conn.commit()
        return {
            "session_id": sid,
            "mode": organized.mode,
            "source_message_count": source_message_count,
            "is_stale": False,
            "topics": topics_payload,
            "noise_turns": noise_payload,
            "updated_at": now,
        }

    async def organize_session(
        self,
        session_id: str,
        history_mgr,
        *,
        organizer: Optional[ConversationOrganizer] = None,
        force: bool = False,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Organize session turns into topics and noise, using cache when fresh."""
        sid = _validate_session_id(session_id)
        session = self.get_session(sid, tenant_id=tenant_id)
        if session is None:
            raise KeyError(sid)
        messages = history_mgr.get_history(sid, auto_recover=False)
        turns = extract_turns(messages)
        turns_payload = [t.model_dump() for t in turns]

        if not force:
            cached = self.get_organized_topics(sid, tenant_id=tenant_id)
            if cached is not None and not cached["is_stale"]:
                return {**cached, "turns": turns_payload}

        org = organizer or conversation_organizer
        organized = await org.organize(messages, domain=session["domain"])
        saved = self.save_organized_topics(sid, organized, source_message_count=session["message_count"])
        return {**saved, "turns": turns_payload}

    def _create_split_child(
        self,
        parent_id: str,
        tenant: str,
        topic: Dict[str, Any],
        turns: List[Any],
        history_mgr,
    ) -> Dict[str, Any]:
        selected_turns = [turns[idx] for idx in topic["turn_indices"] if 0 <= idx < len(turns)]
        child_msgs = []
        for turn in selected_turns:
            child_msgs.append(HumanMessage(content=turn.user_message))
            child_msgs.append(AIMessage(content=turn.ai_message))
        child_id = f"{parent_id}__{topic['topic_id']}_{uuid.uuid4().hex[:6]}"
        history_mgr.save_messages(child_id, child_msgs)

        last_user = selected_turns[-1].user_message if selected_turns else topic["title"]
        preview = pii_scrubber.mask_sensitive_data(last_user).replace("\n", " ").strip()[:120]
        now = _utc_now_iso()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_sessions (
                    session_id, tenant_id, domain, title, title_source,
                    last_message_preview, message_count, pinned, archived, parent_session_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, 'llm', ?, ?, 0, 0, ?, ?, ?)
                """,
                (child_id, tenant, topic.get("domain") or "audit", topic["title"], preview, len(child_msgs), parent_id, now, now),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM chat_sessions WHERE session_id = ?", (child_id,)).fetchone()
        return _row_to_dict(row)

    def split_session_by_topics(
        self,
        session_id: str,
        history_mgr,
        *,
        topic_ids: Optional[List[str]] = None,
        archive_source: bool = False,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Materialize organized topics into independent sessions excluding noise."""
        sid = _validate_session_id(session_id)
        tenant = _resolve_tenant(tenant_id)
        organized = self.get_organized_topics(sid, tenant_id=tenant)
        if organized is None:
            raise ValueError("请先执行对话主题整理后再拆分")
        topics = organized["topics"]
        if topic_ids is not None:
            allowed = set(topic_ids)
            topics = [t for t in topics if t["topic_id"] in allowed]
        if not topics:
            raise ValueError("未选择有效的待拆分主题")

        turns = extract_turns(history_mgr.get_history(sid, auto_recover=False))
        created = [self._create_split_child(sid, tenant, topic, turns, history_mgr) for topic in topics]
        if archive_source:
            self.update_session(sid, archived=True, tenant_id=tenant)
        return {"source_session_id": sid, "archived_source": archive_source, "created_sessions": created}


session_store = LazyProxy("session_store")
