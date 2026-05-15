# -*- coding: utf-8 -*-
"""
HSA 7-Dimension Agent Benchmark  [VERBOSE MODE]
================================================
每个节点的完整 Prompt + 完整 Response 全部打印到控制台。
"""
import os, sys, asyncio, json, time, subprocess
from datetime import datetime
from loguru import logger
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langchain_core.outputs import LLMResult
from typing import Any, List, Union

# [V58.0] Visual Enhancement
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.theme import Theme
from rich.text import Text
from rich.live import Live
from rich.status import Status

console = Console(theme=Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "role": "bold magenta"
}))

sys.path.append(os.getcwd())
os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["HF_HUB_OFFLINE"]  = "1"

if sys.platform == "win32":
    # 强制 Windows 终端输出 UTF-8，防止 UnicodeEncodeError (GBK)
    import io
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

from app.agent_graph import workflow, _record_usage_with_budget
from app.model_manager import model_manager
from app.usage_tracker import usage_tracker
from app.observability import init_observability, shutdown_observability

# ── LangChain Callback: 每次 LLM 调用前后完整打印 ────────────────────
SEP  = "=" * 72
SEP2 = "-" * 72
SEP3 = "~" * 72

class VerboseLLMCallback(BaseCallbackHandler):
    """拦截 LangChain 的每次 LLM 调用，使用 Rich 美化输出。"""

    def _render_content(self, content: Any) -> str:
        if isinstance(content, str):
            # 尝试检测是否为 SQL
            if "SELECT" in content.upper() and "FROM" in content.upper():
                return Syntax(content, "sql", theme="monokai", word_wrap=True)
            return content
        return str(content)

    def on_chat_model_start(self, serialized: dict, messages: List[List[BaseMessage]], **kwargs):
        model = serialized.get("name", serialized.get("id", ["?"])[-1])
        console.rule(f"[bold blue]LLM INVOKE: {model}[/]", style="blue")
        
        for turn in messages:
            for msg in turn:
                role = type(msg).__name__.replace("Message", "")
                color = "magenta" if role == "System" else "green" if role == "Human" else "cyan"
                
                content = getattr(msg, "content", str(msg))
                # 如果内容是 SQL，使用 Syntax 高亮
                if isinstance(content, str) and ("SELECT" in content.upper() or "INSERT" in content.upper()):
                    display = Syntax(content, "sql", theme="monokai", word_wrap=True)
                else:
                    display = content

                console.print(Panel(
                    display, 
                    title=f"[bold {color}]{role}[/]", 
                    border_style=color,
                    padding=(0, 1)
                ))

    def on_llm_end(self, response: LLMResult, **kwargs):
        for gen_list in response.generations:
            for gen in gen_list:
                text = getattr(gen, "text", None) or getattr(getattr(gen, "message", None), "content", str(gen))
                console.print(Panel(
                    text, 
                    title="[bold yellow]LLM RESPONSE[/]", 
                    border_style="yellow",
                    padding=(0, 1)
                ))
        console.print("\n")

    def on_llm_error(self, error: Union[Exception, KeyboardInterrupt], **kwargs):
        console.print(Panel(str(error), title="[bold red]LLM ERROR[/]", border_style="red"))

# 全局回调实例（注入到每次 workflow.ainvoke 的 config 中）
VERBOSE_CB = VerboseLLMCallback()


# ── Token Predictions ─────────────────────────────────────────────────
PREDICTED = {
    "planner_light": {"in": 1800, "out": 700},
    "planner_heavy": {"in": 2200, "out": 900},
    "sqlexec":       {"in": 1200, "out": 600},
    "reporter":      {"in": 2000, "out": 1000},
    "judge":         {"in": 1100, "out": 400},
}

