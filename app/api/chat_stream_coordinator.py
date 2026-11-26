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
from typing import AsyncGenerator, Iterator, List, Optional, Tuple
from fastapi import BackgroundTasks, Request
from loguru import logger
from langchain_core.messages import HumanMessage

from app.orchestration.agent_graph import get_graph_executor
from app.core.memory.history import history_manager
from app.infra.usage_tracker import usage_tracker
from app.infra.model_manager import model_manager
from app.infra.redis_client import redis_manager
from app.core.observability import get_callbacks
from app.skills.security.protocol_filter import ProtocolInterceptor, sanitize
from app.api.events.sse_contract import SSEEvent, SSEEventType
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


def _resolve_checkpointer(request: Request):
    """DI 接缝：从 FastAPI app.state 解析 lifespan 注入的状态持久化层"""
    app_state = getattr(request, "app", None)
    saver = getattr(app_state, "state", None)
    return getattr(saver, "saver", None) if saver else None


class _StreamRenderState:
    """流式渲染会话状态数据契约 (SSOT)

    一次推演内的全部可变渲染上下文单点持有, 经内部缝显式传递,
    取代散落在 coordinate_stream 闭包中的可变局部变量。
    """

    def __init__(self):
        self.in_thought = False                   # 是否处于 :::thought 推演日志帧内
        self.ai_response_content = ""             # 下发给用户的正文累计
        self.active_node = "init"                 # 当前活动节点 (REPORTER 可见 / EXPERT 隐藏)
        self.interceptor = ProtocolInterceptor()  # 协议拦截器 (thought 标签变体过滤)
        self.internal_thoughts: List[str] = []    # on_chain_end 收集的内部推演步骤
        self.root_run_id: Optional[str] = None    # 首个 on_chain_start 捕获的根 run_id
        self.reporter_stream_buffer: str = ""     # REPORTER 缓冲流，待门禁完成后放行或回退
        self.reporter_final_emitted: bool = False  # REPORTER 经门禁净化后的终稿是否已下发


