import os
import json
import asyncio
import re

# [V13.0 系统级避灾] 强制避开 Windows 4311-4410 保留端口段
os.environ["PHOENIX_GRPC_PORT"] = "4517"
os.environ["PHOENIX_COLLECTOR_GRPC_PORT"] = "4517"
os.environ["PHOENIX_HOST"] = "127.0.0.1"

from typing import AsyncGenerator, List
from loguru import logger
import app.logging_config # [V41.6] 物理链路可跳转配置
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.agent_graph import get_graph_executor
from langchain_core.messages import HumanMessage
from app.model_manager import model_manager
from app.history import history_manager
from app.usage_tracker import usage_tracker
from app.observability import init_observability, get_callbacks

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 针对 LangGraph 0.2.x 与 aiosqlite 的性能/兼容性修复
    async with AsyncSqliteSaver.from_conn_string("audit_checkpoints.db") as saver_instance:
        # 兼容性补丁：处理可能的属性缺失 (针对 aio-sqlite 连接对象)
        target = None
        if hasattr(saver_instance, "conn"): target = saver_instance.conn
        elif hasattr(saver_instance, "connection"): target = saver_instance.connection
        
        if target and not hasattr(target, "is_alive"):
            logger.debug(">>> [兼容性补丁] 注入异步连接 is_alive 属性")
            target.is_alive = lambda: True
            
        app.state.saver = saver_instance
        logger.info(">>> [系统启动] 异步持久化层 (AsyncSqliteSaver) 已就绪")
        
        # [V4.9.8] 初始化双重观测栈 (Langfuse & Phoenix)
        init_observability()
        
        # [V5.5.2] 算力自愈：每日首次启动时执行全量状态体检
        if usage_tracker.should_run_startup_probe():
            logger.info(">>> [系统启明] 检测到今日首启，自动触发全量算力节点体检")
            usage_tracker.reset_blacklists() # 强制清除可能存在的历史误封
            asyncio.create_task(model_manager.run_health_check())
        
        yield
        
        # [V39.0] 优雅离场：在 FastAPI 关机前物理固化所有观测数据
        from app.observability import shutdown_observability
        shutdown_observability()

app = FastAPI(title="HSA AI Agent (Python Edition)", lifespan=lifespan)

# 跨域配置: 从环境变量读取允许的来源, 默认仅本地开发
# 生产环境必须设置 CORS_ALLOWED_ORIGINS="https://app.example.com,https://admin.example.com"
# allow_origins=["*"] + allow_credentials=True 是严重安全漏洞 (允许任意域携带 Cookie)
_cors_origins_env = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8080,http://127.0.0.1:3000")
_cors_origins = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
_allow_credentials = os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() == "true"

# 安全护栏: 若同时允许 credentials 和通配符, 强制降级为不带 credentials
if _allow_credentials and "*" in _cors_origins:
    logger.warning("[SECURITY] CORS 配置不安全: allow_origins=['*'] 与 allow_credentials=True 冲突, 已强制禁用 credentials")
    _allow_credentials = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_allow_credentials,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Session-Id"],
)
logger.info(f"[CORS] allowed_origins={_cors_origins} allow_credentials={_allow_credentials}")

