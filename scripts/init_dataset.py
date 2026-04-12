import json
import os

data = [
    {
        "input": "请分析患者 P99999 在 2026 年 1 月 15 日前后的就医行为是否存在异常？",
        "expected_output": "发现高风险异常行为：同日异地住院。该患者于 2026-01-15 同时在上海瑞金医院和江苏省人民医院产生结算数据，涉及金额共计 20000.0 元。违反了医保关于‘参保人在住院期间不得在其他定点医疗机构重复住院结算’的相关规定。",
        "context": "患者 P99999 在 2026-01-15 同日内，于上海和江苏两地产生住院结算明细。其行为符合‘虚假住院’或‘重复套取医保基金’的作案特征。根据《医保稽核管理办法》第18条，此类行为属于重点违规打击范畴。"
    },
    {
        "input": "查询最近一年内，总医疗费用排名前三的定点医疗机构。",
        "expected_output": "Agent 应准确提取汇总表中的聚合金额，并按 Audit-Card-V1 格式分级显示风险机构。",
        "context": "系统中记录了各大医院的结算汇总数据。验证 Agent 是否能正确调用聚合 SQL 并脱敏展示结果。"
    }
]

target_path = r"e:\chain\hsa-agent-python\tests\eval\golden_dataset.json"
os.makedirs(os.path.dirname(target_path), exist_ok=True)

with open(target_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=4)

print(f"Successfully initialized: {target_path}")
