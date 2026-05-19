"""
app/routes/chat.py
==================
核心流式对话路由，从 main.py 提取。
保持 API 路径不变: /agent/chat, /ins-fqz/agent/chat
"""

from typing import AsyncGenerator

from fastapi import APIRouter, Request, BackgroundTasks
from fastapi.responses import StreamingResponse
from loguru import logger
from langchain_core.messages import HumanMessage

from app.core.agent_graph import get_graph_executor
from app.memory.history import history_manager
from app.infra.usage_tracker import usage_tracker
from app.core.observability import get_callbacks
from app.skills.protocol_filter import ProtocolInterceptor, sanitize
from app.api.chat_stream import (
    parse_chat_request,
    emit_node_status,
    emit_tool_start_events,
    classify_and_render_error,
)
from app.infra.model_manager import model_manager

router = APIRouter()


@router.post("/agent/chat")
@router.post("/ins-fqz/agent/chat")
async def chat(request: Request, background_tasks: BackgroundTasks):
    """
    流式对话接口。强化了企业级安全过滤器：
    1. 彻底拦截所有 <thought> 标签变体。
    2. 对物理表名进行脱敏。
    3. 支持会话自动寻回。
    """
    message, model_id, session_id = await parse_chat_request(request)
    
    logger.info(f"收到请求 [Session: {session_id}][Model: {model_id}]: {message}")

    # 获取对应的图执行器，并传入持久化器
    saver = request.app.state.saver
    executor, resolved_id = get_graph_executor(checkpointer=saver, model_id=model_id)
    
    # 显式记录最终用于推演的物理算力标识
    logger.info(f">>> [算力调配] 正在激活物理模型节点: {resolved_id}")

    # 加载持久化历史记录 (禁用自动恢复，确保推演上下文纯净)
    chat_history = history_manager.get_history(session_id, auto_recover=False)

    async def stream_generator() -> AsyncGenerator[str, None]:
        # 物理协议首帧：下发引擎元数据标记（[[[ENGINE:id]]]）
        # 新增 VERSION 标签支持 A/B Test 全局渲染
        yield f"[[[ENGINE:{resolved_id}]]]"
        yield f"[[[VERSION:{resolved_id}]]]"

        in_thought = False
        full_buffer = "" 
        last_yield_idx = 0
        ai_response_content = "" # 用于保存最终回复
        active_node = "init"
        interceptor = ProtocolInterceptor()
        session_internal_thoughts = [] # [V18.1] 初始化会话影子推演缓存
        
        # [V15.1 持久化计数器] 用于推演期间的心跳脉冲
        discard_counter = 0
        
        try:
            # [V4.5.3] 协议原子性：确保引擎 ID 永远作为流的首包发送
            # yield f"[[[ENGINE:{active_node}]]]" # [Removed V4.5.7] 避免覆盖初始物理算力标识
            
            # 使用 session_id 作为 thread_id 实现状态持久化
            # [V4.2.1] 提高递归限制：稽核链路较长，将默认的 25 步提升至 100 步
            config = {
                "configurable": {"thread_id": session_id},
                "recursion_limit": 100
            }
            # [V62.1] 状态寻回与指令中继：检测 Thread 是否处于挂起态 (如 HUMAN_REVIEW)
            thread_snapshot = await executor.aget_state(config)
            is_resuming = bool(thread_snapshot.next)
            
            inputs = {
                "messages": [HumanMessage(content=message)],
                "model_id": resolved_id,
                "session_id": session_id,
                "retry_count": 0,
                "step_counter": 0,
                "human_input": message if is_resuming else None # 如果是恢复执行，则将当前消息视为业务指令
            }
            
            if is_resuming:
                 logger.warning(f">>> [状态中继] 会话 {session_id} 正在从挂起点 {thread_snapshot.next} 恢复执行...")

            # [V4.9.8] 观测链注入：合并 Langfuse 等全局 Callbacks
            config["callbacks"] = get_callbacks()
            
            # [V5.0.0] TokenBudgetGuard：如果今日已烧掉 5M+ tokens，强制发出警报
            model_usage = usage_tracker.stats.daily_usage.get(resolved_id, 0)
            if model_usage > 5_000_000:
                logger.warning(f"!!! [高额开支警报] 节点 {resolved_id} 今日已烧过千万级 Token ({model_usage})，强制进入极端省流模式。")
                yield "\n> [!WARNING]\n> **高成本开支预警**: 您的会话已产生异常高额消耗。系统已自动开启\u201c深度脱水\u201d归档模式以节省费用。"
            
            # [V5.0.0] 重要变更：不再在此处进行物理修剪，改为让 Graph 内置的 MEMORY_COMPRESSOR 节点
            # 在每一轮循环中自动执行" snapshot 归档"和"数据蒸发"，从而实现真正意义上的阅后即焚。
            
            # [V16.0] 协议体系统升级：使用 version="v2" 提升嵌套事件穿透力
            async for event in executor.astream_events(inputs, config, version="v2"):
                kind = event["event"]
                name = str(event.get("name", ""))
                metadata = event.get("metadata", {})
                lg_node = metadata.get("langgraph_node", "")
                
                # [V15.3 调试并网] 在终端实时打印底层事件流
                if kind in ["on_chain_start", "on_chat_model_start"]:
                    logger.debug(f">>> [STREAM] kind={kind} | name={name} | lg_node={lg_node}")
                
                if kind == "on_chat_model_stream":
                    content = event["data"]["chunk"].content
                    if not content: continue
                    
                    # [V15.0 核心拦截] 只有 REPORTER 节点的输出才允许流向前端
                    if active_node != "reporter":
                        # [V15.1 智能心跳] 如果正在推演，每隔 40 个 token 喂一个点，防止死机错觉
                        discard_counter += 1
                        if discard_counter >= 40:
                            yield "."
                            discard_counter = 0
                        continue
                    
                    # 关键增强：过滤并提取有效文本，移除 JSON/思维链 结构
                    text_to_append = ""
                    if isinstance(content, str):
                        text_to_append = content
                    elif isinstance(content, list):
                        # 处理结构化内容：提取文本与思维链，实现透明化推演
                        for item in content:
                            if not isinstance(item, dict): continue
                            
                            i_type = item.get("type", "")
                            if i_type == "text":
                                text_to_append += item.get("text", "")
                            elif i_type in ["thought", "reasoning", "thinking"]:
                                # 思维片段：即便非交付阶段，也实时下发以降低用户焦虑
                                thought_chunk = item.get("thought") or item.get("reasoning") or item.get("text", "")
                                if thought_chunk:
                                    yield f"[[[THOUGHT:{sanitize(thought_chunk)}]]]\n\n"
                    elif isinstance(content, dict):
                        if content.get("type") == "text":
                            text_to_append = content.get("text", "")
                    
                    # [V4.6.1] 拦截器 + 强制脱敏双重过滤
                    interceptor_chunks = interceptor.process_chunk(text_to_append)
                    for chunk in interceptor_chunks:
                        if chunk:
                            filtered_content = sanitize(chunk)
                            if filtered_content:
                                # [V15.7] 场景化分流：根据活跃节点识别"交付阶段"与"推演阶段"
                                # 只有 REPORTER 的输出被视为最终用户可见并落库
                                if active_node == "REPORTER":
                                    full_buffer += filtered_content
                                    ai_response_content += filtered_content # 只有交付节点内容计入持久化
                                    yield filtered_content
                                else:
                                    # 专家的推演过程以 THOUGHT 标签实时下发给 UI 展示，但不计入 ai_response_content (不落库)
                                    yield f"[[[THOUGHT:{filtered_content}]]]\n\n"
                
                elif kind == "on_chain_start":
                    # [V15.3 强固检测] 优先使用 metadata 中的节点名称，其次使用 chain name
                    check_name = (lg_node or name).upper()
                    # [重构 V90.0] 节点切换的协议包生成委托给 emit_node_status
                    if check_name in ("DATA_EXPERT", "AUDITOR", "FINANCIAL_EXPERT", "REPORTER", "SOLO_EXPERT"):
                        active_node = "REPORTER" if check_name == "REPORTER" else "EXPERT"
                        for packet in emit_node_status(check_name, name):
                            yield packet

                elif kind == "on_tool_start":
                    name = event['name']
                    inputs = event['data']['input'] or {}
                    logger.info(f"审计工具执行: {name} -> {inputs}")
                    # [重构 V90.0] 工具启动协议包委托给 emit_tool_start_events
                    for packet in emit_tool_start_events(name, inputs):
                        yield packet

                elif kind == "on_tool_end":
                    name = event['name']
                    output = event['data'].get('output', '')
                    # [V23.1] 取证公示：将工具执行结果实时推送到 UI
                    if name in ["execute_audit_sql", "search_expert_knowledge", "list_tables"]:
                        summary = str(output)[:200].replace('\n', ' ')
                        yield f"[[[LOGIC: [取证回显] {name} 产出 -> {summary}...]]]\n\n"

                elif kind == "on_chat_model_end":
                    # 算力资源遥测与最终交付补益
                    data = event.get('data', {}) or {}
                    output = data.get('output')
                    
                    # [V15.9.4] 交付兜底：如果交付阶段结束但内容不足 50 字符，强制从 Final Output 中拉取全文
                    if active_node == "REPORTER" and output and len(ai_response_content) < 50:
                        final_text = getattr(output, "content", "")
                        if final_text and len(str(final_text)) > len(ai_response_content):
                             # 提取并清理
                             patch_content = sanitize(str(final_text))
                             # 只 yield 尚未被流式发送的部分 (简单起见，如果落后太多直接全文覆盖或拼接)
                             # 此处逻辑主要用于防止彻底的"空包"
                             ai_response_content = patch_content
                             yield patch_content
                    
                    usage = getattr(output, 'usage_metadata', {}) if output else {}
                    if usage:
                        prompt_tokens = usage.get('prompt_tokens', 0)
                        completion_tokens = usage.get('completion_tokens', 0)
                        
                        # [V35.0] 增强资源遥测：包含角色与成本估算
                        # 假设成本 (1k tokens): input=0.01元, output=0.03元 (综合均价)
                        input_cost = (prompt_tokens / 1000) * 0.01
                        output_cost = (completion_tokens / 1000) * 0.03
                        total_cost = input_cost + output_cost
                        
                        yield f"[[[RESOURCE:{{'role': '{lg_node or name}', 'prompt': {prompt_tokens}, 'completion': {completion_tokens}, 'cost': {total_cost:.4f}}}]]]"

                elif kind == "on_chain_end":
                    # [V18.1] 捕获影子推演链路：拦截节点返回的 internal_steps 并存入调试列表
                    data = event.get('data', {}) or {}
                    output = data.get('output', {}) or {}
                    if isinstance(output, dict) and 'internal_steps' in output:
                        steps = output['internal_steps']
                        if isinstance(steps, list):
                            session_internal_thoughts.extend([str(s) for s in steps])
                    
                    # [V39.7 物理回显穿透] 针对非 LLM 生成的静态报告（如诊断书）进行强制采集
                    if lg_node == "REPORTER":
                        if isinstance(output, dict) and "messages" in output:
                            last_msg = output["messages"][-1]
                            if hasattr(last_msg, "content") and len(ai_response_content) < 50:
                                static_content = sanitize(str(last_msg.content))
                                if static_content:
                                    ai_response_content = static_content
                                    yield static_content

            # [V61.0] 挂起探测：检测 Graph 是否在中断点暂停 (如 HUMAN_REVIEW)
            snapshot = await executor.aget_state(config)
            if snapshot.next:
                logger.warning(f">>> [状态预警] 会话 {session_id} 处于挂起状态: {snapshot.next}")
                
                help_msg = ""
                if snapshot.values and snapshot.values.get("error_log"):
                    error_log = str(snapshot.values["error_log"])
                    if error_log.startswith("MODEL_REQUEST_HELP:"):
                        help_msg = error_log.replace("MODEL_REQUEST_HELP:", "").strip()
                
                # 如果没有正常回复输出，则强制下发中断卡片
                if not ai_response_content:
                    signal_header = f"[[[STATUS: 审计链路已挂起，正在等待人工业务指导...]]]\n\n"
                    yield signal_header
                    ai_response_content += signal_header
                    
                    if help_msg:
                        help_body = f"### \U0001f6a9 专家业务校准请求\n\nAgent 在执行审计取证时遇到关键疑虑：\n\n> {help_msg}\n\n---\n**\U0001f4a1 下一步指引**：\n请根据上述疑虑，直接在对话框中输入您的决策建议（如：\u201c请按XX口径继续查询\u201d或\u201c忽略此项\u201d），系统将自动恢复审计链路。"
                        yield help_body
                        ai_response_content += help_body
                    else:
                        placeholder = "\n\n> [!IMPORTANT]\n> **审计链路中断**: 模型由于逻辑过于复杂请求人工接管。请在下方输入您的业务指导意见。"
                        yield placeholder
                        ai_response_content += placeholder

            # 最终物理清罐：由拦截器统一完成最后文本的释放
            final = interceptor.flush()
            if final:
                cleaned = sanitize(final)
                if cleaned:
                    ai_response_content += cleaned
                    yield cleaned
            
            # 对话结束后，异步保存至持久化层
            history_manager.save_turn(session_id, message, ai_response_content)
            
            # [V18.1] 深度转储：将全量对话历史与影子思维链共同持久化
            try:
                full_history = history_manager.get_history(session_id)
                history_manager.dump_debug_history(session_id, full_history, session_internal_thoughts)
            except Exception as e:
                logger.error(f"调试转储失败: {e}")
                
            # [V15.3] 将最终内容推送到终端，方便非 UI 环境验证
            print("\n" + "="*50)
            print(f"审计会话 [ {session_id} ] 最终输出结果:")
            print("-" * 50)
            print(ai_response_content if ai_response_content else "[警告: 无内容输出，可能被拦截器过滤或节点未匹配]")
            print("="*50 + "\n")
            
        except Exception as e:
            err_msg = str(e)
            logger.error(f"Agent Engine Error: {err_msg}")
            
            # [V4.9.15] 架构级容灾：将异常反馈给稳定性注册表
            _rid = resolved_id if 'resolved_id' in locals() else None
            if _rid:
                usage_tracker.record_failure(_rid, err_msg)
            
            # [重构 V90.0] 错误分类 + 自愈文案已提取到 classify_and_render_error
            # 该函数处理: Token 耗尽透传 / 403 配额熔断 / Model not found / 兜底
            # 以及黑名单和后台健康检查的副作用
            err_packets = classify_and_render_error(
                err_msg=err_msg,
                resolved_id=_rid,
                usage_tracker=usage_tracker,
                model_manager=model_manager,
                background_tasks=background_tasks,
            )
            for pkt in err_packets:
                yield pkt
                # Model not found / 兜底错误需要计入 ai_response_content
                if pkt.startswith("\n[算力链路异常]") or pkt.startswith("\n[核心审计异常]"):
                    ai_response_content += pkt

            # 异常时也要保存历史，否则会导致对话树不对齐
            history_manager.save_turn(session_id, message, ai_response_content)

    return StreamingResponse(
        stream_generator(), 
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )
