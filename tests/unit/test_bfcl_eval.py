"""
tests/unit/test_bfcl_eval.py
============================
BFCL 接入模块的离线单元测试 (不消耗真实 LLM Token)。
"""

import json
from pathlib import Path
from typing import Any, List, Optional

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ConfigDict

from tests.eval.bfcl.agent import ArgusFCAgent
from tests.eval.bfcl.checker import check_sample
from tests.eval.bfcl.dataset import BFCLDataset
from tests.eval.bfcl.evaluator import BFCLEvaluator
from tests.eval.bfcl.schema import to_openai_tools


class _MockToolChatModel(BaseChatModel):
    """按调用顺序返回预设 tool_calls 的 Mock ChatModel。"""

    planned_calls: List[List[dict]] = []
    idx: int = 0
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def _llm_type(self) -> str:
        return "mock-fc"

    def bind_tools(self, tools, **kwargs):
        return self.bind(tools=tools, **kwargs)

    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs) -> ChatResult:
        calls = self.planned_calls[self.idx] if self.idx < len(self.planned_calls) else []
        self.idx += 1
        msg = AIMessage(content="" if calls else "No tool needed.", tool_calls=calls)
        return ChatResult(generations=[ChatGeneration(message=msg)])

    async def _agenerate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs) -> ChatResult:
        return self._generate(messages, stop=stop, **kwargs)


def test_schema_conversion_and_dotted_name_mapping():
    funcs = [
        {
            "name": "math.triangle_area",
            "description": "Calculate triangle area.",
            "parameters": {
                "type": "dict",
                "properties": {
                    "base": {"type": "float", "description": "base"},
                    "tags": {"type": "tuple"},
                },
                "required": ["base"],
            },
        }
    ]
    tools, name_map = to_openai_tools(funcs)
    assert len(tools) == 1
    fn = tools[0]["function"]
    assert fn["name"] == "math_triangle_area"
    assert name_map["math_triangle_area"] == "math.triangle_area"
    assert fn["parameters"]["type"] == "object"
    assert fn["parameters"]["properties"]["base"]["type"] == "number"
    assert fn["parameters"]["properties"]["tags"]["type"] == "array"
    assert "items" in fn["parameters"]["properties"]["tags"]


def test_checker_handles_optional_args_case_and_parallel():
    gt = [{"calc_area": {"base": [10], "height": [5.0], "unit": ["", "cm"]}}]
    ok, _ = check_sample([{"name": "calc_area", "arguments": {"height": 5, "base": 10}}], gt, "simple_python")
    assert ok

    # 多余参数应判错
    ok_extra, reason = check_sample(
        [{"name": "calc_area", "arguments": {"base": 10, "height": 5, "extra": 1}}],
        gt,
        "simple_python",
    )
    assert not ok_extra and "多余参数" in reason

    # parallel 无序匹配
    gt_parallel = [
        {"get_weather": {"city": ["New York", "NY"]}},
        {"get_weather": {"city": ["Boston"]}},
    ]
    ok_par, _ = check_sample(
        [
            {"name": "get_weather", "arguments": {"city": "boston"}},
            {"name": "get_weather", "arguments": {"city": "ny"}},
        ],
        gt_parallel,
        "parallel",
    )
    assert ok_par

    # irrelevance
    ok_irr, _ = check_sample([], None, "irrelevance")
    assert ok_irr
    bad_irr, _ = check_sample([{"name": "get_weather", "arguments": {"city": "NY"}}], None, "irrelevance")
    assert not bad_irr


def test_dataset_evaluator_export_and_report(tmp_path: Path):
    data_dir = tmp_path / "bfcl_data"
    gt_dir = data_dir / "possible_answer"
    gt_dir.mkdir(parents=True)

    test_rows = [
        {
            "id": "simple_python_0",
            "question": [[{"role": "user", "content": "Area of triangle base 10 height 5"}]],
            "function": [
                {
                    "name": "math.triangle_area",
                    "description": "area",
                    "parameters": {
                        "type": "dict",
                        "properties": {"base": {"type": "integer"}, "height": {"type": "integer"}},
                        "required": ["base", "height"],
                    },
                }
            ],
        },
        {
            "id": "simple_python_1",
            "question": [[{"role": "user", "content": "Factorial of 5"}]],
            "function": [
                {
                    "name": "factorial",
                    "description": "fact",
                    "parameters": {"type": "dict", "properties": {"n": {"type": "integer"}}, "required": ["n"]},
                }
            ],
        },
    ]
    gt_rows = [
        {"id": "simple_python_0", "ground_truth": [{"math.triangle_area": {"base": [10], "height": [5]}}]},
        {"id": "simple_python_1", "ground_truth": [{"factorial": {"n": [5]}}]},
    ]
    (data_dir / "BFCL_v4_simple_python.json").write_text(
        "\n".join(json.dumps(r) for r in test_rows), encoding="utf-8"
    )
    (gt_dir / "BFCL_v4_simple_python.json").write_text(
        "\n".join(json.dumps(r) for r in gt_rows), encoding="utf-8"
    )

    ds = BFCLDataset(category="simple_python", bfcl_data_dir=str(data_dir))
    assert len(ds.load()) == 2

    mock_llm = _MockToolChatModel(
        planned_calls=[
            [{"name": "math_triangle_area", "args": {"base": 10, "height": 5}, "id": "c1"}],
            [{"name": "factorial", "args": {"n": 99}, "id": "c2"}],  # 故意错一个
        ]
    )
    agent = ArgusFCAgent(model_id="mock-model", llm=mock_llm)
    evaluator = BFCLEvaluator(agent=agent, bfcl_data_dir=str(data_dir), concurrency=1)
    report = evaluator.evaluate(categories=["simple_python"], max_samples=5)

    assert report.total_samples == 2
    assert report.correct_samples == 1
    assert report.overall_accuracy == pytest.approx(0.5)

    exported = evaluator.export_to_bfcl_format(report, output_dir=tmp_path / "out", bfcl_model_name="Test/Model")
    out_file = exported["simple_python"]
    assert out_file.exists()
    lines = [json.loads(line) for line in out_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines[0]["id"] == "simple_python_0"
    assert "math.triangle_area" in lines[0]["result"][0]

    md_path = evaluator.generate_markdown_report(report, output_path=tmp_path / "report.md")
    assert md_path.exists()
    md_text = md_path.read_text(encoding="utf-8")
    assert "50.00%" in md_text
    assert "simple_python_0" in md_text
