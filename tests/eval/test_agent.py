import os
import json
import time
import datetime
import pytest
from deepeval import assert_test
from deepeval.test_case import LLMTestCase
from tests.eval.metrics import get_hsa_evidence_chain_metric, NumericalPrecisionMetric as HSANumericalPrecisionMetric
from dotenv import load_dotenv

# 确保在运行前正确加载环境
os.environ["CLICKHOUSE_DB"] = "hsa_sandbox"
load_dotenv(override=True)

from app.core.agent_graph import get_graph_executor as get_executor
from app.core.registry.prompt_registry import prompt_registry
from app.core.registry.rule_registry import rule_registry


# ──────────────────────────────────────────────────────────────
# [V90.0] Prompt 版本追踪: 每次评测开始时拍下所有 prompt 的 content_hash,
# 写入 artifacts/eval_runs/{timestamp}.json, 这样可以回溯
# "某次评测得分下降是哪些 prompt 改动导致的"
# ──────────────────────────────────────────────────────────────

_RUN_TIMESTAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
_EVAL_ARTIFACTS_DIR = os.path.join("artifacts", "eval_runs")
os.makedirs(_EVAL_ARTIFACTS_DIR, exist_ok=True)


def _snapshot_registries() -> dict:
    """采集本次评测使用的所有可版本化资产的快照。"""
    return {
        "timestamp": _RUN_TIMESTAMP,
        "prompts": {
            pid: prompt_registry.get_version_info(pid)
            for pid in prompt_registry.list_prompts()
        },
        "sql_templates": rule_registry.sql_templates.list_rules(),
        "routing_rules_count": len(rule_registry.routing_rules.get_rules()),
    }


_REGISTRY_SNAPSHOT = _snapshot_registries()
with open(os.path.join(_EVAL_ARTIFACTS_DIR, f"{_RUN_TIMESTAMP}_registry.json"), "w", encoding="utf-8") as f:
    json.dump(_REGISTRY_SNAPSHOT, f, indent=2, ensure_ascii=False)


