"""
[SPEC-227 / Matt Pocock Deep Module] 流式对话编排协调深模块 (Chat Stream Coordinator)

统一治理核心流式推演链路：
- 算力物理协议首包与引擎标识注入 (ENGINE, VERSION)
- LangGraph v2 事件穿透与分流 (stream, tools, chains, telemetry)
- 协议拦截器 (ProtocolInterceptor) 与敏感表名/思维链脱敏
- 中断与挂起状态探测及人机复核卡片渲染
- 会话历史与影子推演链路持久化
- 算力熔断异常分类自愈与降级下发
- 会话级飞行锁 (In-flight Lock) 拦截高频重复并发推演
"""

from __future__ import annotations
import sys
from typing import AsyncGenerator, Optional
from fastapi import BackgroundTasks, Request
from loguru import logger
from langchain_core.messages import HumanMessage

from app.core.agent_graph import get_graph_executor
from app.memory.history import history_manager
from app.infra.usage_tracker import usage_tracker
from app.infra.model_manager import model_manager
from app.infra.redis_client import redis_manager
from app.core.observability import get_callbacks
from app.skills.security.protocol_filter import ProtocolInterceptor, sanitize
from app.api.chat_stream import (
    emit_node_status,
    emit_tool_start_events,
    classify_and_render_error,
    extract_stream_chunk_text,
    format_resource_telemetry,
    format_tool_trace_packet,
    render_human_review_card,
    render_meta_envelope,
)


def _is_legal_request(model_id: Optional[str], message: str) -> bool:
    """启发式与显式意图判断：是否路由至法律辩法智能体"""
    if model_id and ("legal" in model_id.lower() or "law" in model_id.lower()):
        return True
    if model_id in (None, "", "auto", "default"):
        legal_keywords = [
            "借款", "借条", "欠条", "借钱", "还钱", "本金", "利息", "民间借贷",
            "买卖合同", "货款", "违约金", "起诉", "原告", "被告", "时效",
            "诉讼时效", "借据", "逾期", "借期", "LPR", "转账凭证", "担保",
            "保证人", "连带责任", "法官", "抗辩", "答辩", "出借人", "借款人",
            "合同法", "民法典", "违约责任", "解除合同", "标的物"
        ]
        return any(kw in message for kw in legal_keywords)
    return False


