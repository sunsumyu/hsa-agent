import json
import random
import os
import re

# 确保目录存在
os.makedirs("data", exist_ok=True)

# 动态 Schema 加载器
KB_DIR = r"C:\Users\AREN\.gemini\antigravity\knowledge"

def get_real_tables():
    tables = {}
    ck_file = os.path.join(KB_DIR, "db_schema_clickhouse.md")
    if os.path.exists(ck_file):
        with open(ck_file, "r", encoding="utf-8") as f:
            content = f.read()
            # 简单提取表名
            table_matches = re.findall(r"## 表: `(.*?)`", content)
            for t in table_matches:
                tables[t] = "clickhouse"
    return tables

REAL_TABLES = get_real_tables()
MAIN_TABLE = "fqz_all_yy_yd_1" if "fqz_all_yy_yd_1" in REAL_TABLES else "fqz_cgzhan_hosp"

SCENARIOS = [
    {
        "type": "statistical_audit",
        "instruction": "分析各医疗机构的医疗费用变动趋势，识别增长异常的单位。",
        "sql_template": f"SELECT fixmedins_name, sum(medfee_sumamt) as total_fee FROM {MAIN_TABLE} GROUP BY fixmedins_name ORDER BY total_fee DESC",
        "thought": f"费用增长审计应优先使用结算汇总表 {MAIN_TABLE}。通过对机构名进行分组并汇总金额，可以识别异常的高额结算清单。"
    },
    {
        "type": "hospitalization_stat",
        "instruction": "排查平均住院天数明显偏高的医疗机构（疑似挂床）。",
        "sql_template": "SELECT fixmedins_name, avg(avg_ipt_days) as avg_days FROM fqz_cgzhan_hosp GROUP BY fixmedins_name HAVING avg_days > 15",
        "thought": "挂床住院在统计层面表现为平均住院天数异常。使用统计表 fqz_cgzhan_hosp 的 avg_ipt_days 字段进行聚合分析。"
    },
    {
        "type": "regional_summary",
        "instruction": "统计各医保区划（admdvs）下的医疗基金支出占比。",
        "sql_template": f"SELECT admdvs, sum(fund_pay_sumamt) as fund_total FROM {MAIN_TABLE} GROUP BY admdvs",
        "thought": f"区划审计需要关联 admdvs 字段。在 {MAIN_TABLE} 中汇总统筹基金支付金额，用于分析区域间的保障差异。"
    },
    {
        "type": "amount_verification",
        "instruction": "查询最近一笔超过 5000 元的异地结算记录记录。",
        "sql_template": f"SELECT fixmedins_name, medfee_sumamt, setl_time FROM {MAIN_TABLE} WHERE medfee_sumamt > 5000 ORDER BY setl_time DESC LIMIT 1",
        "thought": f"针对大额记录审计，直接从 {MAIN_TABLE} 筛选 sumamt 大于 5000 的记录，并取最新一笔。"
    }
]

def generate_sft_data(count=200):
    dataset = []
    
    for i in range(count):
        scenario = random.choice(SCENARIOS)
        
        # 增加提问的多样性
        prefix = random.choice(["", "请", "作为专家，请", "系统任务："])
        question = f"{prefix}{scenario['instruction']}"
        
        # 构造专家级思维链
        entry = {
            "conversations": [
                {
                    "from": "system",
                    "value": f"你是一名专业的医保审计专家。你熟悉 ClickHouse 语法。主审计表为 {MAIN_TABLE}。"
                },
                {
                    "from": "human",
                    "value": question
                },
                {
                    "from": "gpt",
                    "value": f"⟦THOUGHT⟧\n{scenario['thought']}\n我将首先通过 get_table_schema 验证字段准确性，然后执行 SQL。\n\n⟦REASONING⟧\n执行 SQL 如下：\n```sql\n{scenario['sql_template']}\n```"
                }
            ]
        }
        dataset.append(entry)
        
    return dataset

if __name__ == "__main__":
    data = generate_sft_data(300)
    output_path = "data/audit_sft_train_synced.jsonl"
    with open(output_path, "w", encoding="utf-8") as f:
        for entry in data:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            
    print(f"成功生成 {len(data)} 条对齐真实 Schema 的 SFT 训练数据：{output_path}")
