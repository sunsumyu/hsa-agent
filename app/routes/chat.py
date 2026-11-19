"""
app/routes/chat.py
==================
核心流式对话与反馈路由，薄控制器 (Thin Controller) 设计。
保持 API 路径不变: /agent/chat, /ins-fqz/agent/chat, /agent/feedback, /ins-fqz/agent/feedback
遵循 Matt Pocock 设计哲学：
- 控制器极薄 (Thin Controller)：无复杂业务逻辑，纯做 DTO 校验与分发
- 核心流式循环委托至 ChatStreamCoordinator 深模块
- 反馈收集全权委托至 ObservabilityService 深模块
"""

from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from loguru import logger

from app.api.chat_stream import parse_chat_request
from app.api.chat_stream_coordinator import chat_stream_coordinator
from app.core.container import ServiceProvider

router = APIRouter()


class FeedbackDTO(BaseModel):
    """人工审计反馈数据传输对象"""
    run_id: str = Field(..., description="LangSmith Run ID")
    score: float = Field(..., ge=0.0, le=1.0, description="评分：1.0 满意/通过，0.0 纠错/差评")
    category: Optional[str] = Field(None, description="错误分类，如 SQL_ERROR, WRONG_AMOUNT, HALLUCINATION")
    comment: Optional[str] = Field(None, description="人工批注或校准答案")


@router.post("/agent/chat")
@router.post("/ins-fqz/agent/chat")
async def chat(request: Request, background_tasks: BackgroundTasks):
    """
    流式对话接口。强化了企业级安全过滤器：
    1. 彻底拦截所有 <thought> 标签变体。
    2. 对物理表名进行脱敏。
    3. 支持会话自动寻回与中继恢复。
    """
    message, model_id, session_id = await parse_chat_request(request)
    logger.info(f"收到请求 [Session: {session_id}][Model: {model_id}]: {message}")

    stream_gen = chat_stream_coordinator.coordinate_stream(
        request=request,
        background_tasks=background_tasks,
        session_id=session_id,
        model_id=model_id,
        message=message,
    )

    return StreamingResponse(
        stream_gen,
        media_type="text/plain",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.post("/agent/feedback")
@router.post("/ins-fqz/agent/feedback")
async def submit_feedback(dto: FeedbackDTO):
    """
    [薄控制器] 接收人工审计点赞/纠错反馈并回流至数据飞轮
    """
    logger.info(f"收到人工审计反馈 [RunID: {dto.run_id}][Score: {dto.score}]: {dto.category or 'N/A'}")
    obs = ServiceProvider.resolve("observability")
    success = obs.record_feedback(
        run_id=dto.run_id,
        score=dto.score,
        category=dto.category,
        comment=dto.comment,
    )
    return {"success": success, "run_id": dto.run_id}
