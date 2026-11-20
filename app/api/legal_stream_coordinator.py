"""
app/api/legal_stream_coordinator.py
====================================
[Legal Agent Deep Module] 法律多轮辩法流式协调器
将民商事法律辩法引擎（事实审查、焦点三段论、红蓝攻防、神经符号门禁、HITL 人工补证中断、法官心证）
无缝转换为 argus-frontend (Rust/WASM) 协议流格式。
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any, AsyncGenerator, Dict, Optional
from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from loguru import logger

from domains.legal.graph import build_legal_graph
from domains.legal.state.case_state import LegalCaseState
from domains.legal.agents.contract_reviewer import contract_reviewer
from domains.legal.agents.contract_drafter import contract_drafter
from domains.legal.agents.consultation_advisor import consultation_advisor
from app.memory.history import history_manager
from app.infra.redis_client import redis_manager


class LegalStreamCoordinator:
    """民商事法律辩法核心流式编排器（支持 LangGraph HITL 中断与中继恢复）"""

    def __init__(self):
        self._checkpointer = MemorySaver()
        self._graph = build_legal_graph(checkpointer=self._checkpointer, enable_hitl=True)

    def _detect_mode(self, message: str) -> str:
        if "【模式：合同审查】" in message or "【模式：审查】" in message or "模式：合同审查" in message:
            return "contract_review"
        if "【模式：合同起草】" in message or "【模式：起草】" in message or "模式：合同起草" in message:
            return "contract_draft"
        if "【模式：诉前咨询】" in message or "【模式：协商调解】" in message or "模式：诉前咨询" in message or "【模式：咨询】" in message:
            return "consultation"
        return "dialectic"

    def _detect_cause(self, message: str) -> str:
        construction_keywords = ["工程", "施工", "承包", "分包", "转包", "资质", "实际施工人", "竣工", "工程款", "签证", "优先受偿权"]
        labor_keywords = ["劳动", "辞退", "开除", "解雇", "二倍工资", "经济补偿金", "赔偿金", "加班费", "仲裁", "离职", "用人单位"]
        sales_keywords = ["买卖", "货款", "交货", "收货", "产品", "货物", "采购", "标的物"]
        if any(kw in message for kw in construction_keywords):
            return "建设工程施工合同纠纷"
        if any(kw in message for kw in labor_keywords):
            return "劳动争议纠纷"
        if any(kw in message for kw in sales_keywords):
            return "买卖合同纠纷"
        return "民间借贷纠纷"

    def _detect_role(self, message: str) -> str:
        if "【身份：原告律师】" in message or "【角色：原告律师】" in message:
            return "plaintiff"
        if "【身份：被告律师】" in message or "【角色：被告律师】" in message:
            return "defendant"
        if "【身份：企业法务】" in message or "【角色：企业法务】" in message:
            return "corporate"
        if "【身份：大众维权】" in message or "【角色：大众维权】" in message or "【身份：当事人】" in message:
            return "citizen"
        return "judge"

    async def coordinate_legal_stream(
        self,
        *,
        session_id: str,
        message: str,
    ) -> AsyncGenerator[str, None]:
        session_lock_key = f"session:in_flight:{session_id}"
        with redis_manager.dist_lock(session_lock_key, timeout=120) as acquired:
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
            if not is_resuming and mode != "dialectic":
                if mode == "contract_review":
                    yield "[[[STATUS: 🔍 正在执行合同智能审查与高危红线排查...]]]\n\n"
                    text, usage = await contract_reviewer.areview(message)
                    yield text
                    prompt_tok = int(usage.get("prompt", 0))
                    comp_tok = int(usage.get("completion", 0))
                    yield f"\n\n[[[RESOURCE: {{'role': 'REVIEWER', 'cost': 0.0, 'prompt': {prompt_tok}, 'completion': {comp_tok}}}]]]\n\n"
                    history_manager.save_turn(session_id, message, text)
                    try:
                        sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))
                    except Exception:
                        pass
                    return

                if mode == "contract_draft":
                    yield "[[[STATUS: 📝 正在依据民法典及行业规范起草合规合同草案...]]]\n\n"
                    text, usage = await contract_drafter.adraft(message)
                    yield text
                    prompt_tok = int(usage.get("prompt", 0))
                    comp_tok = int(usage.get("completion", 0))
                    yield f"\n\n[[[RESOURCE: {{'role': 'DRAFTER', 'cost': 0.0, 'prompt': {prompt_tok}, 'completion': {comp_tok}}}]]]\n\n"
                    history_manager.save_turn(session_id, message, text)
                    try:
                        sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))
                    except Exception:
                        pass
                    return

                if mode == "consultation":
                    yield "[[[STATUS: 💬 正在梳理法律关系、博弈筹码与定制诉前谈判方案...]]]\n\n"
                    text, usage = await consultation_advisor.aadvise(message)
                    yield text
                    prompt_tok = int(usage.get("prompt", 0))
                    comp_tok = int(usage.get("completion", 0))
                    yield f"\n\n[[[RESOURCE: {{'role': 'ADVISOR', 'cost': 0.0, 'prompt': {prompt_tok}, 'completion': {comp_tok}}}]]]\n\n"
                    history_manager.save_turn(session_id, message, text)
                    try:
                        sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))
                    except Exception:
                        pass
                    return

            if is_resuming:
                yield "[[[STATUS: 🔄 已接收补充材料，正在恢复辩法推演...]]]\n\n"
                graph_input: Any = Command(resume=message)
            else:
                role_status = {
                    "plaintiff": "⚔️ 正在以【原告代理律师】视角拟定胜诉突围策略...",
                    "defendant": "🛡️ 正在以【被告代理律师】视角挖掘原告证据硬伤与防御狙击...",
                    "corporate": "🏢 正在以【企业法务总监】视角测算追偿可行性与草拟催告函...",
                    "citizen": "🤝 正在以【当事人维权顾问】视角生成通俗白话指引与避坑清单...",
                    "judge": "⚖️ 正在以【法官审判员】中立视角梳理案件事实与三段论要件...",
                }.get(role, "⚖️ 正在分析民商事案件事实与争议焦点...")
                yield f"[[[STATUS: {role_status}]]]\n\n"
                graph_input = LegalCaseState(
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

                        if node_name == "ALIGNER":
                            yield "[[[STATUS: 📋 客观事实提取与证据核验完成...]]]\n\n"
                            facts = node_output.get("case_facts", [])
                            evidence = node_output.get("evidence_items", [])
                            missing = node_output.get("missing_evidence", [])

                            facts_lines = []
                            for f in facts:
                                text = f.narrative if hasattr(f, "narrative") else (f.get("narrative", "") if isinstance(f, dict) else str(f))
                                facts_lines.append(f"- 📌 **要素认定**: {text}")
                            facts_block = "\n".join(facts_lines) if facts_lines else "- 暂无明确客观事实提取"

                            ev_lines = []
                            for e in evidence:
                                t = e.title if hasattr(e, "title") else (e.get("title", "") if isinstance(e, dict) else str(e))
                                etype = e.evidence_type if hasattr(e, "evidence_type") else (e.get("evidence_type", "书证") if isinstance(e, dict) else "书证")
                                auth = e.authenticity_level if hasattr(e, "authenticity_level") else (e.get("authenticity_level", "存疑") if isinstance(e, dict) else "存疑")
                                sub = e.submission_status if hasattr(e, "submission_status") else (e.get("submission_status", "仅口头陈述提及（待提交）") if isinstance(e, dict) else "仅口头陈述提及（待提交）")
                                ev_lines.append(f"- 📄 **凭证**: 《{t}》（类型: `{etype}` | 状态: `{sub}` | 效力: `{auth}`）")
                            ev_block = "\n".join(ev_lines) if ev_lines else "- 尚无已提交的书面/电子证据"

                            miss_block = ""
                            if missing:
                                miss_lines = "\n".join(f"- ❗ {m}" for m in missing)
                                miss_block = f"\n\n**【缺失/待补充凭证】**:\n{miss_lines}"

                            aligner_text = (
                                f"### 📋 一、涉案案情事实认定与证据审查\n"
                                f"> **审判案由**: `{cause}`\n\n"
                                f"**【已查明事实要件】**:\n{facts_block}\n\n"
                                f"**【证据凭证审查】**:\n{ev_block}{miss_block}\n\n---\n\n"
                            )
                            ai_response_content += aligner_text
                            yield aligner_text
                            await asyncio.sleep(0.02)

                        elif node_name == "PLANNER":
                            yield "[[[STATUS: 🎯 已锁定法定构成要件与争议焦点树...]]]\n\n"
                            foci = node_output.get("dispute_foci", [])
                            foci_lines = []
                            for i, fc in enumerate(foci, 1):
                                stmt = fc.issue_statement if hasattr(fc, "issue_statement") else (fc.get("issue_statement", "") if isinstance(fc, dict) else str(fc))
                                statutes = fc.governing_statutes if hasattr(fc, "governing_statutes") else (fc.get("governing_statutes", []) if isinstance(fc, dict) else [])
                                statute_str = ", ".join(statutes) if statutes else "《民法典》相关规定"
                                foci_lines.append(f"{i}. 🎯 **争议焦点 {i}**: {stmt} *(适用法条: {statute_str})*")
                            foci_block = "\n".join(foci_lines) if foci_lines else "- 核心要件基本无争议"

                            planner_text = (
                                f"### 🎯 二、法定构成要件与争议焦点\n"
                                f"{foci_block}\n\n---\n\n"
                            )
                            ai_response_content += planner_text
                            yield planner_text
                            await asyncio.sleep(0.02)

                        elif node_name == "DIALECTIC":
                            yield "[[[STATUS: ⚔️ 红蓝攻防对抗完成，正在执行神经符号门禁...]]]\n\n"
                            turns = node_output.get("dialectic_history", [])
                            dialectic_text = "### ⚔️ 三、法庭红蓝攻防对抗推演\n"
                            for t in turns[-1:]:
                                p_arg = t.plaintiff_stance if hasattr(t, "plaintiff_stance") else (t.get("plaintiff_stance", "") if isinstance(t, dict) else "")
                                d_arg = t.defendant_defense if hasattr(t, "defendant_defense") else (t.get("defendant_defense", "") if isinstance(t, dict) else "")
                                c_strat = t.counter_strategy if hasattr(t, "counter_strategy") else (t.get("counter_strategy", "") if isinstance(t, dict) else "")
                                dialectic_text += (
                                    f"- 🔴 **原告攻击要件 (Plaintiff)**: {p_arg}\n"
                                    f"- 🔵 **被告抗辩防御 (Defendant)**: {d_arg}\n"
                                    f"- 🛡️ **诉讼突围策略 (Advise)**: {c_strat}\n\n"
                                )
                            dialectic_text += "---\n\n"
                            ai_response_content += dialectic_text
                            yield dialectic_text
                            await asyncio.sleep(0.02)

                        elif node_name == "GATE":
                            yield "[[[STATUS: 🛡️ 神经符号门禁刚性审查完毕...]]]\n\n"
                            passed = node_output.get("current_step") == "GATE_PASS"
                            error_log = node_output.get("error_log")

                            if not passed and error_log:
                                gate_text = (
                                    f"### 🛡️ 四、神经符号法理门禁审查\n"
                                    f"> [!WARNING]\n"
                                    f"> **法理门禁刚性拦截 / 实体法重大风险**:\n"
                                    f"> {error_log}\n\n---\n\n"
                                )
                            else:
                                gate_text = (
                                    f"### 🛡️ 四、神经符号法理门禁审查\n"
                                    f"> [!NOTE]\n"
                                    f"> **神经符号法理门禁审查通过**: 诉讼时效、利息上限与禁止反言审查通过（具体证据原件效力见下述核验提示）。\n\n---\n\n"
                                )
                            ai_response_content += gate_text
                            yield gate_text
                            await asyncio.sleep(0.02)

                        elif node_name == "REPORTER":
                            yield "[[[STATUS: ⚖️ 法官终审心证评判与诉讼策略生成完毕]]]\n\n"
                            disposition = node_output.get("final_disposition", "")
                            reporter_text = f"{disposition}\n\n"
                            ai_response_content += reporter_text
                            yield reporter_text

                # 检查是否触发了 HITL 人工介入中断
                post_snapshot = await self._graph.aget_state(config)
                if post_snapshot and post_snapshot.next:
                    vals = post_snapshot.values or {}
                    missing = list(vals.get("missing_evidence") or [])
                    err = vals.get("error_log")
                    items = []
                    if err:
                        items.append(f"- 🚨 **硬门禁阻塞项**: {err}")
                    for m in missing:
                        items.append(f"- 📎 **待补充/核验材料**: {m}")
                    if not items:
                        items.append("- 📎 **待核验材料**: 当前陈述提及的借条/合同/转账回单尚未提交原件核验")
                    items_md = "\n".join(items)

                    hitl_card = (
                        f"### ⏸️ 人工介入核验：请补充缺失的证据材料\n"
                        f"> [!IMPORTANT]\n"
                        f"> 系统检测到关键证据缺口（或证据仅停留在口头陈述、尚未实际提交核验），已**主动中断终审心证**，请补充：\n\n"
                        f"{items_md}\n\n"
                        f"**请直接在下方输入框回复补充证据**（例如：`已补充提交招行银行转账电子回单及借条原件，金额20万元`）；\n"
                        f"若暂无上述材料，请直接回复 **`跳过`**，系统将基于当前举证状态直接出具法官心证与风险提示。\n\n"
                    )
                    yield "[[[STATUS: ⏸️ 等待人工补充缺失证据（或回复“跳过”继续）...]]]\n\n"
                    ai_response_content += hitl_card
                    yield hitl_card

                prompt_tok = int(token_usage.get("prompt", 0))
                comp_tok = int(token_usage.get("completion", 0))
                yield f"[[[RESOURCE: {{'role': 'JUDGE', 'cost': 0.0, 'prompt': {prompt_tok}, 'completion': {comp_tok}}}]]]\n\n"

                history_manager.save_turn(session_id, message, ai_response_content)

                try:
                    sys.stdout.buffer.write((ai_response_content + "\n").encode("utf-8", errors="replace"))
                except Exception:
                    pass

            except Exception as e:
                logger.exception("Legal Agent 推演异常")
                err_text = f"\n\n> [!CAUTION]\n> **法律辩法推理中断**: {str(e)}"
                ai_response_content += err_text
                yield err_text
                history_manager.save_turn(session_id, message, ai_response_content)


legal_stream_coordinator = LegalStreamCoordinator()
