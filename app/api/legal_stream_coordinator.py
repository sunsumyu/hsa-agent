"""
app/api/legal_stream_coordinator.py
====================================
[Legal Agent Deep Module] 法律多轮辩法流式协调器
将民商事法律辩法引擎（事实审查、焦点三段论、红蓝攻防、神经符号门禁、HITL 人工补证中断、法官心证）
无缝转换为 argus-frontend (Rust/WASM) 协议流格式。
"""

from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, Dict, Optional, Tuple
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from loguru import logger

from domains.legal.graph import build_legal_graph
from domains.legal.state.case_state import LegalCaseState
from domains.legal.agents.contract_reviewer import contract_reviewer
from domains.legal.agents.contract_drafter import contract_drafter
from domains.legal.agents.consultation_advisor import consultation_advisor
from domains.legal.agents.evidence_examiner import evidence_examiner
from domains.legal.agents.execution_advisor import execution_advisor
from app.core.memory.history import history_manager
from app.core.memory.session_store import session_store
from app.infra.redis_client import redis_manager

_DIRECT_MODE_SPECS: Dict[str, Tuple[str, str, Any, str]] = {
    "contract_review": ("🔍 正在执行合同智能审查与高危红线排查...", "REVIEWER", contract_reviewer, "areview"),
    "contract_draft": ("📝 正在依据民法典及行业规范起草合规合同草案...", "DRAFTER", contract_drafter, "adraft"),
    "consultation": ("💬 正在梳理法律关系、博弈筹码与定制诉前谈判方案...", "ADVISOR", consultation_advisor, "aadvise"),
    "evidence_examination": ("📑 正在执行证据法定三性审查与举证质证推演...", "EXAMINER", evidence_examiner, "aexamine"),
    "execution_advisory": ("⚡ 正在审查执行依据、排查财产线索与制定强制执行方案...", "EXECUTION", execution_advisor, "aadvise"),
}

_MODE_RULES = (
    ("contract_review", ("【模式：合同审查】", "【模式：审查】", "模式：合同审查")),
    ("contract_draft", ("【模式：合同起草】", "【模式：起草】", "模式：合同起草")),
    ("consultation", ("【模式：诉前咨询】", "【模式：协商调解】", "模式：诉前咨询", "【模式：咨询】")),
    ("evidence_examination", ("【模式：证据质证】", "【模式：质证审查】", "模式：证据质证", "【模式：质证】")),
    ("execution_advisory", ("【模式：强制执行】", "【模式：执行查控】", "模式：强制执行", "【模式：执行】", "模式：执行查控")),
)

_CAUSE_RULES = (
    ("建设工程施工合同纠纷", ("工程", "施工", "承包", "分包", "转包", "资质", "实际施工人", "竣工", "工程款", "签证", "优先受偿权")),
    ("劳动争议纠纷", ("劳动", "辞退", "开除", "解雇", "二倍工资", "经济补偿金", "赔偿金", "加班费", "仲裁", "离职", "用人单位")),
    ("买卖合同纠纷", ("买卖", "货款", "交货", "收货", "产品", "货物", "采购", "标的物")),
    ("房屋租赁合同纠纷", ("租赁", "租房", "商铺", "退租", "押金", "转租", "房东", "租客", "免租期", "租金")),
    ("机动车交通事故责任纠纷", ("交通事故", "撞车", "交强险", "三者险", "商业险", "事故责任认定", "全责", "次责", "同等责任", "主责", "伤残等级")),
)

_ROLE_RULES = (
    ("plaintiff", ("【身份：原告律师】", "【角色：原告律师】")),
    ("defendant", ("【身份：被告律师】", "【角色：被告律师】")),
    ("corporate", ("【身份：企业法务】", "【角色：企业法务】")),
    ("citizen", ("【身份：大众维权】", "【角色：大众维权】", "【身份：当事人】")),
)

_ROLE_STATUS_MAP = {
    "plaintiff": "⚔️ 正在以【原告代理律师】视角拟定胜诉突围策略...",
    "defendant": "🛡️ 正在以【被告代理律师】视角挖掘原告证据硬伤与防御狙击...",
    "corporate": "🏢 正在以【企业法务总监】视角测算追偿可行性与草拟催告函...",
    "citizen": "🤝 正在以【当事人维权顾问】视角生成通俗白话指引与避坑清单...",
    "judge": "⚖️ 正在以【法官审判员】中立视角梳理案件事实与三段论要件...",
}


