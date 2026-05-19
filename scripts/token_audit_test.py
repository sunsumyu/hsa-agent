import os
import sys
import asyncio
import json
from loguru import logger
from datetime import datetime

# 环境初始化
sys.path.append(os.getcwd())
# HF_HOME: use .env or system default
os.environ["LANGFUSE_PUBLIC_KEY"] = "" 
os.environ["LANGFUSE_SECRET_KEY"] = ""
os.environ["PYTHONIOENCODING"] = "utf-8"

from app.core.agent_graph import get_graph_executor, _record_usage_with_budget
from app.infra.usage_tracker import usage_tracker

# ---------------------------------------------------------
# 1. Token 物理追踪拦截器 (改进版：基于 Role 追踪)
# ---------------------------------------------------------
class TokenRoleTracker:
    def __init__(self):
        self.role_stats = {} # {role: {"in": 0, "out": 0, "calls": 0}}
        self._original_record_usage_with_budget = None

    def patch(self):
        # 拦截 _record_usage_with_budget 以获取 Role 信息
        import app.core.agent_graph
        self._original_record_usage_with_budget = app.agent_graph._record_usage_with_budget
        app.agent_graph._record_usage_with_budget = self._intercepted_record_budget

    def _intercepted_record_budget(self, role, response, model_id, prompt=""):
        # 获取内容
        res_text = str(getattr(response, "content", ""))
        
        # 估算
        in_t = usage_tracker._estimate_tokens(prompt)
        out_t = usage_tracker._estimate_tokens(res_text)
        
        print(f"  [Token拦截] 角色: {role} | 模型: {model_id} | In: {in_t}, Out: {out_t}")
        sys.stdout.flush()

        # 归档
        if role not in self.role_stats:
            self.role_stats[role] = {"in": 0, "out": 0, "calls": 0}
        
        self.role_stats[role]["in"] += in_t
        self.role_stats[role]["out"] += out_t
        self.role_stats[role]["calls"] += 1

        # 调用原始逻辑
        self._original_record_usage_with_budget(role, response, model_id, prompt)

    def reset(self):
        self.role_stats = {}

    def print_report(self, case_id, duration):
        print(f"\n{'='*60}")
        print(f"TOKEN Analysis Report (Role-based) - Case: {case_id}")
        print(f"Total Duration: {duration:.2f}s")
        print(f"{'Role':<15} | {'Calls':<8} | {'Input':<10} | {'Output':<10} | {'Subtotal':<10}")
        print("-" * 60)
        
        total_in = 0
        total_out = 0
        for role, s in self.role_stats.items():
            subtotal = s['in'] + s['out']
            total_in += s['in']
            total_out += s['out']
            print(f"{role:<15} | {s['calls']:<8} | {s['in']:<10} | {s['out']:<10} | {subtotal:<10}")
            
        print("-" * 60)
        print(f"{'Total':<15} | {'-':<8} | {total_in:<10} | {total_out:<10} | {total_in + total_out:<10}")
        print(f"{'='*60}\n")
        sys.stdout.flush()

# 初始化追踪器
tracker = TokenRoleTracker()
tracker.patch()

# ---------------------------------------------------------
# 2. 测试执行引擎
# ---------------------------------------------------------
async def run_audit_with_tracking(case_id, prompt):
    print(f"Starting Task: {case_id}...")
    sys.stdout.flush()
    tracker.reset()
    start_time = asyncio.get_event_loop().time()
    
    inputs = {"messages": [("user", prompt)], "session_id": f"TEST_{case_id}"}
    
    try:
        # 增加递归上限到 50，防止复杂任务中断
        config = {"recursion_limit": 50}
        final_state = await executor.ainvoke(inputs, config=config)
        print(f"  Task Completed Successfully")
    except Exception as e:
        print(f"  Task Failed or Interrupted: {str(e)}")
    
    duration = asyncio.get_event_loop().time() - start_time
    tracker.print_report(case_id, duration)

async def main():
    # Case A: 基础取证
    await run_audit_with_tracking(
        "QA-01 (Basic)", 
        "核查 2024 年是否存在同一天、同一患者、在同一医院多次收取的结算费用？"
    )
    
    await asyncio.sleep(2)
    
    # Case B: 复杂对撞
    await run_audit_with_tracking(
        "QA-06 (Complex)", 
        "跨院审计：查询是否存在同一患者在同一天内，在两家不同等级的医院同时住院（Inpatient Overlap）的情况？"
    )

if __name__ == "__main__":
    asyncio.run(main())