class _LangGraphEventTranslator:
    """LangGraph v2 事件 → 流式协议帧 翻译状态机 (内部缝)

    输出不变式: 仅 REPORTER 节点输出作为正文帧 (前端可见), 其余所有节点
    输出统一包进 :::thought 推演日志帧 (前端折叠)。主图新增节点自动成为
    不可见 thought 帧; 若需对新节点可见, 仅修改本类的分派逻辑。
    """

    def __init__(self, session_id: str, is_sse: bool = False):
        self._session_id = session_id
        self._is_sse = is_sse

    def translate(self, event: dict, state: _StreamRenderState) -> Iterator[str]:
        """将单个 astream_events 事件翻译为 0..N 个协议帧 (同步纯转换, 无 IO)"""
        kind = event["event"]
        name = str(event.get("name", ""))
        metadata = event.get("metadata", {})
        lg_node = metadata.get("langgraph_node", "")

        if kind in ["on_chain_start", "on_chat_model_start"]:
            logger.debug(f">>> [STREAM] kind={kind} | name={name} | lg_node={lg_node}")
            if kind == "on_chain_start" and not state.root_run_id:
                state.root_run_id = event.get("run_id")
                if state.root_run_id:
                    if self._is_sse:
                        yield SSEEvent(
                            event=SSEEventType.ENGINE,
                            data={"root_run_id": str(state.root_run_id), "session_id": self._session_id}
                        ).to_sse_packet()
                    else:
                        yield render_meta_envelope(state.root_run_id, self._session_id)

        if kind == "on_chat_model_stream":
            content = event["data"]["chunk"].content
            text_to_append = extract_stream_chunk_text(content)
            if not text_to_append:
                return
            interceptor_chunks = state.interceptor.process_chunk(text_to_append)
            for chunk in interceptor_chunks:
                if chunk:
                    filtered_content = sanitize(chunk)
                    if filtered_content:
                        if state.active_node == "REPORTER":
                            if state.in_thought:
                                if not self._is_sse:
                                    yield "\n:::\n\n"
                                state.in_thought = False
                            state.reporter_stream_buffer += filtered_content
                        else:
                            if not state.in_thought:
                                if not self._is_sse:
                                    yield f"\n:::thought\n**【{lg_node or name}】推演日志:**\n"
                                state.in_thought = True
                            if self._is_sse:
                                yield SSEEvent(
                                    event=SSEEventType.THOUGHT,
                                    data={"node": lg_node or name, "text": filtered_content}
                                ).to_sse_packet()
                            else:
                                yield filtered_content

        elif kind == "on_chain_start":
            check_name = (lg_node or name).upper()
            if check_name in (
                "DATA_EXPERT",
                "AUDITOR",
                "FINANCIAL_EXPERT",
                "MULTI_AGENT_HUB",
                "REPORTER",
                "SOLO_EXPERT",
            ):
                state.active_node = "REPORTER" if check_name == "REPORTER" else "EXPERT"
                if state.active_node == "REPORTER" and state.in_thought:
                    if not self._is_sse:
                        yield "\n:::\n\n"
                    state.in_thought = False
                if self._is_sse:
                    yield SSEEvent(
                        event=SSEEventType.STATUS,
                        data={"node": check_name, "name": name, "display_name": f"正在激活 [{check_name}] 进行推演..."}
                    ).to_sse_packet()
                else:
                    for packet in emit_node_status(check_name, name):
                        yield packet

        elif kind == "on_tool_start":
            tool_name = event["name"]
            inputs_data = event["data"]["input"] or {}
            logger.info(f"审计工具执行: {tool_name} -> {inputs_data}")
            if state.in_thought:
                if not self._is_sse:
                    yield "\n:::\n\n"
                state.in_thought = False
            if self._is_sse:
                yield SSEEvent(
                    event=SSEEventType.ACTION,
                    data={"tool": tool_name, "inputs": inputs_data}
                ).to_sse_packet()
            else:
                for packet in emit_tool_start_events(tool_name, inputs_data):
                    yield packet

        elif kind == "on_tool_end":
            tool_name = event["name"]
            output = event["data"].get("output", "")
            if state.in_thought:
                if not self._is_sse:
                    yield "\n:::\n\n"
                state.in_thought = False
            if self._is_sse:
                yield SSEEvent(
                    event=SSEEventType.ACTION,
                    data={"tool": tool_name, "stage": "end", "output": str(output)[:300]}
                ).to_sse_packet()
            else:
                trace_pkt = format_tool_trace_packet(tool_name, output)
                if trace_pkt:
                    yield trace_pkt

        elif kind == "on_chat_model_end":
            if state.in_thought:
                if not self._is_sse:
                    yield "\n:::\n\n"
                state.in_thought = False
            data = event.get("data", {}) or {}
            output = data.get("output")

            if state.active_node == "REPORTER" and output and not state.reporter_final_emitted:
                final_text = getattr(output, "content", "")
                if final_text and len(str(final_text)) > len(state.reporter_stream_buffer):
                    state.reporter_stream_buffer = sanitize(str(final_text))

            usage = getattr(output, "usage_metadata", {}) if output else {}
            if self._is_sse:
                if usage:
                    yield SSEEvent(
                        event=SSEEventType.RESOURCE,
                        data={"role": lg_node or name, "usage": usage}
                    ).to_sse_packet()
            else:
                res_pkt = format_resource_telemetry(usage, lg_node or name)
                if res_pkt:
                    yield res_pkt

        elif kind == "on_chain_end":
            data = event.get("data", {}) or {}
            output = data.get("output", {}) or {}
            if isinstance(output, dict) and "internal_steps" in output:
                steps = output["internal_steps"]
                if isinstance(steps, list):
                    state.internal_thoughts.extend([str(s) for s in steps])

            if lg_node == "REPORTER":
                if isinstance(output, dict) and output.get("messages"):
                    last_msg = output["messages"][-1]
                    if hasattr(last_msg, "content") and not state.reporter_final_emitted:
                        static_content = sanitize(str(last_msg.content))
                        if static_content:
                            state.ai_response_content = static_content
                            state.reporter_final_emitted = True
                            state.reporter_stream_buffer = ""
                            if self._is_sse:
                                yield SSEEvent(event=SSEEventType.MESSAGE, data=static_content).to_sse_packet()
                            else:
                                yield static_content


