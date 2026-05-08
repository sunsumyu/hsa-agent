# -*- coding: utf-8 -*-
"""
HSA 7-Dimension Metrics Logic Test (Mocked Agent)
================================================
Tests the 7-dimension scoring logic using a pre-generated report.
This avoids heavy model loading and focuses on the evaluation metrics.
"""
import os, sys, asyncio, json, time
from datetime import datetime
from loguru import logger

# Use Rich for better console output if available
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.theme import Theme
    console = Console(theme=Theme({
        "info": "cyan",
        "warning": "yellow",
        "error": "bold red",
        "success": "bold green"
    }))
except ImportError:
    console = None

sys.path.append(os.getcwd())
from app.model_manager import model_manager

JUDGE_PROMPT = """You are a senior healthcare insurance audit judge.
Score the following audit report on 7 dimensions (0-10 each, total 70):
1. Success       : Was the task completed? Did SQL/code execute?
2. Recall        : Were all suspicious violations found (no omissions)?
3. Precision     : Are flagged violations accurate (no false positives)?
4. Faithfulness  : Is the conclusion grounded in actual data (no hallucination)?
5. Relevance     : Does the report directly answer the original question?
6. Professionalism: Is the audit logic compliant with healthcare insurance regulations?
7. Interpretability: Is the report clear with solid evidence chains?

Return STRICT JSON (no extra text):
{"scores": {"success": 0, "recall": 0, "precision": 0, "faithfulness": 0, "relevance": 0, "professionalism": 0, "interpretability": 0}, "total": 0, "advice": "..."}
"""

# A mock report for testing the judge
MOCK_TASK = "核查 2024 年是否存在同一天、同一患者、在同一医院多次收取的结算费用？"
MOCK_REPORT = """
# 🔍 医保专项稽核报告

**审计总结**: 本次核查针对 2024 年度“同一天、同一患者、同一医院重复收费”的可疑行为进行了专项扫描。
**审计发现**:
1. 发现患者“张三”在 2024-03-12 于“中心医院”产生了 3 笔完全相同的挂号费。
2. 发现患者“李四”在 2024-05-20 于“中心医院”产生了 2 笔住院诊查费。
**涉及金额**: ¥450.00
**风险等级**: 低
**审计建议**: 建议该医院核查收费系统是否存在重复触发，或是否存在分解收费行为。
"""

async def run_metrics_logic_test():
    if console:
        console.rule("[bold cyan]HSA 7-Dimension Metrics Logic Test[/]")
    else:
        print("=== HSA 7-Dimension Metrics Logic Test ===")

    print(f"Task: {MOCK_TASK}")
    print("Report: (Mocked Report provided for evaluation)")

    # Initialize Judge LLM (using Doubao)
    try:
        judge_llm, judge_model = model_manager.get_adaptive_llm(model_id="doubao-pro-32k")
        if console:
            console.print(f"[success][OK][/] Judge Model: [bold]{judge_model}[/]")
    except Exception as e:
        logger.error(f"Failed to initialize judge LLM: {e}")
        return

    # Judge Phase
    if console:
        console.print("[info]Judging report...[/]")
    else:
        print("Judging report...")
    
    judge_input = f"{JUDGE_PROMPT}\n\nAudit Task: {MOCK_TASK}\n\nGenerated Report:\n{MOCK_REPORT}"
    
    tj0 = time.time()
    try:
        res = await judge_llm.ainvoke(judge_input)
        content = str(res.content)
        
        # Parse JSON
        js = content
        if "```json" in content:
            js = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            js = content.split("```")[1].split("```")[0]
        else:
            s, e = content.find("{"), content.rfind("}")
            if s != -1 and e != -1:
                js = content[s:e+1]
        
        eval_res = json.loads(js.strip())
        
        # Display Results
        sc = eval_res.get("scores", {})
        total = eval_res.get("total", 0)
        advice = eval_res.get("advice", "")

        if console:
            table = Table(title="7-Dimension Audit Evaluation Results")
            table.add_column("Dimension", style="magenta")
            table.add_column("Score", justify="right", style="green")
            table.add_column("Bar")

            dims = ["success", "recall", "precision", "faithfulness", "relevance", "professionalism", "interpretability"]
            for d in dims:
                v = sc.get(d, 0)
                bar = "█" * int(v) + "░" * (10 - int(v))
                table.add_row(d.capitalize(), str(v), bar)
            
            console.print(table)
            console.print(Panel(f"[bold yellow]Total Score: {total} / 70[/]\n[bold]Advice:[/] {advice}", title="Judge Summary"))
        else:
            print(f"\nScores: {sc}")
            print(f"Total: {total}/70")
            print(f"Advice: {advice}")

    except Exception as ex:
        logger.error(f"Judge error: {ex}")
        if console:
            console.print(f"[error]Judge failed: {ex}[/]")

    judge_t = time.time() - tj0
    print(f"\nEvaluation completed in {judge_t:.1f}s")

if __name__ == "__main__":
    asyncio.run(run_metrics_logic_test())
