import sys
import os
# 导入加固后的组件
from app.security import SQLGuardian, SQLComplexityError
from app.agent_graph import should_audit_and_retry, AuditState

def stress_test_v2():
    print("\n" + "="*60)
    print(">>> [STRESS TEST V2.0] 启动架构硬化极限验收")
    print("="*60 + "\n")

    # --- 1. AST 深度拦截测试 (JOIN Contract) ---
    print("SCENARIO 1: 检测别名掩盖下的高危 JOIN...")
    # 模拟一个使用别名且缺失 psn_no 过滤的复杂自连接
    obfuscated_join_sql = """
    SELECT t1.psn_no, t2.start_date 
    FROM fqz_gz_jzsj_all_ql AS t1
    JOIN fqz_gz_jzsj_all_ql AS t2 ON t1.start_date = t2.start_date
    """
    try:
        SQLGuardian.validate_sql(obfuscated_join_sql)
        print("[FAIL] Scenario 1 失败：AST 未能识别出别名背后的自连接风险！")
    except SQLComplexityError as e:
        print(f"[PASS] Scenario 1 成功：AST 解析器精准识破别名干扰 -> {e}")

    # --- 2. 字段类型 AST 拦截测试 (Type Safety) ---
    print("\nSCENARIO 2: 检测 String 字段裸聚合拦截...")
    illegal_agg_sql = "SELECT SUM(ipt_days) FROM fqz_all_yy_yd_1"
    try:
        SQLGuardian.validate_sql(illegal_agg_sql)
        print("[FAIL] Scenario 2 失败：AST 未能拦截对 String 字段的裸聚合！")
    except SQLComplexityError as e:
        print(f"[PASS] Scenario 2 成功：AST 聚合探测器已生效 -> {e}")

    # --- 3. 重试熔断与降级路由测试 (Retry Sandbox) ---
    print("\nSCENARIO 3: 检测 MAX_RETRIES 路由熔断...")
    # 模拟重试次数已达上限且仍有错误的 State
    degraded_state = {
        "retry_count": 3,
        "error_log": "DB Connection Refused (Timeout Simulation)",
        "messages": []
    }
    next_node = should_audit_and_retry(degraded_state)
    if next_node == "REPORTER":
        print("[PASS] Scenario 3 成功：重试耗尽后强制流向 REPORTER 执行降级。")
    else:
        print(f"[FAIL] Scenario 3 失败：重试耗尽后意外流向了 {next_node}。")

if __name__ == "__main__":
    stress_test_v2()
