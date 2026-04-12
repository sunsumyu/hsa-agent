import asyncio
import os
import json
from dotenv import load_dotenv
from app.model_manager import model_manager
from app.agent import get_executor
from app.tools import execute_audit_sql, list_tables, get_table_schema, calculator, search_expert_knowledge

load_dotenv(override=True)

# 定义地狱级 Hard Cases
HARD_CASES = [
    {
        "id": "JOIN_CATALOG",
        "question": "深度排查：检查是否存在医保目录外药品违规报销的情况？请核对 fqz_fymx_test 明细表与专家目录库。",
        "gold_sql": "SELECT t1.fixmedins_name, t1.hilist_name FROM fqz_fymx_test t1 LEFT JOIN fqz_drug_mcs_info_list t2 ON t1.hilist_code = t2.med_list_code WHERE t2.med_list_code IS NULL"
    },
    {
        "id": "GENDER_LOGIC",
        "question": "常识冲突排查：是否存在男性患者计费了‘子宫检查’或‘产科护理’相关项目的记录？",
        "gold_sql": "SELECT psn_name, gend, hilist_name FROM fqz_fymx_test WHERE gend = '1' AND (hilist_name LIKE '%子宫%' OR hilist_name LIKE '%产科%')"
    },
    {
        "id": "RESTRICTED_MEDS",
        "question": "限用合规性审计：识别由于‘感冒’原因却使用了‘限工伤或限大病’报销药物的违规行为。",
        "gold_sql": "SELECT t1.psn_no, t1.hilist_name, t2.nat_hi_druglist_memo FROM fqz_fymx_test t1 JOIN fqz_drug_mcs_info_list t2 ON t1.hilist_code = t2.med_list_code WHERE t2.nat_hi_druglist_memo LIKE '%限%' AND t1.disease_name LIKE '%感冒%'"
    }
]

async def capture_rag_failure():
    model_id = "doubao-pro-32k"  # 使用最强模型来证明 RAG 的逻辑局限
    executor, resolved_id = get_executor(model_id=model_id)
    
    results = []
    
    print(f"--- 正在执行 RAG 翻车对撞实验 [模型: {model_id}] ---")
    
    for case in HARD_CASES:
        print(f"正在测试用例: {case['id']}...")
        try:
            # 执行回复
            res = await executor.ainvoke({"input": case["question"], "chat_history": []})
            output = res["output"]
            
            # 尝试从回答中提取 SQL (简单正则)
            rag_sql = "未生成有效 SQL"
            if "```sql" in output:
                rag_sql = output.split("```sql")[1].split("```")[0].strip()
            
            results.append({
                "id": case["id"],
                "question": case["question"],
                "gold_sql": case["gold_sql"],
                "rag_sql": rag_sql,
                "rag_output": output[:200] + "..."
            })
        except Exception as e:
            results.append({
                "id": case["id"],
                "status": "ERROR",
                "error": str(e)
            })
            
    with open("data/rag_failure_report.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    
    print("\n实验完成！结果已写入 data/rag_failure_report.json")

if __name__ == "__main__":
    asyncio.run(capture_rag_failure())