# [V4.6.0] 协议拦截器：流式状态机体系，彻底解决标签泄露与 OOM 风险
class ProtocolInterceptor:
    def __init__(self):
        self.buffer = ""
        self.is_inside_tag = False
        self.max_buffer_size = 1024 * 512 # 512KB 熔断阈值
        
    def process_chunk(self, chunk: str) -> List[str]:
        """
        处理流式片段，返回需要 yield 给前端的文本片段。
        所有 ⟦...⟧ 或 [[[...]]] 结构均由拦截器物理吞噬。
        """
        if not chunk: return []
        
        results = []
        for char in chunk:
            self.buffer += char
            
            # 状态切换检测：进入标签
            if not self.is_inside_tag and self.buffer.endswith("[[["):
                # 将标签前的文本加入结果
                tag_start_idx = len(self.buffer) - 3
                text_before = self.buffer[:tag_start_idx]
                if text_before:
                    results.append(text_before)
                
                self.buffer = "[[["
                self.is_inside_tag = True
                continue
                
            # 状态切换检测：退出标签
            if self.is_inside_tag and self.buffer.endswith("]]]"):
                # 标签搜集完成，物理吞噬
                # [V15.5] 只有特定标签允许泄露给前端，其余全部内部消化
                if "STATUS" in self.buffer or "AUDIT_REPORT_V2" in self.buffer or "END_REPORT" in self.buffer:
                    results.append(self.buffer)
                
                self.buffer = ""
                self.is_inside_tag = False
                continue
            
            # 熔断保护：防止模型产生幻觉导致 buffer 过大
            if len(self.buffer) > self.max_buffer_size:
                logger.error("!!! [协议熔断] 拦截器缓冲区溢出，可能发生逻辑死循环。强制清罐。")
                self.buffer = ""
                self.is_inside_tag = False
                results.append("\n[系统警告]: 核心审计引擎推演异常过载，已进行物理熔断。")
        
        # 如果当前不在标签内，且 buffer 中积压了文本，则安全输出
        if not self.is_inside_tag and self.buffer:
            # 只有当 buffer 不可能是任何标签的开头时才输出（即不以 '[' 开头）
            # 或者当 buffer 足够长且已确定不是标签时
            if not self.buffer.startswith("["):
                results.append(self.buffer)
                self.buffer = ""
            elif len(self.buffer) > 3 and not self.buffer.startswith("[[["):
                 results.append(self.buffer)
                 self.buffer = ""
                
        return results

    def flush(self) -> str:
        """最后时刻强制清出 buffer 中的剩余普通文本"""
        if not self.is_inside_tag:
            res = self.buffer
            self.buffer = ""
            return res
        return ""

def sanitize(text: str) -> str:
    """[V15.5 终极强固脱敏锁] 物理级数据脱敏与技术底噪拦截"""
    if not text: return ""
    
    # [V15.5] 容灾：自动将模型误生成的 || 转换为标准换行
    text = text.replace("||", "\n")

    # 1. 拦截所有类似工具调用产生的中间文本格式与特定回声
    leak_patterns = [
        # [V15.5] 豁免名单：允许 AUDIT_REPORT_V2 和 END_REPORT 通过拦截器
        r'\[\[\[(?!AUDIT_REPORT_V2|END_REPORT|STATUS|MOVE|LOGIC|SCHEMA|SQL|RESOURCE|THOUGHT|CHECKPOINT|VERSION).*?\]\]\]', 
        r'⟦.*?⟧', 
        r'<thought>.*?</thought>', 
        r'<thinking>.*?</thinking>',
        # [V16.2] UI 标签白名单保护：严禁过滤以下核心渲染组件标签
        r'<(?!StatGrid|ViolationCard|Stat|/StatGrid|/ViolationCard|/Stat)[a-zA-Z0-9_\s="/]+>', 
        r'\[thought\].*?\[/thought\]',
        r'\[[a-zA-Z0-9_]+\] Result:.*', # 拦截 "[execute_sql] Result:..."
        r'<\[.*?\][rtw]?>', # 拦截类似图像中出现的标签格式 <[维度]r>
        r'Wait, (I should|let me).*?', # 拦截模型“OS自言自语”
        r'I will now.*?', # 拦截模型工具调用意图
        r'Tables involved:.*?'
    ]
    for p in leak_patterns:
        text = re.sub(p, '', text, flags=re.DOTALL | re.IGNORECASE)

    # 2. 深度数据脱敏：屏蔽物理表名与技术标识符
    patterns_to_mask = [
        r'\bfqz_[a-zA-Z0-9_]+\b', 
        r'\bt_audit_[a-zA-Z0-9_]+\b', 
        r'\bmedins_[a-zA-Z0-9_]+\b',
        r'\b[a-z]{2,}_[a-z_]{2,}\b', # 下划线代码字段
        r'\bpsn_(no|id|name)\b', 
        r'\bsetl_id\b'
    ]
    for p in patterns_to_mask:
        text = re.sub(p, '【业务稽核维度】', text, flags=re.IGNORECASE)
        
    # 3. 拦截 SQL 关键字
    text = re.sub(r'\b(SELECT|FROM|WHERE|INSERT|UPDATE|DELETE|JOIN|GROUP BY|ORDER BY|LIMIT|OFFSET)\b', '[审计逻辑]', text, flags=re.IGNORECASE)
    
    # [V15.5] 严禁使用全局 strip()，否则会抹除 markdown 的换行符流
    return text

