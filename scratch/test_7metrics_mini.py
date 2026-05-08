# -*- coding: utf-8 -*-
"""
HSA 7-Dimension Agent Benchmark [MINIMAL TEST]
==============================================
Runs only one case (QA-01) to verify the 7-dimension scoring logic.
"""
import os, sys, asyncio, json, time, subprocess
from datetime import datetime
from loguru import logger
from langchain_core.messages import BaseMessage
from typing import Any, List, Union

# Use Rich for better console output if available
try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.table import Table
    from rich.theme import Theme
    from rich.syntax import Syntax
    console = Console(theme=Theme({
        "info": "cyan",
        "warning": "yellow",
        "error": "bold red",
        "success": "bold green",
        "role": "bold magenta"
    }))
except ImportError:
    console = None

def log_print(msg):
    if console:
        console.print(msg)
    else:
        print(msg)
    sys.stdout.flush()

log_print("[info]Importing dependencies...[/]")
sys.path.append(os.getcwd())
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["HF_HUB_OFFLINE"]  = "1"

log_print("[info]Loading Agent Graph and Model Manager... (This may take 30-60s due to local embedding models)[/]")
from app.agent_graph import workflow
from app.model_manager import model_manager
from app.usage_tracker import usage_tracker
log_print("[success]✓ Models and Graph loaded.[/]")

# Import logic from run_7metrics_bench (cloned for minimal test)
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

TEST_CASES = [
    {
        "id": "MINI-01", "tag": "Repeat Billing", "diff": "*   ",
        "prompt": "核查 2024 年是否存在同一天、同一患者、在同一医院多次收取的结算费用？",
        "pred_tokens": 9000,
    }
]

async def run_mini_test():
    if console:
        console.rule("[bold cyan]HSA 7-Dimension Minimal Test Starting[/]")
    else:
        print("=== HSA 7-Dimension Minimal Test Starting ===")

    # Initialize Judge LLM
    try:
        judge_llm, judge_model = model_manager.get_adaptive_llm(model_id="doubao-pro-32k")
        if console:
            console.print(f"[success][OK][/] Judge Model: [bold]{judge_model}[/]")
    except Exception as e:
        logger.error(f"Failed to initialize judge LLM: {e}")
        return

    case = TEST_CASES[0]
    cid, prompt = case["id"], case["prompt"]
    
    if console:
        console.print(Panel(f"Question: [bold]{prompt}[/]", title=f"Case {cid}", border_style="cyan"))
    else:
        print(f"Case {cid}: {prompt}")

    t0 = time.time()
    report_text = "(no report)"
    agent_ok = False

    try:
        inputs = {"messages": [("user", prompt)], "session_id": f"MINI_BENCH_{int(t0)}"}
        # Run workflow
        state = await workflow.ainvoke(inputs, config={"recursion_limit": 15})
        agent_ok = True
        msgs = state.get("messages", [])
        if msgs:
            last = msgs[-1]
            report_text = last[1] if isinstance(last, tuple) else getattr(last, "content", str(last))
    except Exception as ex:
        report_text = f"(Agent error: {ex})"
        logger.error(f"[{cid}] Agent error: {ex}")

    agent_t = time.time() - t0

    if console:
        console.print(Panel(report_text, title="Final Audit Report", border_style="green"))
    else:
        print(f"\nFinal Audit Report:\n{report_text}\n")

    # Judge Phase
    if console:
        console.print("[info]Judging report...[/]")
    
    judge_input = f"{JUDGE_PROMPT}\n\nAudit Task: {prompt}\n\nGenerated Report:\n{report_text[:4000]}"
    
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
            table = Table(title=f"7-Dimension Scores for {cid}")
            table.add_column("Dimension", style="magenta")
            table.add_column("Score", justify="right", style="green")
            table.add_column("Bar")

            dims = ["success", "recall", "precision", "faithfulness", "relevance", "professionalism", "interpretability"]
            for d in dims:
                v = sc.get(d, 0)
                bar = "█" * int(v) + "░" * (10 - int(v))
                table.add_row(d.capitalize(), str(v), bar)
            
            console.print(table)
            console.print(f"[bold yellow]Total Score: {total} / 70[/]")
            console.print(f"[bold]Advice:[/] {advice}")
        else:
            print(f"\nScores: {sc}")
            print(f"Total: {total}/70")
            print(f"Advice: {advice}")

    except Exception as ex:
        logger.error(f"Judge error: {ex}")
        if console:
            console.print(f"[error]Judge failed: {ex}[/]")

    judge_t = time.time() - tj0
    if console:
        console.print(f"\n[info]Time:[/] Agent {agent_t:.1f}s, Judge {judge_t:.1f}s")

if __name__ == "__main__":
    asyncio.run(run_mini_test())
