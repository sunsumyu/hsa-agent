import os
import json
import asyncio
import re
from typing import AsyncGenerator, List
from loguru import logger
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from app.agent_graph import get_graph_executor
from langchain_core.messages import HumanMessage
from app.model_manager import model_manager
from app.history import history_manager

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
        yield

app = FastAPI(title="HSA AI Agent (Python Edition)", lifespan=lifespan)

# 允许跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
                # 标签搜集完成，物理吞噬，清空 buffer
                # 注意：此处可以扩展对已知系统标签的解析逻辑 (如 SQL, LOGIC)
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
            if len(self.buffer) > 3:
                safe_len = len(self.buffer) - 3
                results.append(self.buffer[:safe_len])
                self.buffer = self.buffer[safe_len:]
                
        return results

    def flush(self) -> str:
        """最后时刻强制清出 buffer 中的剩余普通文本"""
        if not self.is_inside_tag:
            res = self.buffer
            self.buffer = ""
            return res
        return ""

def sanitize(text: str) -> str:
    """[V4.6.1] 深度审计盾：物理级数据脱敏与技术底噪拦截"""
    if not text: return ""
    
    # 1. 深度脱敏：屏蔽所有物理表名 (fqz_, t_audit_, clickhouse_等前缀)
    # 增加对 fqz 相关各种变体的覆盖
    patterns_to_mask = [r'fqz_[a-zA-Z0-9_]+', r't_audit_[a-zA-Z0-9_]+', r'medins_[a-zA-Z0-9_]+']
    for p in patterns_to_mask:
        text = re.sub(p, '【业务稽核表数据】', text, flags=re.IGNORECASE)
        
    # 2. 核心字段屏蔽：屏蔽 medfee_sumamt, psn_no 等技术标识符，保持业务感
    technical_fields = [
        r'\b[a-z]{2,}_[a-z_]{2,}\b', # 常见的下划线连接代码字段
        r'\bpsn_(no|id|name)\b', 
        r'\binsutype\b',
        r'\bsetl_id\b'
    ]
    for p in technical_fields:
        text = re.sub(p, '[关键审计维度]', text, flags=re.IGNORECASE)
        
    # 3. 拦截 SQL/JSON/思维链 残留
    text = re.sub(r'\b(SELECT|FROM|WHERE|INSERT|UPDATE|DELETE|JOIN|GROUP BY|ORDER BY|LIMIT|OFFSET)\b', '[核验逻辑]', text, flags=re.IGNORECASE)
    text = re.sub(r'\{.*?:.*?\}', '{结构化条目}', text, flags=re.DOTALL) # 拦截可能的 JSON 泄露
    
    # 4. 后线防御：清理所有未被拦截器捕获的标签以及模型生成的思维片段 (Thinking leaks)
    leak_patterns = [
        r'\[\[\[.*?\]\]\]', 
        r'⟦.*?⟧', 
        r'<thought>.*?</thought>', 
        r'\[thought\].*?\[/thought\]',
        r'(?i)Wait,.*?\.', # 拦截模型“OS自言自语”式的思维泄露
        r'(?i)I should.*?\.', # 拦截模型产生的技术决策碎碎念
        r'(?i)Tables are.*?\.'
    ]
    for p in leak_patterns:
        text = re.sub(p, '', text, flags=re.DOTALL | re.IGNORECASE)
        
    return text.strip()

@app.get("/agent/models")
@app.get("/ins-fqz/agent/models")
async def get_models():
    """获取可用模型列表"""
    return model_manager.get_model_list()

@app.get("/agent/history")
@app.get("/ins-fqz/agent/history")
async def get_history(request: Request):
    """获取指定会话的历史记录"""
    session_id = request.headers.get("X-Session-Id", "default-python-session")
    history = history_manager.get_history(session_id)
    # 转换为前端易读的简单格式
    return [
        {"role": "user" if msg.type == "human" else "ai", "content": msg.content}
        for msg in history
    ]

