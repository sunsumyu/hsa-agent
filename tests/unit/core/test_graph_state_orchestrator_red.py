"""
tests/unit/core/test_graph_state_orchestrator_red.py
===================================================
Red unit tests for Graph State & Session Lifecycle Orchestrator.
Tests:
- format_findings_overwrite: formats list and str with ⟦OVERWRITE⟧ marker
- intervene_session_findings: updates graph state for active thread or returns error
- fork_session_thread: clones state from source to target thread or returns error
- get_session_timeline_events: safely extracts timeline_events from thread snapshot
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.orchestration.graph_state_orchestrator import (
    format_findings_overwrite,
    get_session_timeline_events,
    intervene_session_findings,
    fork_session_thread,
    GraphStateOrchestrator,
)


def test_format_findings_overwrite_list():
    findings = ["Finding 1: Overbilling", "Finding 2: False diagnosis"]
    formatted = format_findings_overwrite(findings)
    assert isinstance(formatted, list)
    assert len(formatted) == 1
    assert formatted[0].startswith("⟦OVERWRITE⟧")
    assert "Finding 1: Overbilling" in formatted[0]
    assert "Finding 2: False diagnosis" in formatted[0]


def test_format_findings_overwrite_string():
    findings = "Single finding string"
    formatted = format_findings_overwrite(findings)
    assert isinstance(formatted, list)
    assert len(formatted) == 1
    assert formatted[0] == "⟦OVERWRITE⟧Single finding string"


@pytest.mark.asyncio
async def test_intervene_session_findings_success():
    mock_executor = MagicMock()
    mock_state = MagicMock()
    mock_state.values = {"findings": ["old finding"]}
    mock_executor.aget_state = AsyncMock(return_value=mock_state)
    mock_executor.aupdate_state = AsyncMock()

    result = await intervene_session_findings(
        session_id="session-123",
        findings=["new finding"],
        executor=mock_executor,
    )

    assert result["status"] == "success"
    mock_executor.aget_state.assert_awaited_once_with({"configurable": {"thread_id": "session-123"}})
    mock_executor.aupdate_state.assert_awaited_once_with(
        {"configurable": {"thread_id": "session-123"}},
        {"findings": ["⟦OVERWRITE⟧new finding"]}
    )


@pytest.mark.asyncio
async def test_intervene_session_findings_not_found():
    mock_executor = MagicMock()
    mock_state = MagicMock()
    mock_state.values = None
    mock_executor.aget_state = AsyncMock(return_value=mock_state)

    result = await intervene_session_findings(
        session_id="missing-session",
        findings=["new finding"],
        executor=mock_executor,
    )

    assert result["status"] == "error"
    assert "不存在" in result["message"]


@pytest.mark.asyncio
async def test_fork_session_thread_success():
    mock_executor = MagicMock()
    mock_state = MagicMock()
    mock_state.values = {"findings": ["cloned finding"], "step": 3}
    mock_executor.aget_state = AsyncMock(return_value=mock_state)
    mock_executor.aupdate_state = AsyncMock()

    result = await fork_session_thread(
        source_session="src-session",
        target_session="tgt-session",
        executor=mock_executor,
    )

    assert result["status"] == "success"
    assert result["targetSession"] == "tgt-session"
    mock_executor.aupdate_state.assert_awaited_once_with(
        {"configurable": {"thread_id": "tgt-session"}},
        {"findings": ["cloned finding"], "step": 3}
    )


@pytest.mark.asyncio
async def test_fork_session_thread_not_found():
    mock_executor = MagicMock()
    mock_state = MagicMock()
    mock_state.values = {}
    mock_executor.aget_state = AsyncMock(return_value=mock_state)

    result = await fork_session_thread(
        source_session="missing-src",
        target_session="tgt-session",
        executor=mock_executor,
    )

    assert result["status"] == "error"
    assert "源会话不存在" in result["message"]


@pytest.mark.asyncio
async def test_get_session_timeline_events():
    mock_executor = MagicMock()
    mock_state = MagicMock()
    mock_state.values = {
        "timeline_events": [
            {"step": "PLANNER", "timestamp": "2026-10-18T10:00:00"},
            {"step": "SQLEXEC", "timestamp": "2026-10-18T10:00:05"},
        ]
    }
    mock_executor.aget_state = AsyncMock(return_value=mock_state)

    events = await get_session_timeline_events("session-456", executor=mock_executor)
    assert len(events) == 2
    assert events[0]["step"] == "PLANNER"

    # When no timeline_events exist in state
    mock_state.values = {}
    empty_events = await get_session_timeline_events("session-456", executor=mock_executor)
    assert empty_events == []
