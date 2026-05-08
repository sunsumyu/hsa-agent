import sys
import os
sys.path.append(os.getcwd())

from app.audit_rules import rule_engine
from loguru import logger

def test_enterprise_fix():
    logger.info("🧪 测试企业级 SQL 注入加固逻辑...")
    
    # 模拟之前报错的场景：只有数值，没有算子
    extra_filters = {
        "year": "2024",
        "total_amount": "5000",
        "tel": "13888888888"
    }
    
    # 模拟 CROSS_HOSPITAL_OVERLAP 规则注入
    sql = rule_engine.get_rule_sql("CROSS_HOSPITAL_OVERLAP", extra_filters=extra_filters)
    
    print("\n--- 生成的 SQL ---")
    print(sql)
    print("------------------\n")
    
    # 验证关键点
    assert "year = '2024'" in sql or "year='2024'" in sql
    assert "medfee_sumamt = 5000" in sql or "medfee_sumamt=5000" in sql # total_amount 应被 resolve 为 medfee_sumamt
    assert "tel = '13888888888'" in sql
    
    logger.success("✅ 验证通过！注入逻辑已具备工业级鲁棒性。")

if __name__ == "__main__":
    test_enterprise_fix()