def _get_field(obj: Any, key: str, default: Any = "") -> Any:
    if hasattr(obj, key):
        return getattr(obj, key)
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def _format_aligner_section(node_output: Dict[str, Any], cause: str) -> str:
    facts = node_output.get("case_facts", [])
    evidence = node_output.get("evidence_items", [])
    missing = node_output.get("missing_evidence", [])

    facts_lines = [f"- 📌 **要素认定**: {_get_field(f, 'narrative', str(f))}" for f in facts]
    facts_block = "\n".join(facts_lines) if facts_lines else "- 暂无明确客观事实提取"

    ev_lines = [
        f"- 📄 **凭证**: 《{_get_field(e, 'title', str(e))}》（类型: `{_get_field(e, 'evidence_type', '书证')}` | "
        f"状态: `{_get_field(e, 'submission_status', '仅口头陈述提及（待提交）')}` | "
        f"效力: `{_get_field(e, 'authenticity_level', '存疑')}`）"
        for e in evidence
    ]
    ev_block = "\n".join(ev_lines) if ev_lines else "- 尚无已提交的书面/电子证据"

    miss_block = ""
    if missing:
        miss_lines = "\n".join(f"- ❗ {m}" for m in missing)
        miss_block = f"\n\n**【缺失/待补充凭证】**:\n{miss_lines}"

    return (
        f"### 📋 一、涉案案情事实认定与证据审查\n"
        f"> **审判案由**: `{cause}`\n\n"
        f"**【已查明事实要件】**:\n{facts_block}\n\n"
        f"**【证据凭证审查】**:\n{ev_block}{miss_block}\n\n---\n\n"
    )


def _format_planner_section(node_output: Dict[str, Any]) -> str:
    foci_lines = []
    for idx, fc in enumerate(node_output.get("dispute_foci", []), 1):
        stmt = _get_field(fc, "issue_statement", str(fc))
        statutes = _get_field(fc, "governing_statutes", []) or []
        statute_str = ", ".join(statutes) if statutes else "《民法典》相关规定"
        foci_lines.append(f"{idx}. 🎯 **争议焦点 {idx}**: {stmt} *(适用法条: {statute_str})*")
    foci_block = "\n".join(foci_lines) if foci_lines else "- 核心要件基本无争议"
    return f"### 🎯 二、法定构成要件与争议焦点\n{foci_block}\n\n---\n\n"


def _format_dialectic_section(node_output: Dict[str, Any]) -> str:
    turns = node_output.get("dialectic_history", [])
    text = "### ⚔️ 三、法庭红蓝攻防对抗推演\n"
    for turn in turns[-1:]:
        p_arg = _get_field(turn, "plaintiff_stance", "")
        d_arg = _get_field(turn, "defendant_defense", "")
        c_strat = _get_field(turn, "counter_strategy", "")
        text += (
            f"- 🔴 **原告攻击要件 (Plaintiff)**: {p_arg}\n"
            f"- 🔵 **被告抗辩防御 (Defendant)**: {d_arg}\n"
            f"- 🛡️ **诉讼突围策略 (Advise)**: {c_strat}\n\n"
        )
    return text + "---\n\n"


def _format_gate_section(node_output: Dict[str, Any]) -> str:
    passed = node_output.get("current_step") == "GATE_PASS"
    error_log = node_output.get("error_log")
    if not passed and error_log:
        return (
            "### 🛡️ 四、神经符号法理门禁审查\n"
            "> [!WARNING]\n"
            "> **法理门禁刚性拦截 / 实体法重大风险**:\n"
            f"> {error_log}\n\n---\n\n"
        )
    return (
        "### 🛡️ 四、神经符号法理门禁审查\n"
        "> [!NOTE]\n"
        "> **神经符号法理门禁审查通过**: 诉讼时效、利息上限与禁止反言审查通过（具体证据原件效力见下述核验提示）。\n\n---\n\n"
    )