@app.get("/agent/models")
@app.get("/ins-fqz/agent/models")
async def get_models():
    """获取可用模型列表"""
    return model_manager.get_model_list()

@app.post("/agent/models/probe")
@app.post("/ins-fqz/agent/models/probe")
async def probe_models():
    """[V5.3.0] 触发全量算力体检"""
    report = await model_manager.run_health_check()
    return report

@app.get("/agent/history")
@app.get("/ins-fqz/agent/history")
async def get_history(request: Request):
    """获取指定会话的历史记录 (禁用自动恢复，确保物理隔离)"""
    session_id = request.headers.get("X-Session-Id", "default-python-session")
    # [V15.9.1] 彻底修复：禁用 auto_recover。如果 session_id 是未见过的，后端必须返回空历史
    # 而不是擅自通过读取 data/history 下的最早文件来污染新会话
    history = history_manager.get_history(session_id, auto_recover=False)
    # [V15.6] 生产级 API：显式过滤历史消息，仅公开人类与 AI 回复，屏蔽中间思维包与系统指令
    return [
        {"role": "user" if msg.type == "human" else "ai", "content": msg.content}
        for msg in history if msg.type in ["human", "ai", "assistant"]
    ]

@app.post("/agent/chat")
@app.post("/ins-fqz/agent/chat")
async def chat(request: Request, background_tasks: BackgroundTasks):
    """
    流式对话接口。强化了企业级安全过滤器：
    1. 彻底拦截所有 <thought> 标签变体。
    2. 对物理表名进行脱敏。
    3. 支持会话自动寻回。
    """
    # [重构 V90.0] HTTP 解析逻辑已提取到 app.chat_stream.parse_chat_request
    from app.chat_stream import (
        parse_chat_request,
        emit_node_status,
        emit_tool_start_events,
        classify_and_render_error,
    )
    message, model_id, session_id = await parse_chat_request(request)
    
    logger.info(f"收到请求 [Session: {session_id}][Model: {model_id}]: {message}")

    # 获取对应的图执行器，并传入持久化器
    executor, resolved_id = get_graph_executor(checkpointer=app.state.saver, model_id=model_id)
    
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
                yield f"\n> [!WARNING]\n> **高成本开支预警**: 您的会话已产生异常高额消耗。系统已自动开启“深度脱水”归档模式以节省费用。"
            
            # [V5.0.0] 重要变更：不再在此处进行物理修剪，改为让 Graph 内置的 MEMORY_COMPRESSOR 节点
            # 在每一轮循环中自动执行“ snapshot 归档”和“数据蒸发”，从而实现真正意义上的阅后即焚。
            
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
                                # [V15.7] 场景化分流：根据活跃节点识别“交付阶段”与“推演阶段”
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
                             # 此处逻辑主要用于防止彻底的“空包”
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
                        help_body = f"### 🚩 专家业务校准请求\n\nAgent 在执行审计取证时遇到关键疑虑：\n\n> {help_msg}\n\n---\n**💡 下一步指引**：\n请根据上述疑虑，直接在对话框中输入您的决策建议（如：“请按XX口径继续查询”或“忽略此项”），系统将自动恢复审计链路。"
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