def _load_suite(suite: str) -> list:
    """按 suite 加载数据集。空列表则 parametrize 为空, pytest 自动 skip。"""
    if suite == "basic":
        path = "tests/eval/golden_dataset.json"
    else:
        path = f"tests/eval/golden_dataset_{suite}.json"
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _persist_case_result(item: dict, final_output: str, elapsed: float, extra: dict = None):
    """将每个 case 的输出 + 注册表快照写盘, 供事后比对。"""
    record = {
        "registry_snapshot": _REGISTRY_SNAPSHOT,
        "input": item.get("input"),
        "expected_output": item.get("expected_output"),
        "actual_output": final_output,
        "elapsed_seconds": elapsed,
        "suite": item.get("suite", "basic"),
        "assertion_type": item.get("assertion_type", "llm_judge"),
    }
    if extra:
        record.update(extra)
    case_id = (item.get("context") or "case").replace("/", "_")[:60]
    out_path = os.path.join(_EVAL_ARTIFACTS_DIR, f"{_RUN_TIMESTAMP}_{case_id}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)


# ──────────────────────────────────────────────────────────────
# 共用 Agent 执行器 (所有 suite 共享, 避免重复编译图)
# ──────────────────────────────────────────────────────────────

async def _run_agent(input_text: str) -> tuple[str, dict, float]:
    """运行一次 Agent, 返回 (最终输出文本, state, 耗时秒数)。"""
    app, _ = get_executor()
    inputs = {
        "messages": [("user", input_text)],
        "session_id": "test_regression",
        "retry_count": 0,
    }
    config = {"configurable": {"thread_id": "test_thread"}}
    t0 = time.time()
    state = await app.ainvoke(inputs, config=config)
    elapsed = time.time() - t0
    final_output = state["messages"][-1].content if state.get("messages") else ""
    return final_output, state, elapsed


# ──────────────────────────────────────────────────────────────
# 轻量断言: 不烧 LLM token, 适合 CI 大批量回归
# ──────────────────────────────────────────────────────────────

def _assert_keyword_any(final_output: str, expected_keywords: list) -> None:
    """任一关键词命中即通过 (用于模糊意图 / refusal 检查)。"""
    hit = [kw for kw in expected_keywords if kw in final_output]
    assert hit, (
        f"None of expected keywords {expected_keywords} found in output.\n"
        f"Output (first 300 chars): {final_output[:300]}"
    )


def _assert_sql_template_used(state: dict, expected_template_ids: list) -> None:
    """断言 state 中的 sql_query 引用了期望的 SQL 模板之一。
    
    我们通过 SQL 模板中独特的字段/子句特征做字符串匹配, 而不依赖 LLM。
    """
    from app.core.registry.rule_registry import rule_registry

    sql_query = (state.get("sql_query") or "").lower()
    methodology = (state.get("methodology") or "").lower()
    # 从报告中也看一眼, 因为 rule_engine 会把模板名写进 methodology
    text_corpus = sql_query + "\n" + methodology

    matched = []
    for tpl_id in expected_template_ids:
        tpl = rule_registry.sql_templates.get_rule(tpl_id)
        if not tpl:
            continue
        # 匹配策略: 模板 ID、方法论关键词、SQL 中的独特列/表组合
        signals = [tpl_id.lower(), tpl.methodology.lower()[:30] if tpl.methodology else ""]
        signals = [s for s in signals if s]
        if any(s in text_corpus for s in signals):
            matched.append(tpl_id)

    assert matched, (
        f"Expected one of SQL templates {expected_template_ids} to be used, "
        f"but none were matched in sql_query or methodology.\n"
        f"sql_query (first 200): {sql_query[:200]}\n"
        f"methodology (first 200): {methodology[:200]}"
    )


# ──────────────────────────────────────────────────────────────
# Suite: basic (原 5 个用例, LLM-as-judge, token 消耗最高)
# ──────────────────────────────────────────────────────────────

@pytest.mark.basic
@pytest.mark.asyncio
@pytest.mark.parametrize("item", _load_suite("basic"))
async def test_medical_agent_basic(item):
    """基础患者行为分析 — 证据链 + 数值精度 (LLM-as-judge)。"""
    final_output, _, elapsed = await _run_agent(item["input"])
    _persist_case_result(item, final_output, elapsed)

    evidence_chain_metric = get_hsa_evidence_chain_metric()
    precision_metric = HSANumericalPrecisionMetric()
    test_case = LLMTestCase(
        input=item["input"],
        actual_output=final_output,
        expected_output=item.get("expected_output"),
        context=[item.get("context")],
    )
    assert_test(test_case, [evidence_chain_metric, precision_metric])


# Note: 旧的 test_medical_agent 别名已移除 (会导致 pytest 双重收集 basic suite)。
# 如果外部 CI 引用了该名字, 请改为 test_medical_agent_basic。


# ──────────────────────────────────────────────────────────────
# Suite: fuzzy (模糊意图路由, 不烧 LLM)
# ──────────────────────────────────────────────────────────────

@pytest.mark.fuzzy
@pytest.mark.asyncio
@pytest.mark.parametrize("item", _load_suite("fuzzy"))
async def test_medical_agent_fuzzy(item):
    """模糊意图 → SQL 模板路由准确性。"""
    final_output, state, elapsed = await _run_agent(item["input"])
    _persist_case_result(
        item, final_output, elapsed,
        extra={"sql_query": state.get("sql_query", ""), "methodology": state.get("methodology", "")},
    )

    atype = item.get("assertion_type", "keyword_any")
    if atype == "sql_template_used":
        _assert_sql_template_used(state, item["expected_template_ids"])
    elif atype == "keyword_any":
        _assert_keyword_any(final_output, item["expected_keywords"])
    else:
        pytest.fail(f"Unsupported assertion_type for fuzzy suite: {atype}")


# ──────────────────────────────────────────────────────────────
# Suite: refusal (越权/注入拦截, 正则匹配, 近零 LLM 成本)
# ──────────────────────────────────────────────────────────────

@pytest.mark.refusal
@pytest.mark.asyncio
@pytest.mark.parametrize("item", _load_suite("refusal"))
async def test_medical_agent_refusal(item):
    """越权请求 → Agent 应拒绝或脱敏。"""
    final_output, state, elapsed = await _run_agent(item["input"])
    _persist_case_result(
        item, final_output, elapsed,
        extra={"error_log": state.get("error_log", "")},
    )

    atype = item.get("assertion_type", "refusal_expected")
    # refusal_expected 和 keyword_any 语义一致, 只是字段名不同以便日志可读
    _assert_keyword_any(final_output, item["expected_keywords"])


# ──────────────────────────────────────────────────────────────
# Suite: rules (SQL 模板直接激活, 验证规则引擎路由)
# ──────────────────────────────────────────────────────────────

@pytest.mark.rules
@pytest.mark.asyncio
@pytest.mark.parametrize("item", _load_suite("rules"))
async def test_medical_agent_rules(item):
    """直接指令 → 对应 SQL 模板必须被选中。"""
    final_output, state, elapsed = await _run_agent(item["input"])
    _persist_case_result(
        item, final_output, elapsed,
        extra={"sql_query": state.get("sql_query", ""), "methodology": state.get("methodology", "")},
    )
    _assert_sql_template_used(state, item["expected_template_ids"])