@app.post("/agent/chat")
@app.post("/ins-fqz/agent/chat")
async def chat(request: Request):
    """
    流式对话接口。强化了企业级安全过滤器：
    1. 彻底拦截所有 <thought> 标签变体。
    2. 对物理表名进行脱敏。
    """
    body = await request.body()
    try:
        # 尝试解析为 JSON 并提取 input 字段，兼容 Java 侧的 Payload
        data = json.loads(body.decode("utf-8"))
        message = data.get("input", str(data))
        model_id = data.get("modelId") # 获取前端指定的模型 ID
    except Exception:
        # 回退到原始文本模式
        message = body.decode("utf-8")
        model_id = None
        
    session_id = request.headers.get("X-Session-Id", "default-python-session")
    logger.info(f"收到请求 [Session: {session_id}][Model: {model_id}]: {message}")

    # 获取对应的图执行器，并传入持久化器
    executor, resolved_id = get_graph_executor(checkpointer=app.state.saver, model_id=model_id)
    
    # 显式记录最终用于推演的物理算力标识
    logger.info(f">>> [算力调配] 正在激活物理模型节点: {resolved_id}")

    # 加载持久化历史记录
    chat_history = history_manager.get_history(session_id)

    async def stream_generator() -> AsyncGenerator[str, None]:
        # 物理协议首帧：下发引擎元数据标记（[[[ENGINE:id]]]）
        # 新增 VERSION 标签支持 A/B Test 全局渲染
        yield f"[[[ENGINE:{resolved_id}]]]"
        yield f"[[[VERSION:{resolved_id}]]]"

        in_thought = False
        full_buffer = "" 
        last_yield_idx = 0
        ai_response_content = "" # 用于保存最终回复
        
        interceptor = ProtocolInterceptor()

        active_node = "init"
        try:
            # [V4.5.3] 协议原子性：确保引擎 ID 永远作为流的首包发送
            # yield f"[[[ENGINE:{active_node}]]]" # [Removed V4.5.7] 避免覆盖初始物理算力标识
            
            # 使用 session_id 作为 thread_id 实现状态持久化
            # [V4.2.1] 提高递归限制：稽核链路较长，将默认的 25 步提升至 100 步
            config = {
                "configurable": {"thread_id": session_id},
                "recursion_limit": 100
            }
            # [Critical Fix] 修复历史记录重复叠加导致的上下文爆炸 Bug
            # 由于使用了 checkpointer (AsyncSqliteSaver)，状态中已经包含了消息历史。
            # 这里只需发送当前最新的一条 HumanMessage，LangGraph 会自动通过 operator.add 合并。
            inputs = {
                "messages": [HumanMessage(content=message)],
                "model_id": resolved_id
            }

            async for event in executor.astream_events(inputs, config, version="v1"):
                kind = event["event"]
                if kind == "on_chat_model_stream":
                    content = event["data"]["chunk"].content
                    if not content: continue
                    
                    # 关键增强：过滤并提取有效文本，移除 JSON/思维链 结构
                    text_to_append = ""
                    if isinstance(content, str):
                        text_to_append = content
                    elif isinstance(content, list):
                        # 处理结构化内容：只提取 type='text' 的部分，忽略 thinking 部分
                        for item in content:
                            if isinstance(item, dict) and item.get("type") == "text":
                                text_to_append += item.get("text", "")
                    elif isinstance(content, dict):
                        if content.get("type") == "text":
                            text_to_append = content.get("text", "")
                    
                    # [V4.6.1] 拦截器 + 强制脱敏双重过滤
                    interceptor_chunks = interceptor.process_chunk(text_to_append)
                    for chunk in interceptor_chunks:
                        if chunk:
                            cleaned_chunk = sanitize(chunk)
                            if cleaned_chunk:
                                ai_response_content += cleaned_chunk
                                yield cleaned_chunk
                
                elif kind == "on_chain_start":
                    name = event.get("name")
                    # 监听专家节点切换，发送 3D 状态包 (不再重复读取 DB 以防死锁)
                    if name in ["data_expert", "auditor", "financial_expert", "reporter"]:
                        active_node = name
                        display_name = {
                            "data_expert": "数据外联专家",
                            "auditor": "政策合规专家",
                            "financial_expert": "精算核算专家",
                            "reporter": "稽核报告终审"
                        }.get(name, name)
                        
                        yield f"[[[STATUS:正在激活 [{display_name}] 进行推演...]]]"
                        # 触发初始空间移动 — 键名与前端 ARCHIVE_WORLD 严格一致
                        if name == "data_expert": 
                            yield "[[[MOVE:default.fqz_all_yy_yd_1]]]"
                            yield "[[[SCHEMA:default.fqz_all_yy_yd_1:fixmedins_code,medfee_sumamt,setl_time,psn_no]]]"
                        elif name == "auditor": 
                            yield "[[[MOVE:hsa_policy_kb]]]"
                            yield "[[[SCHEMA:hsa_policy_kb:rule_id,rule_name,legal_basis,risk_weight]]]"
                        elif name == "financial_expert": 
                            yield "[[[MOVE:t_audit_task]]]"
                            yield "[[[SCHEMA:t_audit_task:task_id,status,target_hosp_id,audit_amount]]]"

                elif kind == "on_tool_start":
                    name = event['name']
                    inputs = event['data']['input']
                    logger.info(f"审计工具执行: {name} -> {inputs}")
                    
                    # 联动 3D：精确空间指令
                    if name in ["execute_audit_sql", "get_table_schema"]:
                        db = inputs.get("db_type", "clickhouse")
                        table = inputs.get("table_name", "archives")
                        if table == "archives": table = "fqz_all_yy_yd_1"
                        
                        # 统一为前端 ARCHIVE_WORLD 键名
                        world_key = f"default.{table}" if db == "clickhouse" else table
                        yield f"[[[MOVE:{world_key}]]]"
                        yield f"[[[LOGIC:正在执行交叉核验 -> 检索键: {inputs.get('sql', 'Metadata Fetch')[:50]}...]]]"
                        if "sql" in inputs:
                            sql_val = inputs['sql']
                            yield f"[[[SQL:{sql_val}]]]"
                            # 新增: 精确书架命中协议 — 从 SQL 中提取 SELECT 字段
                            try:
                                col_match = re.search(r'SELECT\s+(.+?)\s+FROM', sql_val, re.IGNORECASE)
                                if col_match:
                                    raw_cols = col_match.group(1).strip()
                                    if raw_cols != '*':
                                        cols = [c.strip().split('.')[-1].split(' ')[0] for c in raw_cols.split(',')]
                                        yield f"[[[BOOKSHELF:{world_key}:{','.join(cols)}]]]"
                                    else:
                                        yield f"[[[BOOKSHELF:{world_key}:*]]]"
                            except Exception:
                                pass
                    elif name == "search_expert_knowledge":
                        yield "[[[MOVE:hsa_policy_kb]]]"
                        yield "[[[THOUGHT:正在检索核心政策库以比对违规特征...]]]"
                        yield "[[[LOGIC:输入诊断特征 -> 搜索高风险规则集...]]]"
                        query_text = inputs.get('query', '')[:40]
                        yield f"[[[BOOKSHELF:hsa_policy_kb:rule_name,legal_basis]]]"
                    elif name == "calculator":
                        yield "[[[MOVE:logic_core]]]"
                        yield "[[[THOUGHT:正在启动确证计算引擎，进行高精度金额核算...]]]"
                        yield "[[[LOGIC:输入数值对 -> 精算确认违规金额总计...]]]"

                elif kind == "on_chat_model_end":
                    # 算力资源遥测：提取 Token 消耗
                    usage = event['data'].get('output', {}).get('usage_metadata', {})
                    if usage:
                        prompt_tokens = usage.get('prompt_tokens', 0)
                        completion_tokens = usage.get('completion_tokens', 0)
                        total_tokens = usage.get('total_tokens', 0)
                        # 发送资源遥测协议包 (用于 HUD 渲染)
                        yield f"[[[RESOURCE:{{'model': '{active_node}', 'prompt': {prompt_tokens}, 'completion': {completion_tokens}, 'total': {total_tokens}}}]]]"
                    
            # 最终物理清罐：由拦截器统一完成最后文本的释放
            final = interceptor.flush()
            if final:
                cleaned = sanitize(final)
                if cleaned:
                    ai_response_content += cleaned
                    yield cleaned
            
            # 对话结束后，异步保存至持久化层
            history_manager.save_turn(session_id, message, ai_response_content)
                
        except Exception as e:
            err_msg = str(e)
            logger.error(f"Agent Engine Error: {err_msg}")
            
            # 1. 协议透传：如果是 Token 耗尽导致的结构化建议，必须原样透传
            if "[[[OUT_OF_TOKEN" in err_msg:
                yield f"\n{err_msg}"
            # 2. 对 403 和 权限类错误进行业务化处理
            elif "403" in err_msg or "Forbidden" in err_msg:
                yield "\n[审计权限异常]: 当前模型账号权限不足或额度已耗尽 (403)。系统已自动尝试算力寻回，请刷新页面重新发起。"
            elif "Model not found" in err_msg:
                err_str = f"\n[算力链路异常]: 找不到模型标识符。请检查 llm_providers.json 配置。"
                yield err_str
                ai_response_content += err_str
            else:
                err_str = f"\n[核心审计异常]: 处理中断。详细信息: {err_msg[:50]}..."
                yield err_str
                ai_response_content += err_str
                
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=18082)
