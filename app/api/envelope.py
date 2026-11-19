"""
app/api/envelope.py
===================
API 响应信封与统一异常处理器 (ResponseEnvelope & APIExceptionHandler)
遵循 Matt Pocock 与 Deep Module 原则：
- 浅接口，深实现：提供简单统一的响应信封封装 ResponseEnvelope.success / ResponseEnvelope.error
- 全局集中式异常拦截：自动捕获并规范化常见业务异常与未捕获异常：
  * ValueError -> 400 Bad Request
  * KeyError -> 404 Not Found
  * HTTPException -> 保持原有状态码与错误信息
  * 未捕获 Exception -> 记录结构化日志并返回统一 500 降级信封
- 消除各 Controller 内重复繁冗的 try...except JSONResponse 样板代码，实现真正的高内聚薄控制器 (Thin Controller)。
"""

from typing import Any, Optional, Dict
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from loguru import logger


class ResponseEnvelope:
    """统一 API 响应信封深模块"""

    @staticmethod
    def success(
        data: Optional[Any] = None,
        message: Optional[str] = None,
        status_code: int = 200,
        **kwargs: Any,
    ) -> JSONResponse:
        """
        构造标准成功响应
        - ok: True
        - data: 载荷数据 (若提供)
        - message: 提示消息 (若提供)
        - kwargs: 其他透传属性 (如 report, summary, history 等向后兼容字段)
        """
        content: Dict[str, Any] = {"ok": True}
        if data is not None:
            content["data"] = data
        if message is not None:
            content["message"] = message
        content.update(kwargs)
        return JSONResponse(status_code=status_code, content=content)

    @staticmethod
    def error(
        error: str,
        status_code: int = 400,
        message: Optional[str] = None,
        details: Optional[Any] = None,
        **kwargs: Any,
    ) -> JSONResponse:
        """
        构造标准失败响应
        - ok: False
        - error: 错误原因描述
        - status_code: HTTP 响应码 (默认 400)
        - details: 错误详情 (如校验失败字段)
        """
        content: Dict[str, Any] = {"ok": False, "error": error}
        if message is not None:
            content["message"] = message
        if details is not None:
            content["details"] = details
        content.update(kwargs)
        return JSONResponse(status_code=status_code, content=content)

    @classmethod
    def from_result(
        cls,
        result: Optional[Dict[str, Any]],
        default_message: Optional[str] = None,
        error_status_code: int = 400,
    ) -> JSONResponse:
        """
        [Matt Pocock Deep Module] 适配业务服务层字典结果至标准信封
        - 自动侦测 status == 'error' 或 ok is False 并转换为标准失败信封
        - 自动侦测包含 '不存在' / 'not found' 等语义，提供恰当的 HTTP 状态码映射
        - 透传全部既有字段以保证向后兼容性
        """
        if not isinstance(result, dict):
            return cls.success(data=result, message=default_message)

        res_dict = dict(result)
        is_error = res_dict.get("status") == "error" or res_dict.get("ok") is False

        if is_error:
            error_msg = res_dict.get("error") or res_dict.get("message") or "操作执行失败"
            # 自动探测 404 资源未找到场景
            if error_status_code == 400 and ("不存在" in str(error_msg) or "not found" in str(error_msg).lower()):
                status_code = 404
            else:
                status_code = error_status_code
            return cls.error(error=error_msg, status_code=status_code, **res_dict)

        return cls.success(**res_dict)


def register_api_exception_handlers(app: FastAPI) -> None:
    """为 FastAPI 应用注册全局统一异常处理器"""

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        logger.warning(f"⚠️ [APIExceptionHandler] 参数/业务校验异常 ({request.method} {request.url.path}): {exc}")
        return ResponseEnvelope.error(error=str(exc), status_code=400)

    @app.exception_handler(KeyError)
    async def key_error_handler(request: Request, exc: KeyError) -> JSONResponse:
        logger.warning(f"⚠️ [APIExceptionHandler] 目标键不存在异常 ({request.method} {request.url.path}): {exc}")
        return ResponseEnvelope.error(error=f"未找到相关资源: {str(exc)}", status_code=404)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        logger.info(f"ℹ️ [APIExceptionHandler] HTTP 显式异常 ({request.method} {request.url.path}, {exc.status_code}): {exc.detail}")
        return ResponseEnvelope.error(error=str(exc.detail), status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(f"❌ [APIExceptionHandler] 未处理的系统运行时异常 ({request.method} {request.url.path}): {exc}")
        return ResponseEnvelope.error(error=f"内部服务器错误: {str(exc)}", status_code=500)
