"""
tests/eval/gaia
===============
GAIA (General AI Assistants) 基准评测接入。

组件:
- dataset.GAIADataset      加载本地或 HuggingFace (`gaia-benchmark/GAIA`) 数据集
- scorer.quasi_exact_match 准精确匹配 (Quasi Exact Match) 与 FINAL ANSWER 提取
- agent.ArgusGAIAAgent     通过 Argus 模型工厂 (`model_manager`) 执行推理
- evaluator.GAIAEvaluator  分级准确率、难度递进下降率、JSONL 导出与 Markdown 报告
"""

from tests.eval.gaia.agent import GAIA_SYSTEM_PROMPT, ArgusGAIAAgent
from tests.eval.gaia.dataset import GAIADataset, GAIASample
from tests.eval.gaia.evaluator import GAIAEvaluator, GAIAReport
from tests.eval.gaia.scorer import extract_final_answer, normalize_answer, quasi_exact_match

__all__ = [
    "ArgusGAIAAgent",
    "GAIA_SYSTEM_PROMPT",
    "GAIADataset",
    "GAIAEvaluator",
    "GAIAReport",
    "GAIASample",
    "extract_final_answer",
    "normalize_answer",
    "quasi_exact_match",
]
