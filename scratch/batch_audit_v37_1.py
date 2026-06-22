import asyncio
import os
import sys
import json
import re
import time
from datetime import datetime

# 锁定绝对路径
BASE_DIR = "e:/chain/hsa-agent"
sys.path.append(BASE_DIR)
os.chdir(BASE_DIR)

from app.agent_graph import get_graph_executor
from app.semantic_layer import get_embedding_model

SCENARIO_FILE = os.path.join(BASE_DIR, "docs/1000_business_audit_scenarios.md")
CHECKPOINT_FILE = os.path.join(BASE_DIR, "data/batch_v37_1_checkpoint.json")
RESULTS_FILE = os.path.join(BASE_DIR, "data/batch_v37_1_results.json")

async def batch_runner_v37_1():
    print(f"🔥 [BATCH-AUDIT V37.1] 启动！工作目�? {os.getcwd()}")
    
    if not os.path.exists(SCENARIO_FILE):
        print(f"�?错误: 找不到题库文�?{SCENARIO_FILE}")
        return

    with open(SCENARIO_FILE, "r", encoding="utf-8") as f:
        content = f.read()
    
    questions = re.findall(r'^\d+\.\s+(.+)$', content, re.MULTILINE)
    print(f"📦 已解�?{len(questions)} 个业务场景�?)

    start_index = 0
    results = []
    
    # 加载断点
    if os.path.exists(CHECKPOINT_FILE):
        try:
            with open(CHECKPOINT_FILE, "r", encoding="utf-8") as f:
                start_index = json.load(f).get("last_index", 0)
        except: pass

    if os.path.exists(RESULTS_FILE) and start_index > 0:
        try:
            with open(RESULTS_FILE, "r", encoding="utf-8") as f:
                results = json.load(f)
        except: pass

    executor, _ = get_graph_executor()
    get_embedding_model() # 预热

    for i in range(start_index, len(questions)):
        q = questions[i]
        print(f"🚀 [{i+1}/{len(questions)}] 正在审计: {q[:60]}...")
        
        attempt = 0
        success = False
        while attempt < 3 and not success:
            try:
                start_ts = time.time()
                inputs = {"messages": [("user", q)], "retry_count": 0}
                
                final_state = {}
                async for event in executor.astream(inputs, stream_mode="updates"):
                    node_name = list(event.keys())[0]
                    final_state.update(event[node_name])

                latency = time.time() - start_ts
                
                # 增强版结果记�?(参�?RAG 评估维度)
                res = {
                    "index": i + 1,
                    "query": q,
                    "sql": final_state.get("sql_query", "N/A"),
                    "status": "SUCCESS",
                    "metrics": {
                        "total_latency": latency,
                        "nodes": final_state.get("usage_metadata", {}).get("nodes_touched", []),
                        "token_usage": final_state.get("usage_metadata", {}).get("total_tokens", 0)
                    },
                    "timestamp": datetime.now().isoformat()
                }
                results.append(res)
                success = True
                
                # 强制物理落盘
                with open(RESULTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(results, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                
                with open(CHECKPOINT_FILE, "w", encoding="utf-8") as f:
                    json.dump({"last_index": i + 1}, f)
                    f.flush()
                    os.fsync(f.fileno())

            except Exception as e:
                attempt += 1
                if "429" in str(e):
                    wait_time = attempt * 15
                    print(f"⚠️ 限流拦截，休�?{wait_time}s...")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"�?异常: {e}")
                    results.append({"index": i+1, "query": q, "status": "FAIL", "error": str(e)})
                    success = True

    print("🏁 [FINISH] 1000 场景审计全量完成�?)

if __name__ == "__main__":
    asyncio.run(batch_runner_v37_1())

