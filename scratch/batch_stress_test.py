import os
import json
import time
import sys
# 强制使用 UTF-8
if sys.stdout.encoding != 'utf-8':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from app.tools import search_expert_knowledge, _execute_audit_sql_logic
from app.skills.audit_rules import rule_engine
from loguru import logger

def run_stress_test():
    scenarios = [
        {"id": "GENDER_CONFLICT", "name": "性别诊断冲突测试", "query": "参保人性别的基本逻辑和诊断代码冲突审计"},
        {"id": "HIGH_FREQ_DRUG_PURCHASE", "name": "高频购药异常测试", "query": "同一人在药店短时间内多次购药的审计规则"},
        {"id": "CROSS_STORE_HIGH_SPEND", "name": "跨店高额消费测试", "query": "同一参保人跨多家药店高额支出的异常识别"},
        {"id": "DECOMPOSITION_HOSPITALIZATION", "name": "分解住院检测测试", "query": "频繁出入院、分解住院套取基金的SQL逻辑"},
        {"id": "CROSS_HOSPITAL_OVERLAP", "name": "跨机构同日结算测试", "query": "同一参保人在不同机构同日重复结算异常审计"}
    ]
    
    print(f"==================== 医疗审计 Agent 真实规则对撞 (5例) ====================")
    
    # 使用 200 万行的宽表进行 Schema 完整性验证
    TARGET_TABLE = "fqz_gz_jzsj_all_ql"
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    
    results = []
    for scenario in scenarios:
        print(f"\n[对撞开始] {scenario['name']} (ID: {scenario['id']})...")
        start_time = time.time()
        
        # 1. 知识检索 (带 Reranker 逻辑)
        print(f"  > 步骤1: 专家知识检索 (Reranker)...")
        knowledge = search_expert_knowledge(scenario['query'])
        
        # 2. 获取并执行 SQL
        sql = rule_engine.get_rule_sql(scenario['id'], table_name=TARGET_TABLE, limit=100)
        
        status = "UNKNOWN"
        evidence_count = 0
        report = ""
        
        if not sql:
            status = "ERROR (No SQL)"
            report = "未找到对应算子"
        else:
            print(f"  > 步骤2: 物理算子执行 (Table: {TARGET_TABLE})...")
            data = _execute_audit_sql_logic(sql, return_raw=True)
            
            if isinstance(data, str):
                status = f"FAILED (SQL Error)"
                report = data
                print(f"    [!] SQL 报错: {data[:100]}")
            else:
                evidence_count = len(data)
                status = "SUCCESS"
                report = rule_engine.format_violation_report(scenario['id'], data)
        
        elapsed = time.time() - start_time
        print(f"  > 状态: {status} | 耗时: {elapsed:.2f}s | 疑似证据: {evidence_count} 条")
        
        results.append({
            "scenario": scenario['name'],
            "status": status,
            "evidence_count": evidence_count,
            "report_preview": str(report)[:100] + "..."
        })
        
    print(f"\n==================== 真实规则对撞汇总报告 ====================")
    for r in results:
        indicator = "[FOUND]" if r['evidence_count'] > 0 else "[EMPTY]"
        print(f"{indicator} [{r['status']}] {r['scenario']}: 找到疑似违规 {r['evidence_count']} 条")

if __name__ == "__main__":
    run_stress_test()