class ChatStreamCoordinator:
    """流式推演核心协调器 (外部缝: coordinate_stream 窄接口; 内部缝: 事件翻译状态机 + 渲染状态契约)"""

    async def coordinate_stream(
        self,
        *,
        request: Request,
        background_tasks: BackgroundTasks,
        session_id: str,
        model_id: Optional[str],
        message: str,
        stream_format: str = "auto",
    ) -> AsyncGenerator[str, None]:
        # 确定流式协议格式 (W3C SSE vs Legacy in-band text)
        is_sse = False
        if stream_format == "sse":
            is_sse = True
        elif stream_format == "legacy":
            is_sse = False
        else:
            accept_hdr = getattr(request, "headers", {}).get("accept", "") if request else ""
            q_fmt = getattr(request, "query_params", {}).get("format", "") if request else ""
            is_sse = ("text/event-stream" in str(accept_hdr)) or (str(q_fmt) == "sse")

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
                if is_sse:
                    yield SSEEvent(
                        event=SSEEventType.STATUS,
                        data={"message": "正在处理上一轮审计推演，请勿重复提交...", "in_flight": True}
                    ).to_sse_packet()
                    yield SSEEvent(
                        event=SSEEventType.MESSAGE,
                        data="⚠️ 当前会话已有审计推演正在进行中，请等待上一轮完成后再发起新问题。"
                    ).to_sse_packet()
                    yield SSEEvent(
                        event=SSEEventType.DONE,
                        data="[DONE]"
                    ).to_sse_packet()
                else:
                    yield "[[[STATUS: 正在处理上一轮审计推演，请勿重复提交...]]]\n\n"
                    yield "⚠️ 当前会话已有审计推演正在进行中，请等待上一轮完成后再发起新问题。"
                return

            executor, resolved_id = get_graph_executor(
                checkpointer=_resolve_checkpointer(request), model_id=model_id
            )
            logger.info(f">>> [算力调配] 正在激活物理模型节点: {resolved_id}")

            # 加载持久化历史记录 (禁用自动恢复，确保推演上下文纯净)
            history_manager.get_history(session_id, auto_recover=False)

            # 2. 物理协议首帧：下发引擎元数据标记（[[[ENGINE:id]]]）与 VERSION
            if is_sse:
                yield SSEEvent(event=SSEEventType.ENGINE, data=resolved_id).to_sse_packet()
                yield SSEEvent(event=SSEEventType.VERSION, data=resolved_id).to_sse_packet()
            else:
                yield f"[[[ENGINE:{resolved_id}]]]"
                yield f"[[[VERSION:{resolved_id}]]]"

            # [Matt Deep Module] 渲染状态捆成单一数据契约 (SSOT), 事件翻译收敛到内部缝
            state = _StreamRenderState()
            translator = _LangGraphEventTranslator(session_id, is_sse=is_sse)

            try:
                config, inputs, budget_warning = await self._prepare_run(
                    executor, session_id, message, resolved_id
                )
                if budget_warning:
                    if is_sse:
                        yield SSEEvent(event=SSEEventType.STATUS, data={"warning": budget_warning}).to_sse_packet()
                    else:
                        yield budget_warning

                # 协议体系升级：使用 version="v2" 提升嵌套事件穿透力
                async for event in executor.astream_events(inputs, config, version="v2"):
                    for packet in translator.translate(event, state):
                        yield packet

                # 收尾固化：挂起探测、拦截器残余 flush、历史落盘 (stdout 调试残留已移除)
                async for packet in self._finalize_run(executor, config, session_id, message, state, is_sse=is_sse):
                    yield packet

                if is_sse:
                    yield SSEEvent(event=SSEEventType.DONE, data="[DONE]").to_sse_packet()

            except Exception as e:
                async for pkt in self._handle_stream_failure(
                    str(e), resolved_id, session_id, message, background_tasks, state, is_sse=is_sse
                ):
                    yield pkt


    async def _prepare_run(
        self,
        executor,
        session_id: str,
        message: str,
        resolved_id: str,
    ) -> Tuple[dict, dict, Optional[str]]:
        """状态寻回与运行输入装配 (关键数据单次抽取: 挂起快照只读一次, 装配即定型)"""
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
        budget_warning = None
        model_usage = usage_tracker.stats.daily_usage.get(resolved_id, 0)
        if model_usage > 5_000_000:
            logger.warning(
                f"!!! [高额开支警报] 节点 {resolved_id} 今日已烧过千万级 Token ({model_usage})，强制进入极端省流模式。"
            )
            budget_warning = "\n> [!WARNING]\n> **高成本开支预警**: 您的会话已产生异常高额消耗。系统已自动开启“深度脱水”归档模式以节省费用。"

        return config, inputs, budget_warning

    async def _finalize_run(
        self,
        executor,
        config: dict,
        session_id: str,
        message: str,
        state: _StreamRenderState,
        is_sse: bool = False,
    ) -> AsyncGenerator[str, None]:
        """收尾固化：挂起探测、拦截器残余 flush、会话历史与调试转储落盘"""
        snapshot = await executor.aget_state(config)
        if snapshot.next:
            logger.warning(f">>> [状态预警] 会话 {session_id} 处于挂起状态: {snapshot.next}")
            if not state.ai_response_content:
                review_card = render_human_review_card(snapshot.values)
                if is_sse:
                    yield SSEEvent(
                        event=SSEEventType.STATUS,
                        data={"stage": "SUSPENDED_FOR_REVIEW", "message": "审计链路已挂起，正在等待人工业务指导..."}
                    ).to_sse_packet()
                    yield SSEEvent(event=SSEEventType.MESSAGE, data=review_card).to_sse_packet()
                else:
                    signal_header = "[[[STATUS: 审计链路已挂起，正在等待人工业务指导...]]]\n\n"
                    yield signal_header
                    state.ai_response_content += signal_header
                    yield review_card
                state.ai_response_content += review_card

        final = state.interceptor.flush()
        if final:
            cleaned = sanitize(final)
            if cleaned:
                if state.active_node == "REPORTER":
                    if not state.reporter_final_emitted:
                        state.reporter_stream_buffer += cleaned
                else:
                    state.ai_response_content += cleaned
                    if is_sse:
                        yield SSEEvent(event=SSEEventType.MESSAGE, data=cleaned).to_sse_packet()
                    else:
                        yield cleaned

        if not state.reporter_final_emitted and state.reporter_stream_buffer:
            buffered = state.reporter_stream_buffer
            state.reporter_stream_buffer = ""
            state.ai_response_content += buffered
            if is_sse:
                yield SSEEvent(event=SSEEventType.MESSAGE, data=buffered).to_sse_packet()
            else:
                yield buffered

        # 对话结束后，异步保存至持久化层
        history_manager.save_turn(session_id, message, state.ai_response_content)

        try:
            full_history = history_manager.get_history(session_id)
            history_manager.dump_debug_history(
                session_id, full_history, state.internal_thoughts
            )
        except Exception as e:
            logger.error(f"调试转储失败: {e}")

    async def _handle_stream_failure(
        self,
        err_msg: str,
        resolved_id: str,
        session_id: str,
        message: str,
        background_tasks: BackgroundTasks,
        state: _StreamRenderState,
        is_sse: bool = False,
    ) -> AsyncGenerator[str, None]:
        """熔断异常分类自愈与降级下发 (resolved_id 在 try 前必然已装配, 无需 locals 防御)"""
        logger.error(f"Agent Engine Error: {err_msg}")

        usage_tracker.record_failure(resolved_id, err_msg)

        err_packets = classify_and_render_error(
            err_msg=err_msg,
            resolved_id=resolved_id,
            usage_tracker=usage_tracker,
            model_manager=model_manager,
            background_tasks=background_tasks,
        )
        if is_sse:
            yield SSEEvent(
                event=SSEEventType.ERROR,
                data={"error": err_msg, "model_id": resolved_id}
            ).to_sse_packet()
            for pkt in err_packets:
                yield SSEEvent(event=SSEEventType.MESSAGE, data=pkt).to_sse_packet()
                if pkt.startswith("\n[算力链路异常]") or pkt.startswith("\n[核心审计异常]"):
                    state.ai_response_content += pkt
            yield SSEEvent(event=SSEEventType.DONE, data="[DONE]").to_sse_packet()
        else:
            for pkt in err_packets:
                yield pkt
                if pkt.startswith("\n[算力链路异常]") or pkt.startswith("\n[核心审计异常]"):
                    state.ai_response_content += pkt

        history_manager.save_turn(session_id, message, state.ai_response_content)


chat_stream_coordinator = ChatStreamCoordinator()