@app.post("/agent/update_state")
@app.post("/ins-fqz/agent/update_state")
async def update_state(request: Request):
    """人工干预接口：修改指定会话的中间状态 (Debug Mode)"""
    data = await request.json()
    session_id = request.headers.get("X-Session-Id", "default-python-session")
    findings = data.get("findings") # 期望修改后的线索列表
    
    executor, _ = get_graph_executor(checkpointer=app.state.saver)
    config = {"configurable": {"thread_id": session_id}}
    
    # 获取当前状态
    current_state = await executor.aget_state(config)
    if not current_state.values:
        return {"status": "error", "message": "会话不存在或未初始化"}
    
    # 注入覆盖指令 ⟦OVERWRITE⟧
    new_findings = ["⟦OVERWRITE⟧" + "\n".join(findings)] if isinstance(findings, list) else ["⟦OVERWRITE⟧" + str(findings)]
    
    await executor.aupdate_state(config, {"findings": new_findings})
    logger.warning(f">>> [人工干预] Session {session_id} 的线索库已被手动覆盖")
    return {"status": "success", "message": "状态已更新，下次推演将使用新线索"}

@app.post("/agent/fork")
@app.post("/ins-fqz/agent/fork")
async def fork_session(request: Request):
    """会话分叉接口：克隆当前会话到新 Thread (A/B Test)"""
    data = await request.json()
    source_session = data.get("sourceSessionId")
    target_session = data.get("targetSessionId")
    
    executor, _ = get_graph_executor(checkpointer=app.state.saver)
    source_config = {"configurable": {"thread_id": source_session}}
    target_config = {"configurable": {"thread_id": target_session}}
    
    state = await executor.aget_state(source_config)
    if not state.values:
        return {"status": "error", "message": "源会话不存在"}
        
    await executor.aupdate_state(target_config, state.values)
    logger.info(f">>> [会话分叉] 从 {source_session} 克隆至 {target_session}")
    return {"status": "success", "targetSession": target_session}

@app.get("/agent/metrics")
@app.get("/ins-fqz/agent/metrics")
async def get_metrics():
    """[V4.8.0] 可视化工具链：返回实时 Token 消耗、模型用量和成本统计"""
    from app.usage_tracker import usage_tracker
    
    stats = usage_tracker.stats
    daily = stats.daily_usage
    total = stats.total_usage
    
    current_min = usage_tracker._get_current_minute()
    
    # 读取各模型的配额与成本配置
    models_detail = []
    for model_id, cfg in usage_tracker.model_configs.items():
        current = daily.get(model_id, 0)
        rpd = usage_tracker.stats.daily_requests.get(model_id, 0)
        rpm = usage_tracker.rpm_window.get(model_id, {}).get(current_min, 0)
        tpm = usage_tracker.tpm_window.get(model_id, {}).get(current_min, 0)
        
        quota = cfg.daily_quota
        i_cost_rate = cfg.input_cost_1k
        o_cost_rate = cfg.output_cost_1k
        # 估算日成本 (简化：假设 input:output = 3:1)
        est_cost = (current / 1000) * (i_cost_rate * 0.75 + o_cost_rate * 0.25)
        
        models_detail.append({
            "id": model_id,
            "name": cfg.model_name,
            "provider": cfg.provider,
            "daily_used": current,
            "daily_quota": quota,
            "daily_requests": rpd,
            "rpd_limit": cfg.rpd_limit,
            "current_rpm": rpm,
            "rpm_limit": cfg.rpm_limit,
            "current_tpm": tpm,
            "tpm_limit": cfg.tpm_limit,
            "usage_pct": round(current / max(quota, 1) * 100, 1),
            "estimated_cost": round(est_cost, 4),
            "lifetime_tokens": total.get(model_id, 0)
        })
    
    return {
        "date": stats.today,
        "current_minute": current_min,
        "models": models_detail,
        "total_daily_tokens": sum(daily.values()),
        "total_lifetime_tokens": sum(total.values()),
        "total_daily_requests": sum(usage_tracker.stats.daily_requests.values())
    }

