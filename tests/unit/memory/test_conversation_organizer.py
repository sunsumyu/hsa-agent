"""
tests/unit/memory/test_conversation_organizer.py
================================================
Offline unit tests for 3-stage conversation organizer:
L1 noise vs follow-up whitelist, interleaved A->B->A clustering,
L3 deterministic reconciliation, SessionStore cache/split, and REST endpoints.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from langchain_core.messages import AIMessage, HumanMessage
from starlette.testclient import TestClient

from app.api.envelope import register_api_exception_handlers
from app.api.routes import sessions as sessions_route
from app.core.memory.conversation_organizer import (
    ConversationOrganizer,
    TurnItem,
    classify_turn_l1,
    extract_turns,
    organize_heuristically,
)
from app.core.memory.history import HistoryManager
from app.core.memory.session_store import SessionStore


def _make_interleaved_messages():
    pairs = [
        ("你好", "您好，请问有什么可以帮您？"),
        ("排查三甲医院骨科高值耗材骨水泥重复收费情况", "已定位骨水泥超量及重复计费明细 28 笔。"),
        ("展开说说", "骨水泥单节段临床常规用量不超过 6ml，重复收费集中在 3 家科室。"),
        ("换个问题，统计术后出院次日转入康复科的分解住院案例", "共检出术后短期跨科转入康复科疑似分解住院 19 例。"),
        ("再查下前面骨科高值耗材骨水泥重复收费涉案最高的前三家医院", "前三大涉案医院累计违规金额 14.6 万元。"),
        ("好的谢谢", "不客气，随时为您核查。"),
    ]
    msgs = []
    for u, a in pairs:
        msgs.append(HumanMessage(content=u))
        msgs.append(AIMessage(content=a))
    return msgs


def test_l1_noise_and_followup_protection():
    assert classify_turn_l1(TurnItem(turn_index=0, user_message="你好"))[0] == "noise"
    assert classify_turn_l1(TurnItem(turn_index=0, user_message="收到，谢谢！"))[0] == "noise"
    assert classify_turn_l1(TurnItem(turn_index=0, user_message="test"))[0] == "noise"
    assert classify_turn_l1(TurnItem(turn_index=0, user_message="111"))[0] == "noise"

    assert classify_turn_l1(TurnItem(turn_index=1, user_message="继续"))[0] == "followup"
    assert classify_turn_l1(TurnItem(turn_index=1, user_message="展开说说"))[0] == "followup"
    assert classify_turn_l1(TurnItem(turn_index=1, user_message="第一家具体明细呢"))[0] == "followup"
    assert classify_turn_l1(TurnItem(turn_index=1, user_message="为什么"))[0] == "followup"

    assert classify_turn_l1(TurnItem(turn_index=2, user_message="排查三甲医院骨科骨水泥重复收费问题"))[0] == "substantive"


def test_heuristic_interleaved_topics_and_noise_filtering():
    turns = extract_turns(_make_interleaved_messages())
    assert len(turns) == 6
    organized = organize_heuristically(turns, default_domain="audit")
    assert organized.mode == "heuristic"
    assert [n.turn_index for n in organized.noise_turns] == [0, 5]
    assert len(organized.topics) == 2
    assert organized.topics[0].turn_indices == [1, 2, 4]
    assert organized.topics[1].turn_indices == [3]


@pytest.mark.asyncio
async def test_llm_reconcile_guards_coverage_followups_and_pii():
    payload = {
        "topics": [
            {
                "title": "《患者：张三 13812345678 骨科耗材核查》。",
                "domain": "audit",
                "summary": "排查患者：张三 13812345678 骨水泥重复收费。",
                "turn_indices": [1, 1, 4, 99],
                "key_entities": ["骨水泥", "高值耗材"],
            }
        ],
        "noise_turns": [
            {"turn_index": 0, "reason": "问候"},
            {"turn_index": 2, "reason": "短句"},
            {"turn_index": 5, "reason": "感谢"},
        ],
    }

    async def fake_ainvoke(*_args, **_kwargs):
        return SimpleNamespace(content=f"<thought>思考</thought>\n```json\n{json.dumps(payload, ensure_ascii=False)}\n```")

    llm = MagicMock()
    llm.ainvoke = fake_ainvoke
    org = ConversationOrganizer(llm_factory=lambda: llm)
    organized = await org.organize(_make_interleaved_messages(), domain="audit")

    assert organized.mode == "llm"
    assert [n.turn_index for n in organized.noise_turns] == [0, 5]
    all_topic_turns = [idx for t in organized.topics for idx in t.turn_indices]
    assert sorted(all_topic_turns) == [1, 2, 3, 4]
    assert 2 in organized.topics[0].turn_indices
    assert "13812345678" not in organized.topics[0].title
    assert "《" not in organized.topics[0].title
    assert "13812345678" not in organized.topics[0].summary


@pytest.mark.asyncio
async def test_llm_timeout_and_bad_json_fallback_to_heuristic():
    async def broken_ainvoke(*_args, **_kwargs):
        await asyncio.sleep(0.1)
        return SimpleNamespace(content="not-json")

    llm = MagicMock()
    llm.ainvoke = broken_ainvoke
    org = ConversationOrganizer(llm_factory=lambda: llm)
    organized = await org.organize(_make_interleaved_messages(), domain="audit", timeout_seconds=0.01)

    assert organized.mode == "heuristic"
    covered = sorted([idx for t in organized.topics for idx in t.turn_indices] + [n.turn_index for n in organized.noise_turns])
    assert covered == [0, 1, 2, 3, 4, 5]


@pytest.mark.asyncio
async def test_session_store_organize_cache_and_split_by_topics(tmp_path):
    store = SessionStore(db_path=str(tmp_path / "sessions.db"))
    history_mgr = HistoryManager(storage_dir=str(tmp_path / "history"), max_messages=30)

    msgs = _make_interleaved_messages()
    history_mgr.save_messages("mix_s1", msgs)
    for i in range(0, len(msgs), 2):
        store.record_turn("mix_s1", str(msgs[i].content), str(msgs[i + 1].content), domain="audit")

    calls = 0
    llm_resp = {
        "topics": [
            {"title": "骨科高值耗材重复收费核查", "domain": "audit", "summary": "骨水泥超量", "turn_indices": [1, 2, 4]},
            {"title": "术后跨科分解住院认定", "domain": "audit", "summary": "转科时间窗", "turn_indices": [3]},
        ],
        "noise_turns": [{"turn_index": 0, "reason": "问候"}, {"turn_index": 5, "reason": "感谢"}],
    }

    async def fake_ainvoke(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return SimpleNamespace(content=json.dumps(llm_resp, ensure_ascii=False))

    llm = MagicMock()
    llm.ainvoke = fake_ainvoke
    org = ConversationOrganizer(llm_factory=lambda: llm)

    first = await store.organize_session("mix_s1", history_mgr, organizer=org)
    second = await store.organize_session("mix_s1", history_mgr, organizer=org)
    assert calls == 1
    assert first["mode"] == "llm"
    assert second["is_stale"] is False

    store.record_turn("mix_s1", "继续核查第五家机构", "已补充第五家")
    assert store.get_organized_topics("mix_s1")["is_stale"] is True
    await store.organize_session("mix_s1", history_mgr, organizer=org, force=True)
    assert calls == 2

    split_keep = store.split_session_by_topics("mix_s1", history_mgr)
    assert split_keep["archived_source"] is False
    assert len(split_keep["created_sessions"]) == 2
    assert store.get_session("mix_s1")["archived"] is False

    child_a = split_keep["created_sessions"][0]
    assert child_a["parent_session_id"] == "mix_s1"
    assert child_a["title"] == "骨科高值耗材重复收费核查"
    child_a_msgs = history_mgr.get_history(child_a["session_id"])
    assert len(child_a_msgs) == 6
    assert "你好" not in [m.content for m in child_a_msgs]

    split_arch = store.split_session_by_topics("mix_s1", history_mgr, topic_ids=["topic-2"], archive_source=True)
    assert len(split_arch["created_sessions"]) == 1
    assert store.get_session("mix_s1")["archived"] is True


def test_session_organize_and_split_rest_api(tmp_path, monkeypatch):
    store = SessionStore(db_path=str(tmp_path / "sessions.db"))
    history_mgr = HistoryManager(storage_dir=str(tmp_path / "history"), max_messages=30)

    msgs = _make_interleaved_messages()
    history_mgr.save_messages("api_mix", msgs)
    for i in range(0, len(msgs), 2):
        store.record_turn("api_mix", str(msgs[i].content), str(msgs[i + 1].content), domain="audit")

    app = FastAPI()
    register_api_exception_handlers(app)
    app.include_router(sessions_route.router)

    monkeypatch.setattr(sessions_route, "session_store", store)
    monkeypatch.setattr(sessions_route, "history_manager", history_mgr)
    monkeypatch.setattr("app.core.memory.session_store.conversation_organizer", ConversationOrganizer(llm_factory=lambda: (_ for _ in ()).throw(RuntimeError("offline"))))
    client = TestClient(app, raise_server_exceptions=False)

    assert client.get("/agent/sessions/api_mix/topics").json()["data"]["organized"] is False

    resp_org = client.post("/agent/sessions/api_mix/organize")
    assert resp_org.status_code == 200
    org_data = resp_org.json()["data"]
    assert len(org_data["topics"]) == 2
    assert len(org_data["noise_turns"]) == 2

    resp_topics = client.get("/ins-fqz/agent/sessions/api_mix/topics")
    assert resp_topics.status_code == 200
    assert resp_topics.json()["data"]["organized"] is True
    assert len(resp_topics.json()["data"]["turns"]) == 6

    resp_split = client.post("/agent/sessions/api_mix/split", json={"archive_source": False})
    assert resp_split.status_code == 200
    created = resp_split.json()["data"]["created_sessions"]
    assert len(created) == 2

    child_detail = client.get(f"/agent/sessions/{created[0]['session_id']}")
    assert child_detail.status_code == 200
    assert len(child_detail.json()["data"]["messages"]) == 6

    assert client.post("/agent/sessions/api_mix/split", json={"topic_ids": ["nonexistent"]}).status_code == 400
    assert client.post("/agent/sessions/missing/organize").status_code == 404
