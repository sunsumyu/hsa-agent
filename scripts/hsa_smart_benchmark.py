import os
import sys
import asyncio
import time
import json
from datetime import datetime
from loguru import logger

# 环境初始化
sys.path.append(os.getcwd())
os.environ["PYTHONIOENCODING"] = "utf-8"
# [V48.1 极致体验] 强制 HuggingFace 使用离线缓存或快速失败，杜绝网络超时卡死
os.environ["HF_HUB_OFFLINE"] = "1"

if sys.platform == "win32":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

from app.agent_graph import get_graph_executor
from app.model_manager import model_manager
from scripts.token_audit_test import TokenRoleTracker

# 1. 专家评审标准 (七大维度全景评测)
JUDGE_PROMPT = """
你是一名资深医保稽核裁判。请对【审计任务】和【生成的报告】进行严格的定量评审。
评分维度 (每项 10 分，总分 70 分):
1. Success (任务成功率): 任务是否达成，代码/SQL是否成功执行。
2. Recall (召回率): 是否尽可能多地找出了符合条件的违规嫌疑（无遗漏）。
3. Precision (准确率): 找出的违规记录是否精准，没有把正常行为误判为违规。
4. Faithfulness (忠实度): 结论是否完全基于查出的数据，没有任何编造（幻觉）。
5. Relevance (答案相关性): 报告内容是否直接回答了用户最初的问题。
6. Professionalism (专业性): 审计逻辑是否符合医保监管规范与医学常识。
7. Interpretability (可解释性): 报告是否通俗易懂，是否提供了清晰的证据链。

## 评审铁律
- advice 字段**必须**给出至少一条具体、可操作的改进建议（指出报告中缺少什么或可以如何加强）。
- 即使所有维度均满分，也**必须**给出至少一条"锦上添花"建议（如：可增加某类可视化图表、可补充某项交叉验证）。
- 禁止输出空泛的赞美话术（如"保持"、"继续"、"很好"），advice 必须包含具体的报告章节名或技术手段。
- advice 字段使用英文输出。

请严格返回 JSON 格式 (无其他文字):
{"scores": {"success": 0, "recall": 0, "precision": 0, "faithfulness": 0, "relevance": 0, "professionalism": 0, "interpretability": 0}, "total": 0, "advice": "Specific actionable suggestion..."}
"""

# 2. 精选测试用例库 (Chapter 12 标准)
TEST_CASES = {
    "QA-01": {"prompt": "核查 2024 年是否存在同一天、同一患者、在同一医院多次收取的结算费用？", "tag": "基础逻辑/SQL精度"},
    "QA-03": {"prompt": "对全市结算数据进行性别冲突检查：找出男性患者产生妇科或产科费用的异常明细。", "tag": "业务逻辑/属性校验"},
    "QA-06": {"prompt": "核查是否存在同一患者在同一天内，在两家不同医院【同时住院】的情况？", "tag": "复杂关联/跨院对撞"},
    "QA-11": {"prompt": "核查中心医院是否存在与职工共用联系方式（尾号8888）且报销额度异常偏高的患者群？", "tag": "欺诈网络/利益关联"}
}

class SmartAuditorBenchmark:
    def __init__(self):
        self.executor, _ = get_graph_executor()
        self.tracker = TokenRoleTracker()
        self.tracker.patch()
        # 裁判模型
        self.judge_llm, _ = model_manager.get_adaptive_llm(model_id="qwen-max")

    async def run_judge(self, prompt, report):
        """裁判打分逻辑：支持容错解析"""
        try:
            full_input = f"{JUDGE_PROMPT}\n\n审计任务: {prompt}\n生成的报告: {report}"
            res = await self.judge_llm.ainvoke(full_input)
            
            # 强制转为字符串处理
            content = str(res.content)
            
            # 提取 JSON 块
            json_str = content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0]
            
            return json.loads(json_str.strip())
        except Exception as e:
            logger.error(f"评分解析失败: {e} | 原始返回: {res.content if 'res' in locals() else 'None'}")
            return {"total": "N/A", "advice": f"评分解析异常: {e}"}

    async def test_one(self, case_id):
        if case_id not in TEST_CASES:
            print(f"Case ID not found: {case_id}")
            return

        case = TEST_CASES[case_id]
        print(f"\n[START BENCHMARK] ID: {case_id} | TAG: {case['tag']}")
        print(f"Task: {case['prompt']}")
        print("-" * 60)

        self.tracker.reset()
        start_time = time.time()
        
        try:
            inputs = {"messages": [("user", case['prompt'])], "session_id": f"BENCH_{case_id}"}
            # 开启测试运行
            final_state = await self.executor.ainvoke(inputs, config={"recursion_limit": 30})
            duration = time.time() - start_time
            
            # 安全提取最终报告
            report_text = "未生成报告"
            if final_state.get("messages"):
                last_msg = final_state["messages"][-1]
                if isinstance(last_msg, tuple):
                    report_text = last_msg[1]
                else:
                    report_text = getattr(last_msg, "content", str(last_msg))

            # 评审阶段
            print("Running expert judging...")
            eval_res = await self.run_judge(case['prompt'], report_text)

            # 输出全面报告
            self.print_final_report(case_id, case, duration, eval_res)

        except Exception as e:
            logger.error(f"Benchmark failed: {e}")

    def print_final_report(self, case_id, case, duration, eval_res):
        print("\n" + "=" * 60)
        print(f"HSA SMART AUDIT BENCHMARK REPORT - {case_id}")
        print("=" * 60)
        print(f"Latency: {duration:.2f}s")
        print(f"Expert Score: {eval_res.get('total', 0)} / 70")
        if 'scores' in eval_res:
            s = eval_res['scores']
            print("   [Metrics Evaluation]")
            print(f"   ├─ Success (任务成功率)  : {s.get('success',0)}/10")
            print(f"   ├─ Recall (召回率)       : {s.get('recall',0)}/10")
            print(f"   ├─ Precision (准确率)    : {s.get('precision',0)}/10")
            print(f"   ├─ Faithfulness (忠实度) : {s.get('faithfulness',0)}/10")
            print(f"   ├─ Relevance (相关性)    : {s.get('relevance',0)}/10")
            print(f"   ├─ Professionalism(专业) : {s.get('professionalism',0)}/10")
            print(f"   └─ Interpretability(解释): {s.get('interpretability',0)}/10")
        
        print("\nToken Cost Breakdown:")
        total_tokens = 0
        for role, stats in self.tracker.role_stats.items():
            sub = stats['in'] + stats['out']
            total_tokens += sub
            print(f"   {role.ljust(15)}: {sub:>6} tokens ({stats['calls']} calls)")
        print(f"   Total tokens: {total_tokens}")
        
        print(f"\nExpert Advice:\n{eval_res.get('advice', 'None')}")
        print("=" * 60 + "\n")

if __name__ == "__main__":
    benchmark = SmartAuditorBenchmark()
    # 如果通过命令行传入了 ID 则运行指定 ID，否则默认运行 QA-01
    target_id = sys.argv[1] if len(sys.argv) > 1 else "QA-01"
    asyncio.run(benchmark.test_one(target_id))
