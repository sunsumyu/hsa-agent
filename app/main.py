import os
import json
import asyncio
import re
from typing import AsyncGenerator
from loguru import logger
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from app.agent import get_executor
from app.model_manager import model_manager

app = FastAPI(title="HSA AI Agent (Python Edition)")

# 允许跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/agent/models")
@app.get("/ins-fqz/agent/models")
async def get_models():
    """获取可用模型列表"""
    return model_manager.get_model_list()

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

    # 获取对应的执行器（包含动态回退链）
    executor, resolved_id = get_executor(model_id=model_id)
    
    # 显式记录最终用于推演的物理算力标识
    logger.info(f">>> [算力调配] 正在激活物理模型节点: {resolved_id}")

    async def stream_generator() -> AsyncGenerator[str, None]:
        # 物理协议首帧：下发引擎元数据标记（⟦ENGINE:id⟧）
        # 前端会拦截该标记并更新 UI，而不会将其显示给用户
        yield f"⟦ENGINE:{resolved_id}⟧"

        in_thought = False
        full_buffer = "" 
        last_yield_idx = 0
        
        # 增强型脱敏过滤器：屏蔽表名、字段名、SQL关键字
        def sanitize(text: str) -> str:
            # 1. 屏蔽所有 fqz_ 开头的物理表名
            text = re.sub(r'fqz_[a-zA-Z0-9_]+', '业务数据', text, flags=re.IGNORECASE)
            # 2. 屏蔽常见字段名（下划线连接的英文标识符，如 medfee_sumamt, setl_time）
            text = re.sub(r'\b[a-z]{2,}_[a-z_]{2,}\b', '', text, flags=re.IGNORECASE)
            # 3. 屏蔽 SQL 语句片段
            text = re.sub(r'\b(SELECT|FROM|WHERE|INSERT|UPDATE|DELETE|JOIN|GROUP BY|ORDER BY|LIMIT)\b', '', text, flags=re.IGNORECASE)
            return text

        try:
            async for event in executor.astream_events(
                {"input": message, "chat_history": []}, 
                version="v1"
            ):
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
                    
                    if not text_to_append: continue
                    full_buffer += text_to_append
                    
                    while True:
                        remaining = full_buffer[last_yield_idx:]
                        if not in_thought:
                            # 模糊匹配思考链开始标签
                            start_match = re.search(r'(<|\[)\s*thought\s*(>|\])', remaining, re.IGNORECASE)
                            if start_match:
                                start_pos = last_yield_idx + start_match.start()
                                yield_content = sanitize(full_buffer[last_yield_idx:start_pos])
                                if yield_content: yield yield_content
                                in_thought = True
                                last_yield_idx = start_pos + len(start_match.group())
                                continue
                            else:
                                # 保持安全窗口 (32字节)，防止脱敏词或标签被切断而失效
                                if len(remaining) > 32:
                                    to_yield = remaining[:-32]
                                    yield sanitize(to_yield)
                                    last_yield_idx += len(to_yield)
                                break
                        else:
                            # 寻找思考链结束标签
                            end_match = re.search(r'(<|\[)\s*/\s*thought\s*(>|\])|thought\s*>', remaining, re.IGNORECASE)
                            if end_match:
                                end_pos = last_yield_idx + end_match.end()
                                in_thought = False
                                last_yield_idx = end_pos
                                continue
                            else:
                                break
                elif kind == "on_tool_start":
                    logger.info(f"审计工具执行: {event['name']} -> {event['data']['input']}")
                elif kind == "on_chat_model_end":
                    if not in_thought:
                        # 最终清罐，对末尾内容进行脱敏
                        final = sanitize(full_buffer[last_yield_idx:])
                        if final: yield final
        except Exception as e:
            logger.error(f"Agent Engine Error: {e}")
            yield f"\n[核心审计异常]: 处理中断，请联系管理人员。{str(e)[:30]}"

    return StreamingResponse(stream_generator(), media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=18082)