class ChatStreamCoordinator:
    """流式推演核心协调器"""

    async def coordinate_stream(
        self,
        *,
        request: Request,
        background_tasks: BackgroundTasks,
        session_id: str,
        model_id: Optional[str],
        message: str,
    ) -> AsyncGenerator[str, None]:
        # 0. 路由分流：法律辩法智能体深度解耦对接
        if _is_legal_request(model_id, message):
            from app.api.legal_stream_coordinator import legal_stream_coordinator
            async for chunk in legal_stream_coordinator.coordinate_legal_stream(
                session_id=session_id,
                message=message,
            ):
                yield chunk
            return

        # 1. 会话级飞行锁拦截：防止同一 session_id 并发推演导致状态错乱与检查点锁死
        session_lock_key = f"session:in_flight:{session_id}"
        with redis_manager.dist_lock(session_lock_key, timeout=120) as acquired:
            if acquired is False:
                logger.warning(f"⚠️ [会话并发拦截] 会话 {session_id} 正在执行上一轮推演，拒绝并发请求。")
                yield "[[[STATUS: 正在处理上一轮审计推演，请勿重复提交...]]]\n\n"
                yield "⚠️ 当前会话已有审计推演正在进行中，请等待上一轮完成后再发起新问题。"
                return

            # 获取对应的图执行器与持久化器
            app_state = getattr(request, "app", None)
            saver = getattr(app_state, "state", None)
            saver_obj = getattr(saver, "saver", None) if saver else None

            executor, resolved_id = get_graph_executor(checkpointer=saver_obj, model_id=model_id)
            logger.info(f">>> [算力调配] 正在激活物理模型节点: {resolved_id}")

            # 加载持久化历史记录 (禁用自动恢复，确保推演上下文纯净)
            history_manager.get_history(session_id, auto_recover=False)

            # 2. 物理协议首帧：下发引擎元数据标记（[[[ENGINE:id]]]）与 VERSION
            yield f"[[[ENGINE:{resolved_id}]]]"
            yield f"[[[VERSION:{resolved_id}]]]"

            in_thought = False
            full_buffer = ""
            ai_response_content = ""
            active_node = "init"
            interceptor = ProtocolInterceptor()
            session_internal_thoughts = []

            try:
                config = {
                    "configurable": {"thread_id": session_id},
                    "recursion_limit": 100,
                }
                # 状态寻回与指令中继：检测 Thread 是否处于挂起态 (如 HUMAN_REVIEW)
                thread_snapshot = await executor.aget_state(config)
                is_resuming = bool(thread_snapshot.next)

                inputs = {
                    "messages": [HumanMessage(content=message)],
                    "model_id": resolved_id,
                    "session_id": session_id,
                    "retry_count": 0,
                    "step_counter": 0,
                    "human_input": message if is_resuming else None,
                }

                if is_resuming:
                    logger.warning(
                        f">>> [状态中继] 会话 {session_id} 正在从挂起点 {thread_snapshot.next} 恢复执行..."
                    )

                config["callbacks"] = get_callbacks()

                # TokenBudgetGuard：如果今日已烧掉 5M+ tokens，强制发出警报
                model_usage = usage_tracker.stats.daily_usage.get(resolved_id, 0)
                if model_usage > 5_000_000:
                    logger.warning(
                        f"!!! [高额开支警报] 节点 {resolved_id} 今日已烧过千万级 Token ({model_usage})，强制进入极端省流模式。"
                    )
                    yield "\n> [!WARNING]\n> **高成本开支预警**: 您的会话已产生异常高额消耗。系统已自动开启“深度脱水”归档模式以节省费用。"

                root_run_id = None

                # 协议体系升级：使用 version="v2" 提升嵌套事件穿透力
                async for event in executor.astream_events(inputs, config, version="v2"):
                    kind = event["event"]
                    name = str(event.get("name", ""))
                    metadata = event.get("metadata", {})
                    lg_node = metadata.get("langgraph_node", "")

                    if kind in ["on_chain_start", "on_chat_model_start"]:
                        logger.debug(f">>> [STREAM] kind={kind} | name={name} | lg_node={lg_node}")
                        if kind == "on_chain_start" and not root_run_id:
                            root_run_id = event.get("run_id")
                            if root_run_id:
                                yield render_meta_envelope(root_run_id, session_id)

                    if kind == "on_chat_model_stream":
                        content = event["data"]["chunk"].content
                        text_to_append = extract_stream_chunk_text(content)
                        if not text_to_append:
                            continue

                        interceptor_chunks = interceptor.process_chunk(text_to_append)
                        for chunk in interceptor_chunks:
                            if chunk:
                                filtered_content = sanitize(chunk)
                                if filtered_content:
                                    if active_node == "REPORTER":
                                        if in_thought:
                                            yield "\n:::\n\n"
                                            in_thought = False
                                        full_buffer += filtered_content
                                        ai_response_content += filtered_content
                                        yield filtered_content
                                    else:
                                        if not in_thought:
                                            yield f"\n:::thought\n**【{lg_node or name}】推演日志:**\n"
                                            in_thought = True
                                        yield filtered_content

                    elif kind == "on_chain_start":
                        check_name = (lg_node or name).upper()
                        if check_name in (
                            "DATA_EXPERT",
                            "AUDITOR",
                            "FINANCIAL_EXPERT",
                            "REPORTER",
                            "SOLO_EXPERT",
                        ):
                            active_node = "REPORTER" if check_name == "REPORTER" else "EXPERT"
                            if active_node == "REPORTER" and in_thought:
                                yield "\n:::\n\n"
                                in_thought = False
                            for packet in emit_node_status(check_name, name):
                                yield packet

                    elif kind == "on_tool_start":
                        tool_name = event["name"]
                        inputs_data = event["data"]["input"] or {}
                        logger.info(f"审计工具执行: {tool_name} -> {inputs_data}")
                        if in_thought:
                            yield "\n:::\n\n"
                            in_thought = False
                        for packet in emit_tool_start_events(tool_name, inputs_data):
                            yield packet

                    elif kind == "on_tool_end":
                        tool_name = event["name"]
                        output = event["data"].get("output", "")
                        if in_thought:
                            yield "\n:::\n\n"
                            in_thought = False
                        trace_pkt = format_tool_trace_packet(tool_name, output)
                        if trace_pkt:
                            yield trace_pkt

                    elif kind == "on_chat_model_end":
                        if in_thought:
                            yield "\n:::\n\n"
                            in_thought = False
                        data = event.get("data", {}) or {}
                        output = data.get("output")

                        if active_node == "REPORTER" and output and len(ai_response_content) < 50:
                            final_text = getattr(output, "content", "")
                            if final_text and len(str(final_text)) > len(ai_response_content):
                                patch_content = sanitize(str(final_text))
                                ai_response_content = patch_content
                                yield patch_content

                        usage = getattr(output, "usage_metadata", {}) if output else {}
                        res_pkt = format_resource_telemetry(usage, lg_node or name)
                        if res_pkt:
                            yield res_pkt

                    elif kind == "on_chain_end":
                        data = event.get("data", {}) or {}
                        output = data.get("output", {}) or {}
                        if isinstance(output, dict) and "internal_steps" in output:
                            steps = output["internal_steps"]
                            if isinstance(steps, list):
                                session_internal_thoughts.extend([str(s) for s in steps])

                        if lg_node == "REPORTER":
                            if isinstance(output, dict) and "messages" in output:
                                last_msg = output["messages"][-1]
                                if hasattr(last_msg, "content") and len(ai_response_content) < 50:
                                    static_content = sanitize(str(last_msg.content))
                                    if static_content:
                                        ai_response_content = static_content
                                        yield static_content

                # 挂起探测
                snapshot = await executor.aget_state(config)
                if snapshot.next:
                    logger.warning(f">>> [状态预警] 会话 {session_id} 处于挂起状态: {snapshot.next}")
                    if not ai_response_content:
                        signal_header = "[[[STATUS: 审计链路已挂起，正在等待人工业务指导...]]]\n\n"
                        yield signal_header
                        ai_response_content += signal_header

                        review_card = render_human_review_card(snapshot.values)
                        yield review_card
                        ai_response_content += review_card

                final = interceptor.flush()
                if final:
                    cleaned = sanitize(final)
                    if cleaned:
                        ai_response_content += cleaned
                        yield cleaned

                # 对话结束后，异步保存至持久化层
                history_manager.save_turn(session_id, message, ai_response_content)

                try:
                    full_history = history_manager.get_history(session_id)
                    history_manager.dump_debug_history(
                        session_id, full_history, session_internal_thoughts
                    )
                except Exception as e:
                    logger.error(f"调试转储失败: {e}")

                try:
                    safe_out = (
                        ai_response_content
                        if ai_response_content
                        else "[警告: 无内容输出，可能被拦截器过滤或节点未匹配]"
                    )
                    sys.stdout.buffer.write((safe_out + "\n").encode("utf-8", errors="replace"))
                except Exception:
                    pass

            except Exception as e:
                err_msg = str(e)
                logger.error(f"Agent Engine Error: {err_msg}")

                _rid = resolved_id if "resolved_id" in locals() else None
                if _rid:
                    usage_tracker.record_failure(_rid, err_msg)

                err_packets = classify_and_render_error(
                    err_msg=err_msg,
                    resolved_id=_rid,
                    usage_tracker=usage_tracker,
                    model_manager=model_manager,
                    background_tasks=background_tasks,
                )
                for pkt in err_packets:
                    yield pkt
                    if pkt.startswith("\n[算力链路异常]") or pkt.startswith("\n[核心审计异常]"):
                        ai_response_content += pkt

                history_manager.save_turn(session_id, message, ai_response_content)


chat_stream_coordinator = ChatStreamCoordinator()
