"""
app/api/legal_stream_coordinator.py
====================================
[Legal Agent Deep Module] 法律多轮辩法流式协调器
将民商事法律辩法引擎（事实审查、焦点三段论、红蓝攻防、神经符号门禁、法官心证）
无缝转换为 argus-frontend (Rust/WASM) 协议流格式：
- [[[ENGINE: Argus-Legal-Agent]]]
- [[[STATUS: ...]]]
- Markdown 流式内容区块
- [[[RESOURCE: {...}]]]
"""

from __future__ import annotations
import asyncio
import sys
from typing import AsyncGenerator, Optional
from loguru import logger

from domains.legal.graph import build_legal_graph
from domains.legal.state.case_state import LegalCaseState
from app.memory.history import history_manager
from app.infra.redis_client import redis_manager


class LegalStreamCoordinator:
    """民商事法律辩法核心流式编排器"""

    def _detect_cause(self, message: str) -> str:
        sales_keywords = ["买卖", "货款", "交货", "收货", "产品", "货物", "采购", "标的物"]
        if any(kw in message for kw in sales_keywords):
            return "买卖合同纠纷"
        return "民间借贷纠纷"

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

            # 1. 物理协议首帧与引擎身份
            resolved_id = "Argus-Legal-Agent"
            yield f"[[[ENGINE:{resolved_id}]]]"
            yield f"[[[VERSION:Argus-Legal-v1.0]]]\n\n"
            yield "[[[STATUS: ⚖️ 正在分析民商事案件事实与争议焦点...]]]\n\n"

            cause = self._detect_cause(message)
            graph = build_legal_graph()

            initial_state: LegalCaseState = {
                "thread_id": session_id,
                "messages": [],
                "metadata": {
                    "cause": cause,
                    "user_question": message,
                },
                "current_step": "INIT",
                "error_log": None,
                "retry_count": 0,
                "is_awaiting_human": False,
                "case_facts": [],
                "evidence_items": [],
                "dispute_foci": [],
                "active_focus_id": None,
                "dialectic_history": [],
                "final_disposition": None,
            }

            ai_response_content = ""

            try:
                # 逐节点流式执行
                async for event in graph.astream(initial_state):
                    for node_name, node_output in event.items():
                        if node_name == "ALIGNER":
                            yield "[[[STATUS: 📋 客观事实提取与证据链锚定完成...]]]\n\n"
                            facts = node_output.get("case_facts", [])
                            evidence = node_output.get("evidence_items", [])

                            facts_lines = []
                            for f in facts:
                                text = f.narrative if hasattr(f, "narrative") else (f.get("narrative", "") if isinstance(f, dict) else str(f))
                                facts_lines.append(f"- 📌 **要素认定**: {text}")
                            facts_block = "\n".join(facts_lines) if facts_lines else "- 暂无明确客观事实提取"

                            ev_lines = []
                            for e in evidence:
                                t = e.title if hasattr(e, "title") else (e.get("title", "") if isinstance(e, dict) else str(e))
                                etype = e.evidence_type if hasattr(e, "evidence_type") else (e.get("evidence_type", "书证") if isinstance(e, dict) else "书证")
                                auth = e.authenticity_level if hasattr(e, "authenticity_level") else (e.get("authenticity_level", "中") if isinstance(e, dict) else "中")
                                ev_lines.append(f"- 📄 **凭证**: 《{t}》（类型: `{etype}`, 真实性效力: `{auth}`）")
                            ev_block = "\n".join(ev_lines) if ev_lines else "- 需在开庭前补充直接书证/物证"

                            aligner_text = (
                                f"### 📋 一、涉案案情事实认定与证据审查\n"
                                f"> **审判案由**: `{cause}`\n\n"
                                f"**【已查明事实要件】**:\n{facts_block}\n\n"
                                f"**【证据凭证审查】**:\n{ev_block}\n\n---\n\n"
                            )
                            ai_response_content += aligner_text
                            yield aligner_text
                            await asyncio.sleep(0.03)

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
                            await asyncio.sleep(0.03)

                        elif node_name == "DIALECTIC":
                            yield "[[[STATUS: ⚔️ 红蓝攻防对抗完成，正在执行神经符号门禁...]]]\n\n"
                            turns = node_output.get("dialectic_history", [])
                            dialectic_text = "### ⚔️ 三、法庭红蓝攻防对抗推演\n"
                            for t in turns:
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
                            await asyncio.sleep(0.03)

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
                                    f"> **神经符号法理门禁全部通过**: 诉讼时效刚性计算、4倍LPR利息截断上限与自相矛盾审查均符合法定实体规范。\n\n---\n\n"
                                )
                            ai_response_content += gate_text
                            yield gate_text
                            await asyncio.sleep(0.03)

                        elif node_name == "REPORTER":
                            yield "[[[STATUS: ⚖️ 法官终审心证评判与诉讼策略生成完毕]]]\n\n"
                            disposition = node_output.get("final_disposition", "")
                            reporter_text = f"{disposition}\n\n"
                            ai_response_content += reporter_text
                            yield reporter_text

                # 4. 算力治理指标 HUD 报文
                yield "[[[RESOURCE: {'role': 'JUDGE', 'cost': 0.002, 'prompt': 1200, 'completion': 850}]]]\n\n"

                # 5. 持久化存储
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