# ── Test Cases ────────────────────────────────────────────────────────
TEST_CASES = [
    {
        "id": "QA-01", "tag": "Repeat Billing",      "diff": "*   ",
        "prompt": "核查 2024 年是否存在同一天、同一患者、在同一医院多次收取的结算费用？",
        "pred_tokens": 9000,
    },
    {
        "id": "QA-03", "tag": "Gender Conflict",     "diff": "**  ",
        "prompt": "对全市结算数据进行性别冲突检查：找出男性患者产生妇科或产科费用的异常明细。",
        "pred_tokens": 10500,
    },
    {
        "id": "QA-06", "tag": "Dual Hospitalization","diff": "*** ",
        "prompt": "核查是否存在同一患者在同一天内，在两家不同医院【同时住院】的情况？",
        "pred_tokens": 13000,
    },
    {
        "id": "QA-11", "tag": "Fraud Network",        "diff": "****",
        "prompt": "核查中心医院是否存在与职工共用联系方式（尾号8888）且报销额度异常偏高的患者群？",
        "pred_tokens": 15000,
    },
]

# ── Judge Prompt ──────────────────────────────────────────────────────
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

# ── Print Helpers ─────────────────────────────────────────────────────
SEP  = "=" * 72
SEP2 = "-" * 72
SEP3 = "~" * 72

def print_block(title: str, content: str, sep: str = SEP2):
    """把一段内容用明显的边框打印出来"""
    print(f"\n{sep}")
    print(f"  {title}")
    print(sep)
    # 每行加缩进
    for line in content.splitlines():
        print(f"  {line}")
    print(sep)
    sys.stdout.flush()

# ── Physical Token + Content Interceptor ─────────────────────────────
class PhysicalTokenTracker:
    """
    拦截 _record_usage_with_budget：
      1. 打印完整 Prompt（每个 message 逐条输出）
      2. 打印完整 Response
      3. 统计 Token 并与预测对比
    """
    def __init__(self):
        self.case_stats   = {}
        self._current     = None
        self._original_fn = None

    def set_case(self, cid):
        self._current        = cid
        self.case_stats[cid] = {}

    def patch(self):
        import app.agent_graph as ag
        self._original_fn = ag._record_usage_with_budget
        ref = self

        def intercepted(role, response, model_id, prompt=""):
            resp_text = str(getattr(response, "content", ""))
            prompt_str = str(prompt)

            # [V58.5] 采用 Rich 协议重构终端回显，解决数据原始堆叠问题
            console.rule(f"[bold yellow]NODE: {role.upper()}[/] | [bold cyan]MODEL: {model_id}[/]", style="yellow")
            
            # ── 1. 结构化打印 Prompt ──
            if hasattr(prompt, "__iter__") and not isinstance(prompt, str):
                for i, msg in enumerate(prompt):
                    msg_type = type(msg).__name__.replace("Message", "")
                    color = "magenta" if msg_type == "System" else "green" if msg_type == "Human" else "cyan"
                    content = getattr(msg, "content", str(msg))
                    
                    # 针对 SQL 自动高亮
                    if isinstance(content, str) and ("SELECT" in content.upper() or "INSERT" in content.upper()):
                        display = Syntax(content, "sql", theme="monokai", word_wrap=True)
                    elif isinstance(content, str) and content.startswith("#"):
                        from rich.markdown import Markdown
                        display = Markdown(content)
                    else:
                        display = str(content)

                    console.print(Panel(
                        display,
                        title=f"[{color}]Msg-{i+1} | {msg_type}[/]",
                        border_style=color,
                        padding=(0, 1)
                    ))
            else:
                console.print(Panel(prompt_str, title="[dim]Raw Prompt[/]", border_style="dim"))

            # ── 2. 结构化打印 Response ──
            if resp_text:
                # 针对 JSON 或报告格式进行美化处理
                if resp_text.strip().startswith("{"):
                    try:
                        formatted_json = json.dumps(json.loads(resp_text), indent=2, ensure_ascii=False)
                        display_resp = Syntax(formatted_json, "json", theme="monokai")
                    except: display_resp = resp_text
                else:
                    display_resp = resp_text

                console.print(Panel(
                    display_resp, 
                    title="[bold yellow]RESPONSE (full)[/]", 
                    border_style="yellow",
                    padding=(0, 1)
                ))

            # ── 3. Token 统计 Table ──
            in_t  = usage_tracker._estimate_tokens(prompt_str)
            out_t = usage_tracker._estimate_tokens(resp_text)
            p_in  = PREDICTED.get(role, {}).get("in", "?")
            p_out = PREDICTED.get(role, {}).get("out", "?")
            
            table = Table(title="[bold]Token Consumption Metrics[/]", box=None, show_header=True, header_style="bold blue")
            table.add_column("Type", style="cyan")
            table.add_column("Actual", justify="right", style="green")
            table.add_column("Predicted", justify="right", style="dim")
            table.add_row("Input (Prompt)", str(in_t), str(p_in))
            table.add_row("Output (Gen)", str(out_t), str(p_out))
            console.print(table)
            console.rule(style="dim")

            cid = ref._current or "_"
            if cid not in ref.case_stats:
                ref.case_stats[cid] = {}
            s = ref.case_stats[cid]
            if role not in s:
                s[role] = {"in": 0, "out": 0, "calls": 0}
            s[role]["in"]    += in_t
            s[role]["out"]   += out_t
            s[role]["calls"] += 1

            sys.stdout.flush()
            ref._original_fn(role, response, model_id, prompt)

        ag._record_usage_with_budget = intercepted

    def total(self, cid):
        return sum(v["in"] + v["out"] for v in self.case_stats.get(cid, {}).values())