def _format_hitl_card(snapshot_values: Dict[str, Any]) -> str:
    missing = list(snapshot_values.get("missing_evidence") or [])
    err = snapshot_values.get("error_log")
    items = []
    if err:
        items.append(f"- 🚨 **硬门禁阻塞项**: {err}")
    for m in missing:
        items.append(f"- 📎 **待补充/核验材料**: {m}")
    if not items:
        items.append("- 📎 **待核验材料**: 当前陈述提及的借条/合同/转账回单尚未提交原件核验")
    items_md = "\n".join(items)
    return (
        "### ⏸️ 人工介入核验：请补充缺失的证据材料\n"
        "> [!IMPORTANT]\n"
        "> 系统检测到关键证据缺口（或证据仅停留在口头陈述、尚未实际提交核验），已**主动中断终审心证**，请补充：\n\n"
        f"{items_md}\n\n"
        "**请直接在下方输入框回复补充证据**（例如：`已补充提交招行银行转账电子回单及借条原件，金额20万元`）；\n"
        "若暂无上述材料，请直接回复 **`跳过`**，系统将基于当前举证状态直接出具法官心证与风险提示。\n\n"
    )


def _build_initial_legal_state(session_id: str, cause: str, role: str, message: str) -> LegalCaseState:
    return LegalCaseState(
        thread_id=session_id,
        messages=[],
        metadata={"cause": cause, "user_question": message, "user_role": role},
        current_step="INIT",
        error_log=None,
        retry_count=0,
        is_awaiting_human=False,
        case_facts=[],
        evidence_items=[],
        dispute_foci=[],
        active_focus_id=None,
        dialectic_history=[],
        final_disposition=None,
        missing_evidence=[],
    )


def _render_dialectic_node(
    node_name: str,
    node_output: Dict[str, Any],
    cause: str,
) -> Optional[Tuple[str, str]]:
    if node_name == "ALIGNER":
        return "📋 客观事实提取与证据核验完成...", _format_aligner_section(node_output, cause)
    if node_name == "PLANNER":
        return "🎯 已锁定法定构成要件与争议焦点树...", _format_planner_section(node_output)
    if node_name == "DIALECTIC":
        return "⚔️ 红蓝攻防对抗完成，正在执行神经符号门禁...", _format_dialectic_section(node_output)
    if node_name == "GATE":
        return "🛡️ 神经符号门禁刚性审查完毕...", _format_gate_section(node_output)
    if node_name == "REPORTER":
        disposition = node_output.get("final_disposition", "")
        return "⚖️ 法官终审心证评判与诉讼策略生成完毕", f"{disposition}\n\n"
    return None


def _record_legal_session_turn(
    session_id: str,
    message: str,
    ai_reply: str,
    background_tasks: Optional[Any] = None,
) -> None:
    try:
        meta = session_store.record_turn(session_id, message, ai_reply, domain="legal")
        if meta.get("should_refine_title") and background_tasks is not None:
            background_tasks.add_task(
                session_store.refine_title_in_background, session_id, message, ai_reply, domain="legal"
            )
    except Exception as exc:
        logger.warning(f"[LegalStream] 会话元数据记录失败 [Session: {session_id}]: {exc}")


async def _stream_direct_legal_mode(
    mode: str,
    session_id: str,
    message: str,
    background_tasks: Optional[Any] = None,
) -> AsyncGenerator[str, None]:
    status_text, role_tag, runner_obj, method_name = _DIRECT_MODE_SPECS[mode]
    yield f"[[[STATUS: {status_text}]]]\n\n"
    text, usage = await getattr(runner_obj, method_name)(message)
    yield text
    prompt_tok = int(usage.get("prompt", 0))
    comp_tok = int(usage.get("completion", 0))
    yield f"\n\n[[[RESOURCE: {{'role': '{role_tag}', 'cost': 0.0, 'prompt': {prompt_tok}, 'completion': {comp_tok}}}]]]\n\n"
    history_manager.save_turn(session_id, message, text)
    _record_legal_session_turn(session_id, message, text, background_tasks=background_tasks)


