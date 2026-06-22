import sys
import os
sys.path.append("e:/chain/hsa-agent")
from loguru import logger

try:
    from app.core.memory.manager import memory_hub
    logger.success("Successfully imported memory_hub")
    print(f"Current mode: {memory_hub.get_stats().get('memory_mode', 'unknown')}")
except Exception as e:
    logger.error(f"Import failed: {e}")
    import traceback
    traceback.print_exc()