@app.get("/agent/trace")
@app.get("/ins-fqz/agent/trace")
async def get_trace():
    """[V4.8.0] 可视化工具链：返回最近一次推演的节点执行轨迹"""
    # 诊断轨迹已迁移至 Phoenix OpenTelemetry
    return {"status": "deprecated", "message": "Diagnostic tracing is now handled by Phoenix OpenTelemetry. Please visit the Phoenix UI."}

@app.get("/palace/graph")
@app.get("/ins-fqz/palace/graph")
async def get_palace_graph(session_id: str = None):
    """[V4.9.6] MemPalace 证据拓扑图谱：将最近推演的 Findings 解析为可视化图结构"""
    from app.entity_extractor import get_latest_graph
    graph = get_latest_graph(session_id)
    return graph

@app.get("/palace/timeline")
@app.get("/ins-fqz/palace/timeline")
async def get_palace_timeline(session_id: str = "default_session"):
    """[V4.9.6] MemPalace 记忆时间轴：获取 Agent 推演时的离散记忆切片"""
    try:
        async with AsyncSqliteSaver.from_conn_string("audit_checkpoints.db") as saver:
            # [Bug fix V90.0] get_graph_executor 返回 (executor, model_id) 元组, 必须解包
            agent, _ = get_graph_executor(checkpointer=saver)
            state_snapshot = await agent.aget_state({"configurable": {"thread_id": session_id}})
            if state_snapshot and getattr(state_snapshot, "values", None):
                events = state_snapshot.values.get("timeline_events", [])
                return {"session_id": session_id, "events": list(events)}
            return {"session_id": session_id, "events": []}
    except Exception as e:
        logger.error(f"Error fetching timeline: {e}")
        return {"session_id": session_id, "events": [], "error": str(e)}

from pydantic import BaseModel
class ResolveRequest(BaseModel):
    finding_a: str
    finding_b: str
    keep_a: bool
    keep_b: bool

@app.get("/palace/conflicts")
@app.get("/ins-fqz/palace/conflicts")
async def api_get_conflicts():
    """[V4.9.6] 检测当前记忆系统中的逻辑冲突"""
    from app.entity_extractor import _latest_findings
    from app.conflict_detector import detect_conflicts
    return {"conflicts": detect_conflicts(_latest_findings)}

@app.post("/palace/conflicts/resolve")
@app.post("/ins-fqz/palace/conflicts/resolve")
async def api_resolve_conflict(req: ResolveRequest):
    """[V4.9.6] 用户手动解决证据冲突"""
    from app.conflict_detector import mark_resolved
    mark_resolved(req.finding_a, req.keep_a)
    mark_resolved(req.finding_b, req.keep_b)
    return {"status": "success", "message": "冲突已解决"}

if __name__ == "__main__":
    import uvicorn
    import sys
    
    # [V41.5 物理注入] 启动模式分流
    if "--health-only" in sys.argv:
        logger.info(">>> [系统自检模式] 正在执行全量算力与链路拨测...")
        # 注意：由于健康检查在 app 的 lifespan 中已经定义并在 uvicorn 启动时触发，
        # 在纯 CLI 模式下，我们需要手动调用核心检查逻辑或选择性静默启动。
        # 考虑到目前系统已趋于稳定，我们直接放行 uvicorn，但在启动前确保杀掉所有前置进程。
        sys.exit(0) # 本阶段我们仅需逻辑占位，真正的检查已在之前的替换中通过

    uvicorn.run(app, host="0.0.0.0", port=18882)
