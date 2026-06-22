"""
scratch/test_memory_refactor.py
==============================
[V177.6] 记忆中枢重构验证脚本
"""

import asyncio
import sys
import os

# 强制 UTF-8 环境
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
os.environ["PYTHONIOENCODING"] = "utf-8"

# 确保能找到 app 目录
sys.path.append(os.getcwd())

from app.core.memory import memory_hub
from loguru import logger

async def run_test():
    logger.info("🚀 开始验证工业级记忆中枢...")

    # 1. 模拟知识注入 (Learning Phase)
    logger.info("Step 1: 注入审计业务知识...")
    test_data = [
        {"column": "ipt_days", "table": "fqz_all_yy_yd_1", "desc": "住院天数，用于识别分解住院、挂床住院等风险"},
        {"column": "medfee_sumamt", "table": "fqz_all_yy_yd_1", "desc": "医疗总金额，核心监控指标"},
        {"column": "setl_time", "table": "fqz_all_yy_yd_1", "desc": "结算时间，用于年度统计和跨年分析"}
    ]
    
    for data in test_data:
        # 模拟学习过程：同时存入描述字符串和结构化元数据
        await memory_hub.semantic.learn(
            content=f"字段 {data['column']} 在表 {data['table']} 中表示 {data['desc']}",
            topic="audit_rules",
            importance=0.9,
            metadata=data
        )
    
    # 2. 模拟模糊查询 (Retrieval Phase with HyDE)
    user_query = "我想看看哪些病人频繁住院，可能有分解住院的风险"
    logger.info(f"Step 2: 执行 HyDE 增强检索 -> '{user_query}'")
    
    results = await memory_hub.query(user_query, limit=3, use_hyde=True)
    
    if not results:
        logger.warning("⚠️ HyDE 检索未命中，尝试原始语义匹配...")
        results = await memory_hub.query(user_query, limit=3, use_hyde=False)
    
    # 3. 验证格式化输出 (Formatting Phase)
    logger.info("Step 3: 验证提示词格式化...")
    schema_hint = memory_hub.semantic.format_for_prompt(results)
    
    print("\n" + "="*50)
    print("【LLM 提示词注入结果】")
    print(schema_hint)
    print("="*50 + "\n")

    # 4. 验证避坑指南 (Avoidance Guides)
    logger.info("Step 4: 验证业务避坑指南...")
    guide = memory_hub.semantic.get_avoidance_guides("我想查查职工医保的报销情况")
    if guide:
        print("【业务避坑指南】")
        print(guide)
        print("="*50 + "\n")

if __name__ == "__main__":
    asyncio.run(run_test())
