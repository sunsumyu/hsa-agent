import os
import sys

# 确保能 import 到 app 模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.skills.schema_manager import schema_manager
from loguru import logger

def main():
    logger.info("🚀 开始执行全量物理 Schema 同步...")
    schema_manager.sync_from_db()
    logger.success("✨ 同步完成！所有物理字段已注入真相中心。")

if __name__ == "__main__":
    main()