tracker = PhysicalTokenTracker()
tracker.patch()

# ── Run One Case ──────────────────────────────────────────────────────
async def run_one(case: dict, judge_llm) -> dict:
    cid, prompt, pred = case["id"], case["prompt"], case["pred_tokens"]

    print(f"\n{SEP}")
    print(f"  START CASE [{cid}]  {case['tag']}  diff:{case['diff']}")
    print(f"  QUESTION: {prompt}")
    print(f"  PREDICTED TOKENS: {pred:,}")
    print(SEP)

    tracker.set_case(cid)
    t0 = time.time()
    report_text = "(no report)"
    agent_ok    = False

    try:
        inputs = {"messages": [("user", prompt)],
                  "session_id": f"BENCH_{cid}_{int(t0)}"}
        state    = await workflow.ainvoke(inputs, config={
            "recursion_limit": 15,
            "callbacks": [VERBOSE_CB],
        })

        agent_ok = True
        msgs = state.get("messages", [])
        if msgs:
            last = msgs[-1]
            report_text = last[1] if isinstance(last, tuple) else getattr(last, "content", str(last))
    except Exception as ex:
        report_text = f"(Agent error: {ex})"
        logger.error(f"[{cid}] Agent error: {ex}")

    agent_t = time.time() - t0

    # ── 打印最终报告 ─────────────────────────────────────────────────
    print_block(f"FINAL REPORT from Agent [{cid}]", report_text, sep=SEP)

    # ── Judge ──────────────────────────────────────────────────────
    judge_input = f"{JUDGE_PROMPT}\n\nAudit Task: {prompt}\n\nGenerated Report:\n{report_text[:4000]}"

    print(f"\n{SEP3}")
    print(f"  JUDGE PHASE - [{cid}]")
    print(SEP3)

    # 打印 Judge 的完整输入
    print_block("JUDGE PROMPT (full input to Judge LLM)", judge_input, sep=SEP2)

    tj0      = time.time()
    eval_res = {"total": "N/A", "scores": {}, "advice": "parse error"}

    try:
        # [V73.1] 修复 BUG：必须 await 异步函数才能解包
        judge_llm, j_model = await model_manager.get_llm_by_role("planner_heavy")
        res     = await judge_llm.ainvoke(judge_input)
        content = str(res.content)

        # 打印 Judge 原始输出
        print_block("JUDGE RAW RESPONSE", content, sep=SEP2)

        # 解析 JSON
        js = content
        if "```json" in content:
            js = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            js = content.split("```")[1].split("```")[0]
        else:
            s, e = content.find("{"), content.rfind("}")
            if s != -1 and e != -1:
                js = content[s:e+1]
        
        # [V55.0] 健壮 JSON 解析：LLM 常在 advice 字段内输出未转义的双引号
        try:
            eval_res = json.loads(js.strip())
        except json.JSONDecodeError:
            # 尝试修复：提取 scores 和 total，advice 用正则单独抓
            import re as _re
            scores_match = _re.search(r'"scores"\s*:\s*(\{[^}]+\})', js)
            total_match  = _re.search(r'"total"\s*:\s*(\d+)', js)
            advice_match = _re.search(r'"advice"\s*:\s*"(.+)"?\s*\}$', js, _re.DOTALL)
            if scores_match and total_match:
                scores_data = json.loads(scores_match.group(1))
                total_val   = int(total_match.group(1))
                advice_text = advice_match.group(1).replace('"', "'") if advice_match else "parse recovered"
                eval_res = {"scores": scores_data, "total": total_val, "advice": advice_text}
                logger.info(f"[{cid}] Judge JSON recovered: total={total_val}")
            else:
                raise

        j_in  = usage_tracker._estimate_tokens(judge_input)
        j_out = usage_tracker._estimate_tokens(content)
        tracker.case_stats[cid]["judge"] = {"in": j_in, "out": j_out, "calls": 1}
        print(f"\n  [JUDGE TOKEN] in:{j_in}(pred:{PREDICTED['judge']['in']}) "
              f"out:{j_out}(pred:{PREDICTED['judge']['out']})")
    except Exception as ex:
        logger.error(f"[{cid}] Judge parse error: {ex}")

    judge_t = time.time() - tj0
    actual  = tracker.total(cid)
    dev_pct = (actual - pred) / pred * 100

    # ── Case Score Summary ──────────────────────────────────────────
    sc   = eval_res.get("scores", {})
    dims = ["success","recall","precision","faithfulness","relevance","professionalism","interpretability"]

    print(f"\n{SEP}")
    print(f"  CASE RESULT SUMMARY [{cid}]")
    print(SEP)
    labels = ["Success","Recall ","Precision","Faithful","Relevance","Profess.","Interpret"]
    for lab, dim in zip(labels, dims):
        v   = sc.get(dim, 0)
        bar = "#" * int(v) + "-" * (10 - int(v))
        print(f"  {lab:<10}: [{bar}] {v}/10")
    print(f"  {'-'*52}")
    print(f"  Total      : {eval_res.get('total','N/A')} / 70")
    print(f"  Advice     : {str(eval_res.get('advice',''))[:250]}")
    print(f"  Tokens     : predicted={pred:,}  actual={actual:,}  deviation={dev_pct:+.1f}%")
    print(f"  Time       : agent={agent_t:.1f}s  judge={judge_t:.1f}s")
    print(SEP)
    sys.stdout.flush()

    return {
        "id": cid, "tag": case["tag"], "diff": case["diff"],
        "agent_ok": agent_ok, "scores": sc,
        "total_score": eval_res.get("total", "N/A"),
        "advice": eval_res.get("advice", ""),
        "predicted": pred, "actual": actual, "deviation_pct": dev_pct,
        "agent_t": agent_t, "judge_t": judge_t,
        "roles": tracker.case_stats.get(cid, {}),
    }

