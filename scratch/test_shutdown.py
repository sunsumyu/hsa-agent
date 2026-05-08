from app.observability import init_observability
import time
from loguru import logger

if __name__ == "__main__":
    logger.info(">>> [Test] 启动 V38.7 优雅停机测试...")
    init_observability()
    
    # 模拟一段极短的业务逻辑
    logger.info(">>> [Test] 业务逻辑执行完毕，准备退出。")
    time.sleep(1)
    
    # 程序结束时，atexit 钩子应被触发
