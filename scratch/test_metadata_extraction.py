import sys
import os

# 设置项目根目录
sys.path.append(os.getcwd())

from app.skills.semantic_layer import SemanticRetriever
from loguru import logger

def test_extraction():
    logger.info(">>> [Phase 1 验证] 正在启动语义元数据解析测试...")
    retriever = SemanticRetriever()
    data = retriever.extract_metadata()
    
    if not data:
        logger.error("✘ 测试失败: 未提取到任何元数据。")
        return

    # 关键字段验证
    target_cols = ["psn_no", "medfee_sumamt", "setl_time"]
    found_cols = [item["column"] for item in data]
    
    logger.info("正在核对审计核心字段...")
    for target in target_cols:
        if target in found_cols:
            logger.success(f"✔ 物理映射确认: {target}")
        else:
            logger.warning(f"⚠ 字段缺失: {target}")

    # 展示具体样例
    logger.info("\n提取样例 (前3条):")
    for item in data[:3]:
        print(f"  - {item['column']}: {item['desc']}")

if __name__ == "__main__":
    test_extraction()
