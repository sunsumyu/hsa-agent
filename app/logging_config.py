import os
import sys
from loguru import logger

LOG_DIR = os.path.join(os.getcwd(), "logs")

def init_logging():
    """
    [V41.6] 配置生产级点击跳转链路：将逻辑路径改为物理路径格式 {file}:{line}
    以便在 VS Code 等 IDE 终端中直接点击跳转到代码。
    [V90.1] 增加文件 sink：终端 + 文件双输出，文件按 50MB 轮转保留 7 天。
    """
    os.makedirs(LOG_DIR, exist_ok=True)
    logger.remove()
    # 1. 终端输出
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{file}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        enqueue=False
    )
    # 2. 文件输出（轮转保留）
    logger.add(
        os.path.join(LOG_DIR, "app_{time:YYYY-MM-DD}.log"),
        rotation="50 MB",
        retention="7 days",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {file}:{line} - {message}",
        enqueue=True,
        backtrace=True,
        diagnose=True,
    )

# 默认在模块加载时初始化一次
init_logging()
