import os
import sys
from loguru import logger

# 环境初始化
sys.path.append(os.getcwd())

from app.skills.sql_validator import sql_validator

def test_sql_equivalence():
    logger.info("🧪 [AST TEST] 正在执行 SQL 语义等价性对比测试...")
    
    # 场景 A: 格式不同，但逻辑完全一致
    sql_a1 = "SELECT psn_no, medfee_sumamt FROM fqz_gz_jzsj_all_ql WHERE medfee_sumamt > 500"
    sql_a2 = """
    -- 这是一个经过优化的查询
    SELECT 
        PSN_NO, 
        MEDFEE_SUMAMT 
    FROM fqz_gz_jzsj_all_ql 
    WHERE medfee_sumamt > 500 
    """
    
    # 场景 B: 逻辑不同
    sql_b1 = "SELECT count(*) FROM t1 WHERE id = 1"
    sql_b2 = "SELECT count(*) FROM t1 WHERE id = 2"

    logger.info("--- [Test Case 1: 格式变体比对] ---")
    is_eq, reason = sql_validator.are_equivalent(sql_a1, sql_a2)
    if is_eq:
        logger.success(f"✅ 判定一致: {reason}")
    else:
        logger.error(f"❌ 判定失败: {reason}")

    logger.info("--- [Test Case 2: 阈值差异比对] ---")
    is_eq, reason = sql_validator.are_equivalent(sql_b1, sql_b2)
    if not is_eq:
        logger.success(f"✅ 成功检测到逻辑差异: {reason}")
    else:
        logger.error(f"❌ 误报：未检测到逻辑差异")

if __name__ == "__main__":
    test_sql_equivalence()