class LegalStreamCoordinator:
    """民商事法律辩法核心流式编排器（支持 LangGraph HITL 中断与可注入持久化检查点）"""

    def __init__(self, checkpointer: Optional[Any] = None):
        self._checkpointer = checkpointer if checkpointer is not None else MemorySaver()
        self._graph = build_legal_graph(checkpointer=self._checkpointer, enable_hitl=True)

    def _detect_mode(self, message: str) -> str:
        for mode, markers in _MODE_RULES:
            if any(m in message for m in markers):
                return mode
        return "dialectic"

    def _detect_cause(self, message: str) -> str:
        for cause, keywords in _CAUSE_RULES:
            if any(kw in message for kw in keywords):
                return cause
        return "民间借贷纠纷"

    def _detect_role(self, message: str) -> str:
        for role, markers in _ROLE_RULES:
            if any(m in message for m in markers):
                return role
        return "judge"

    async def _stream_dialectic_graph(
        self,
        *,
        session_id: str,
        message: str,
        cause: str,
        role: str,
        is_resuming: bool,
        config: Dict[str, Any],
        background_tasks: Optional[Any] = None,
    ) -> AsyncGenerator[str, None]:
        if is_resuming:
            yield "[[[STATUS: 🔄 已接收补充材料，正在恢复辩法推演...]]]\n\n"
            graph_input: Any = Command(resume=message)
        else:
            role_status = _ROLE_STATUS_MAP.get(role, "⚖️ 正在分析民商事案件事实与争议焦点...")
            yield f"[[[STATUS: {role_status}]]]\n\n"
            graph_input = _build_initial_legal_state(session_id, cause, role, message)

        ai_response_content = ""
        token_usage: Dict[str, Any] = {"prompt": 0, "completion": 0, "model_id": "Argus-Legal"}
        try:
            async for event in self._graph.astream(graph_input, config):
                for node_name, node_output in event.items():
                    if not isinstance(node_output, dict):
                        continue
                    meta = node_output.get("metadata") or {}
                    if isinstance(meta.get("token_usage"), dict):
                        token_usage = meta["token_usage"]
                    rendered = _render_dialectic_node(node_name, node_output, cause)
                    if rendered is None:
                        continue
                    status_text, section_text = rendered
                    yield f"[[[STATUS: {status_text}]]]\n\n"
                    ai_response_content += section_text
                    yield section_text
                    if node_name != "REPORTER":
                        await asyncio.sleep(0.02)

            post_snapshot = await self._graph.aget_state(config)
            if post_snapshot and post_snapshot.next:
                hitl_card = _format_hitl_card(post_snapshot.values or {})
                yield "[[[STATUS: ⏸️ 等待人工补充缺失证据（或回复“跳过”继续）...]]]\n\n"
                ai_response_content += hitl_card
                yield hitl_card

            prompt_tok = int(token_usage.get("prompt", 0))
            comp_tok = int(token_usage.get("completion", 0))
            yield f"[[[RESOURCE: {{'role': 'JUDGE', 'cost': 0.0, 'prompt': {prompt_tok}, 'completion': {comp_tok}}}]]]\n\n"
            history_manager.save_turn(session_id, message, ai_response_content)
            _record_legal_session_turn(session_id, message, ai_response_content, background_tasks=background_tasks)
        except Exception as exc:
            logger.exception("Legal Agent 推演异常")
            err_text = f"\n\n> [!CAUTION]\n> **法律辩法推理中断**: {str(exc)}"
            ai_response_content += err_text
            yield err_text
            history_manager.save_turn(session_id, message, ai_response_content)
            _record_legal_session_turn(session_id, message, ai_response_content, background_tasks=background_tasks)

    async def coordinate_legal_stream(
        self,
        *,
        session_id: str,
        message: str,
        background_tasks: Optional[Any] = None,
    ) -> AsyncGenerator[str, None]:
        with redis_manager.dist_lock(f"session:in_flight:{session_id}", timeout=120) as acquired:
            if acquired is False:
                logger.warning(f"⚠️ [法律会话并发拦截] 会话 {session_id} 正在执行推演，拒绝并发请求。")
                yield "[[[STATUS: 正在处理上一轮法律辩法推演，请勿重复提交...]]]\n\n"
                yield "⚠️ 当前会话已有法律推演正在进行中，请等待上一轮完成后再发起新问题。"
                return

            config = {"configurable": {"thread_id": session_id}}
            snapshot = await self._graph.aget_state(config)
            is_resuming = bool(snapshot and snapshot.next)

            cause = self._detect_cause(message)
            role = self._detect_role(message)
            if is_resuming and snapshot.values:
                prev_meta = snapshot.values.get("metadata") or {}
                cause = prev_meta.get("cause", cause)
                role = prev_meta.get("user_role", role)

            yield "[[[ENGINE:Argus-Legal-Agent]]]"
            yield "[[[VERSION:Argus-Legal-v2.0]]]\n\n"

            mode = self._detect_mode(message)
            if mode != "dialectic":
                async for pkt in _stream_direct_legal_mode(mode, session_id, message, background_tasks=background_tasks):
                    yield pkt
                return

            async for pkt in self._stream_dialectic_graph(
                session_id=session_id,
                message=message,
                cause=cause,
                role=role,
                is_resuming=is_resuming,
                config=config,
                background_tasks=background_tasks,
            ):
                yield pkt


legal_stream_coordinator = LegalStreamCoordinator()
