from unittest.mock import AsyncMock, patch

import pytest
from langgraph.checkpoint.memory import MemorySaver

import app.api.legal_stream_coordinator as lsc_mod
from app.api.legal_stream_coordinator import (
    LegalStreamCoordinator,
    _format_aligner_section,
    _format_gate_section,
    _format_hitl_card,
)


def test_legal_stream_coordinator_accepts_custom_checkpointer():
    custom_saver = MemorySaver()
    coord = LegalStreamCoordinator(checkpointer=custom_saver)
    assert coord._checkpointer is custom_saver


@pytest.mark.asyncio
async def test_direct_legal_mode_dispatches_cleanly_without_stdout_write(capsys):
    coord = LegalStreamCoordinator()
    fake_areview = AsyncMock(return_value=("【审查意见】高风险条款已标出。", {"prompt": 12, "completion": 34}))

    with (
        patch.object(lsc_mod.contract_reviewer, "areview", new=fake_areview),
        patch.object(lsc_mod.history_manager, "save_turn") as mock_save,
    ):
        chunks = [
            c
            async for c in coord.coordinate_legal_stream(
                session_id="legal-direct-1",
                message="【模式：合同审查】请审核这份采购合同的违约金条款。",
            )
        ]

    captured = capsys.readouterr()
    assert captured.out == ""
    joined = "".join(chunks)
    assert "[[[ENGINE:Argus-Legal-Agent]]]" in joined
    assert "REVIEWER" in joined
    assert "高风险条款已标出" in joined
    fake_areview.assert_awaited_once()
    mock_save.assert_called_once()


def test_legal_section_formatters_support_dict_and_hitl_fields():
    aligner_md = _format_aligner_section(
        {
            "case_facts": [{"narrative": "2024年签订借款协议"}],
            "evidence_items": [
                {
                    "title": "借条",
                    "evidence_type": "书证",
                    "submission_status": "已提交",
                    "authenticity_level": "高",
                }
            ],
            "missing_evidence": ["银行转账回单"],
        },
        cause="民间借贷纠纷",
    )
    assert "2024年签订借款协议" in aligner_md
    assert "《借条》" in aligner_md
    assert "银行转账回单" in aligner_md

    gate_md = _format_gate_section({"current_step": "GATE_FAIL", "error_log": "超过三年诉讼时效"})
    assert "超过三年诉讼时效" in gate_md

    hitl_md = _format_hitl_card({"error_log": "缺少交付凭证", "missing_evidence": ["转账流水"]})
    assert "缺少交付凭证" in hitl_md
    assert "转账流水" in hitl_md
