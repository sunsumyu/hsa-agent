"""
app/core/background_worker.py
=============================
[V4.5] 企业级后台异步任务流水线 (Background Worker Pipeline)

职责：
1. 实现计算密集型任务（如实体提取、向量构建）的非阻塞运行。
2. 保护主线程审计逻辑的吞吐量。
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from loguru import logger
from typing import Callable, Any

class BackgroundWorker:
    def __init__(self, max_workers: int = 4):
        self.executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="HSA-BG-Worker"
        )
        self.loop = asyncio.get_event_loop()
        logger.info(f"⚙️ [BackgroundWorker] 后台异步流水线已就绪 | Max Workers: {max_workers}")

    def submit(self, func: Callable, *args, **kwargs):
        """
        提交一个同步函数至后台线程池运行
        """
        try:
            future = self.executor.submit(func, *args, **kwargs)
            logger.debug(f"📤 [BG-Worker] 已提交后台异步任务: {func.__name__}")
            return future
        except Exception as e:
            logger.error(f"❌ [BG-Worker] 任务提交失败: {e}")
            return None

    async def run_async(self, func: Callable, *args, **kwargs):
        """
        在事件循环中运行后台任务
        """
        return await self.loop.run_in_executor(self.executor, func, *args, **kwargs)

# 全局单例
bg_worker = BackgroundWorker()
