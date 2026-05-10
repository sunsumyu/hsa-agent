import sys
from loguru import logger

def init_logging():
    """
    [V41.6] 配置生产级点击跳转链路：将逻辑路径改为物理路径格式 {file}:{line}
    以便在 VS Code 等 IDE 终端中直接点击跳转到代码。
    """
    logger.remove()
    logger.add(
        sys.stderr, 
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{file}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        enqueue=False
    )

# 默认在模块加载时初始化一次
init_logging()