# ── Summary ───────────────────────────────────────────────────────────
def print_summary(results: list):
    dims   = ["success","recall","precision","faithfulness","relevance","professionalism","interpretability"]
    dim_zh = ["Success","Recall","Precision","Faithful","Relevance","Profess.","Interpret"]
    n_ok   = sum(1 for r in results if r["agent_ok"])

    console.print("\n")
    console.print(Panel.fit(
        f"[bold blue]HSA 7-DIMENSION BENCHMARK FINAL SUMMARY[/]\n[cyan]Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}[/]",
        border_style="blue"
    ))

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Case", width=8)
    table.add_column("Tag", width=20)
    table.add_column("Diff", width=6)
    for zh in dim_zh:
        table.add_column(zh, justify="right")
    table.add_column("Total", justify="right", style="bold yellow")
    table.add_column("Actual/Pred", justify="right", no_wrap=True, width=18)

    tot_pre = tot_act = 0
    dim_sum = {d: 0 for d in dims}

    for r in results:
        sc  = r["scores"]
        row_data = [r["id"], r["tag"], r["diff"]]
        
        for d in dims:
            val = sc.get(d, 0)
            color = "green" if val >= 7 else "yellow" if val >= 5 else "red"
            row_data.append(f"[{color}]{val}[/]")
            
        total = r["total_score"]
        total_color = "bright_green" if (isinstance(total, int) and total >= 50) else "white"
        row_data.append(f"[{total_color}]{total}[/]")
        
        tok_ratio = r['actual'] / r['predicted']
        tok_color = "red" if tok_ratio > 1.2 else "green"
        row_data.append(f"[{tok_color}]{r['actual']:,}[/]/{r['predicted']:,}")
        
        table.add_row(*[str(x) for x in row_data])
        
        tot_pre += r["predicted"]
        tot_act += r["actual"]
        for d in dims:
            dim_sum[d] += sc.get(d, 0)

    console.print(table)

    # 汇总统计
    n = max(len(results), 1)
    console.print(f"\n[bold]Agent Success: [green]{n_ok}[/] / {len(results)}[/]")
    
    # 维度平均分图表
    console.print("\n[bold]Dimension Averages:[/]")
    for d, zh in zip(dims, dim_zh):
        avg_v = dim_sum[d] / n
        bar_len = int(avg_v * 2)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        color = "green" if avg_v >= 7 else "yellow" if avg_v >= 5 else "red"
        console.print(f"  {zh:<14}: [{color}]{bar}[/] {avg_v:>4.1f}/10")

    # 改进建议
    console.print("\n[bold yellow]Improvement Suggestions:[/]")
    for r in results:
        if r.get("advice"):
            console.print(f"  • [bold]{r['id']}[/]: {r['advice']}")

    console.print("\n" + "="*72 + "\n")

