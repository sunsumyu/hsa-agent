"""
app/core/memory/session_backfill.py
===================================
Idempotent startup/on-demand backfill indexing legacy `data/history/*.json`
conversation files into SessionStore's `chat_sessions` SQLite index.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

from loguru import logger

from app.core.context import tenant_context
from app.core.memory.pii_scrubber import pii_scrubber
from app.core.memory.session_title_generator import build_fallback_title, is_substantive_message

_LEGAL_MARKERS = (
    "民间借贷", "借款", "借条", "买卖合同", "起诉", "诉讼时效",
    "合同审查", "合同起草", "仲裁", "【模式：", "【身份：",
)


def infer_session_domain(session_id: str, messages: Sequence[Any]) -> str:
    """Infer whether a legacy session belongs to 'legal' or 'audit' domain."""
    if (session_id or "").strip().lower().startswith("legal"):
        return "legal"
    for msg in messages:
        if getattr(msg, "type", "") in ("human", "user"):
            content = str(getattr(msg, "content", "") or "")
            if any(marker in content for marker in _LEGAL_MARKERS):
                return "legal"
            break
    return "audit"


def _file_mtime_iso(filepath: str) -> str:
    ts = os.path.getmtime(filepath)
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _import_single_history_file(
    store,
    history_mgr,
    filename: str,
    tenant: str,
    skip_existing: bool,
) -> str:
    """Import one legacy JSON history file; returns 'imported', 'skipped', or 'empty'."""
    session_id = filename[:-5]
    filepath = os.path.join(history_mgr.storage_dir, filename)
    if skip_existing:
        with store._connect() as conn:
            if conn.execute("SELECT 1 FROM chat_sessions WHERE session_id = ?", (session_id,)).fetchone():
                return "skipped"

    raw_messages = history_mgr.get_history(session_id, auto_recover=False)
    visible = [m for m in raw_messages if getattr(m, "type", "") in ("human", "user", "ai", "assistant")]
    if not visible:
        return "empty"

    humans = [str(getattr(m, "content", "") or "") for m in visible if getattr(m, "type", "") in ("human", "user")]
    title_seed = next((h for h in humans if is_substantive_message(h)), humans[0] if humans else "")
    title = build_fallback_title(title_seed)
    last_user = humans[-1] if humans else str(getattr(visible[-1], "content", "") or "")
    preview = pii_scrubber.mask_sensitive_data(last_user).replace("\n", " ").strip()[:120]
    domain = infer_session_domain(session_id, visible)
    ts_iso = _file_mtime_iso(filepath)

    with store._connect() as conn:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO chat_sessions (
                session_id, tenant_id, domain, title, title_source,
                last_message_preview, message_count, pinned, archived, parent_session_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'fallback', ?, ?, 0, 0, NULL, ?, ?)
            """,
            (session_id, tenant, domain, title, preview, len(visible), ts_iso, ts_iso),
        )
        conn.commit()
    return "imported" if cursor.rowcount > 0 else "skipped"


def backfill_legacy_history(
    store,
    history_mgr,
    *,
    tenant_id: Optional[str] = None,
    skip_existing: bool = True,
) -> Dict[str, Any]:
    """Scan legacy JSON files in history_mgr.storage_dir and index missing sessions."""
    storage_dir = getattr(history_mgr, "storage_dir", "data/history")
    if not os.path.exists(storage_dir):
        return {"scanned": 0, "imported": 0, "skipped": 0, "empty_skipped": 0, "errors": 0, "imported_ids": []}

    effective_tenant = (tenant_id or "").strip() or tenant_context.get() or "default"
    filenames = sorted(
        f for f in os.listdir(storage_dir) if f.endswith(".json") and ".tmp." not in f
    )
    imported_ids: List[str] = []
    skipped = empty_skipped = errors = 0

    for filename in filenames:
        try:
            outcome = _import_single_history_file(store, history_mgr, filename, effective_tenant, skip_existing)
            if outcome == "imported":
                imported_ids.append(filename[:-5])
            elif outcome == "empty":
                empty_skipped += 1
            else:
                skipped += 1
        except Exception as exc:
            errors += 1
            logger.warning(f"[SessionBackfill] Failed importing {filename}: {exc}")

    return {
        "scanned": len(filenames),
        "imported": len(imported_ids),
        "skipped": skipped,
        "empty_skipped": empty_skipped,
        "errors": errors,
        "imported_ids": imported_ids,
    }
