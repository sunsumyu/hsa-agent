import asyncio
import os
import sys
import json
import re
import time
from datetime import datetime

# 注入 PYTHONPATH
sys.path.append("e:/chain/hsa-agent-python")
os.chdir("e:/chain/hsa-agent-python")

from app.agent_graph import get_graph_executor
from app.semantic_layer import get_embedding_model

SCENARIO_FILE = "docs/1000_business_audit_scenarios.md"
CHECKPOINT_FILE = "data/batch_audit_checkpoint.json"
RESULTS_FILE = "data/batch_audit_results_full.json"

async def batch_runner():
    print("🔥 [BATCH-AUDIT] 1000 场景全量自动化审计引擎启动...")
    
    # 1. 解析题库
    with open(SCENARIO_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    
    # 正则提取所有以数字开头的业务问题
    questions = re.findall(r'^\d+\.\s+(.+)$', content, re.MULTILINE)
    print(f"📦 已加载 {len(questions)} 个业务场景。")

    # 2. 加载进度
    start_index = 0
    results = []
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            checkpoint = json.load(f)
            start_index = checkpoint.get("last_index", 0)
            print(f"↩️ 发现断点，从第 {start_index + 1} 个问题继续...")
    
    if os.path.exists(RESULTS_FILE) and start_index > 0:
        with open(RESULTS_FILE, "r", encoding="utf-8") as f:
            results = json.load(f)

    # 3. 运行引擎
    executor, _ = get_graph_executor()
    get_embedding_model() # 预热

    for i in range(start_index, len(questions)):
        q = questions[i]
        print(f"[{i+1}/{len(questions)}] 正在审计: {q[:50]}...")
        
        attempt = 0
        success = False
        while attempt < 3 and not success:
            try:
                start_ts = time.time()
                inputs = {"messages": [("user", q)], "retry_count": 0}
                
                final_state = None
                async for event in executor.astream(inputs, stream_mode="updates"):
                    node_name = list(event.keys())[0]
                    final_state = event[node_name]

                latency = time.time() - start_ts
                
                # 记录结果
                res = {
                    "index": i + 1,
                    "query": q,
                    "sql": final_state.get("sql_query", "N/A"),
                    "latency": latency,
                    "status": "SUCCESS"
                }
                results.append(res)
                success = True
                
                # 每 5 个保存一次，防止崩溃
                if len(results) % 5 == 0:
                    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
                        json.dump(results, f, indent=2, ensure_ascii=False)
                    with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
                        json.dump({"last_index": i + 1}, f)

            except Exception as e:
                attempt += 1
                if "429" in str(e):
                    wait_time = attempt * 10
                    print(f"⚠️ 触发限流，休眠 {wait_time}s 后重试...")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"❌ 运行报错: {e}")
                    results.append({"index": i+1, "query": q, "status": "ERROR", "error": str(e)})
                    success = True # 跳过报错项

    # 4. 最终导出
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print("🏁 [FINISH] 1000 场景审计完成！结果已存入 batch_audit_results_full.json")

if __name__ == "__main__":
    asyncio.run(batch_runner())
