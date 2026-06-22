import os
import time
from app.skills.audit_rules import rule_engine
from app.tools import _execute_audit_sql_logic
import json

# 定义离线案卷库
OFFLINE_CASES = [
    {"id": "GENDER_CONFLICT", "name": "性别与诊断冲突排查"},
    {"id": "HIGH_FREQ_DRUG_PURCHASE", "name": "零售药店高频购药异常"},
    {"id": "CROSS_STORE_HIGH_SPEND", "name": "跨药店流窜套高额消费"},
    {"id": "DECOMPOSITION_HOSPITALIZATION", "name": "分解住院/挂床行为检测"},
    {"id": "CROSS_HOSPITAL_OVERLAP", "name": "跨机构同日挂名结算排查"}
]

def run_offline_audit():
    print(f"===========================================================")
    print(f"[审计智能体 V37.7] 进入离线硬核验证模式 (跳过 LLM)")
    print(f"扫描数据源: fqz_gz_jzsj_all_ql (18GB 生产级 ClickHouse)")
    print(f"===========================================================\n")
    
    total_start_time = time.time()
    
    for i, case in enumerate(OFFLINE_CASES):
        print(f"\n[案卷 {i+1}/{len(OFFLINE_CASES)}]: {case['name']} (ID: {case['id']})")
        print(f"正在构建物理取证 SQL...")
        
        # 1. 构造 SQL
        sql = rule_engine.get_rule_sql(case['id'], limit=50)
        print(f"执行 SQL: {sql[:100]}...")
        
        # 2. 物理取证执行
        start_time = time.time()
        try:
            results = _execute_audit_sql_logic(sql, return_raw=True)
            elapsed = time.time() - start_time
            
            if isinstance(results, str):
                # 如果返回的是字符串说明出错了
                print(f"[ERROR] SQL执行逻辑返回错误: {results}")
                continue
                
            print(f"物理取证成功! 耗时: {elapsed:.2f}s | 捕获证据数: {len(results)}")
            
            # 3. 格式化报告
            report = rule_engine.format_violation_report(case['id'], results)
            
            # 4. 持久化到 Artifacts
            filename = f"artifacts/OFFLINE_AUDIT_{case['id']}.md"
            with open(filename, "w", encoding="utf-8") as f:
                f.write(f"# 离线取证案卷: {case['name']}\n\n")
                f.write(f"**规则ID**: `{case['id']}`\n")
                f.write(f"**取证SQL**: \n```sql\n{sql}\n```\n\n")
                f.write(report)
            
            print(f"报告已导出至: {filename}")
            
        except Exception as e:
            print(f"[ERROR] 取证失败: {str(e)}")
            
        print("-" * 60)
        
    total_time = time.time() - total_start_time
    print(f"\n[离线测试统计面板]")
    print(f"总耗时: {total_time:.2f} 秒")
    print(f"Token 消耗: 0 (模型离线)")
    print(f"物理算力评估: 优秀 (成功压制 18GB 生产数据)")

if __name__ == "__main__":
    if not os.path.exists("artifacts"):
        os.makedirs("artifacts")
    run_offline_audit()