# ── Main ──────────────────────────────────────────────────────────────
async def main():
    print(f"\n{SEP}")
    print(f"  HSA Medical Audit Agent - 7-Dimension Benchmark [VERBOSE]")
    print(f"  Time  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Cases : {len(TEST_CASES)}")
    print(f"  Est.  : {sum(c['pred_tokens'] for c in TEST_CASES):,} tokens")
    print(f"  NOTE  : Full Prompt + Response printed for every node call")
    print(SEP)

    # [V73.0] 裁判模型已移至 run_one 内部动态获取，实现故障秒切
    print(f"  [OK] Judge Strategy: Dynamic Failover Enabled\n")

    # [V74.1] 物理持久化：不再启动时清空黑名单，确保坏掉的模型（如 V3）被持久锁定。
    logger.info("🛡️ [算力治理] 启动时保留历史黑名单状态，防止报废模型复活。")

    # [V174.0] 企业级多 Case 稳定性补强：启动时强制重置黑名单
    from app.usage_tracker import usage_tracker
    usage_tracker.reset_blacklists()
    logger.info("✅ [算力治理] 已强制重置模型黑名单，确保 Benchmark 链路满血启动。")

    # [V75.0] 企业级观测激活：确保 Benchmark 过程被全量追踪
    init_observability()
    
    # 注册退出钩子以确保 Trace 数据完整性
    import atexit
    atexit.register(shutdown_observability)

    results = []
    for case in TEST_CASES:
        r = await run_one(case, None) # judge_llm 内部动态生成
        results.append(r)
        await asyncio.sleep(2)

    print_summary(results)

    ts   = datetime.now().strftime("%Y%m%d_%H%M")
    path = f"data/bench_7dim_verbose_{ts}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"  [File] Report saved: {path}")

if __name__ == "__main__":
    asyncio.run(main())
