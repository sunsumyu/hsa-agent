"""
tests/eval/bfcl
===============
BFCL (Berkeley Function Calling Leaderboard) 评测接入。

评测对象：Argus 模型层 (app.infra.llm_factory) 构造出的 LLM 客户端，在原生
Function Calling (bind_tools) 下的工具调用能力。

组件:
- dataset.BFCLDataset      加载 BFCL v4 数据集 + possible_answer
- schema.to_openai_tools   BFCL 函数定义 -> OpenAI tools schema (含函数名映射)
- checker.check_sample     本地 AST 校验 (对齐官方 ast_checker 语义的轻量实现)
- agent.ArgusFCAgent       用 Argus 的模型工厂发起原生函数调用
- evaluator.BFCLEvaluator  评测编排 / 指标 / 导出官方格式 / Markdown 报告
- official.run_official_eval  调用隔离 venv 中的 `bfcl evaluate` 复核
"""

from tests.eval.bfcl.dataset import BFCLDataset, BFCLSample, SUPPORTED_CATEGORIES
from tests.eval.bfcl.checker import check_sample
from tests.eval.bfcl.schema import to_openai_tools

__all__ = ["BFCLDataset", "BFCLSample", "SUPPORTED_CATEGORIES", "check_sample", "to_openai_tools"]
