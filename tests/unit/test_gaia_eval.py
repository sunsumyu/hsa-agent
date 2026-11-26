"""
tests/unit/test_gaia_eval.py
============================
GAIA 接入模块的离线单元测试 (不依赖 HF_TOKEN 或真实 LLM Token)。
"""

import json
from pathlib import Path
from typing import List, Optional

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import ConfigDict

from tests.eval.gaia.agent import ArgusGAIAAgent
from tests.eval.gaia.dataset import GAIADataset
from tests.eval.gaia.evaluator import GAIAEvaluator
from tests.eval.gaia.scorer import extract_final_answer, normalize_answer, quasi_exact_match


class _MockGAIAChatModel(BaseChatModel):
    responses: List[str] = []
    idx: int = 0
    model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def _llm_type(self) -> str:
        return "mock-gaia"

    def _generate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs) -> ChatResult:
        text = self.responses[self.idx] if self.idx < len(self.responses) else ""
        self.idx += 1
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])

    async def _agenerate(self, messages: List[BaseMessage], stop: Optional[List[str]] = None, **kwargs) -> ChatResult:
        return self._generate(messages, stop=stop, **kwargs)


def test_scorer_extract_and_normalize():
    raw = "Let me think step by step.\nFINAL ANSWER: [$1,234.56]"
    assert extract_final_answer(raw) == "$1,234.56"
    assert normalize_answer("$1,234.56") == "1234.56"
    assert normalize_answer("1,000") == "1000"
    assert normalize_answer("The United States.") == "united states"
    assert normalize_answer("Paris, London, Berlin") == "berlin,london,paris"

    ok_num, _ = quasi_exact_match("$1,000", "1000")
    assert ok_num
    ok_pct, _ = quasi_exact_match("50%", "50")
    assert ok_pct
    ok_str, _ = quasi_exact_match("the apple.", "Apple")
    assert ok_str
    ok_list, _ = quasi_exact_match("Berlin, Paris, London", "Paris, London, Berlin")
    assert ok_list
    bad, _ = quasi_exact_match("17", "24000")
    assert not bad


def test_dataset_missing_raises_clear_error(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("HF_TOKEN", raising=False)
    ds = GAIADataset(split="validation", local_data_dir=tmp_path / "empty_gaia", token=None)
    with pytest.raises(FileNotFoundError, match="HF_TOKEN"):
        ds.load()


def _seed_gaia_validation_fixture(tmp_path: Path) -> Path:
    """Create temporary GAIA validation dataset fixture files."""
    val_dir = tmp_path / "gaia" / "2023" / "validation"
    val_dir.mkdir(parents=True)
    (val_dir / "note.txt").write_text("Population secret factor = 42", encoding="utf-8")

    rows = [
        {"task_id": "g1", "Question": "Read note.txt and give the factor.", "Level": 1, "Final answer": "42", "file_name": "note.txt", "Annotator Metadata": {"Number of steps": 1}},
        {"task_id": "g2", "Question": "Name the country.", "Level": 2, "Final answer": "United States", "file_name": "", "Annotator Metadata": {"Number of steps": 3}},
        {"task_id": "g3", "Question": "Another L2 question.", "Level": 2, "Final answer": "100", "file_name": "", "Annotator Metadata": {"Number of steps": 4}},
        {"task_id": "g4", "Question": "Hard L3 question.", "Level": 3, "Final answer": "alpha, beta", "file_name": "", "Annotator Metadata": {"Number of steps": 6}},
    ]
    (val_dir / "metadata.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return tmp_path / "gaia"


def _assert_gaia_exports(evaluator: GAIAEvaluator, report, tmp_path: Path) -> None:
    """Verify GAIA JSONL submission and Markdown report exports."""
    jsonl_out = evaluator.export_to_gaia_format(report, output_path=tmp_path / "out.jsonl")
    assert jsonl_out.exists()
    exported_rows = [json.loads(line) for line in jsonl_out.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(exported_rows) == 4
    assert exported_rows[0]["task_id"] == "g1"
    assert exported_rows[0]["model_answer"] == "42"

    md_out = evaluator.generate_markdown_report(report, output_path=tmp_path / "report.md")
    assert md_out.exists()
    md_text = md_out.read_text(encoding="utf-8")
    assert "50.00%" in md_text
    assert "Level 1 → Level 2" in md_text


def test_evaluator_level_metrics_drop_rate_and_exports(tmp_path: Path):
    """Verify GAIA evaluator level accuracy, drop rates, avg steps, and exports."""
    gaia_root = _seed_gaia_validation_fixture(tmp_path)
    stats = GAIADataset(split="validation", local_data_dir=gaia_root).get_statistics()
    assert stats["total_samples"] == 4
    assert stats["level_distribution"] == {1: 1, 2: 2, 3: 1}

    mock_llm = _MockGAIAChatModel(
        responses=[
            "Reasoning...\nFINAL ANSWER: 42",
            "FINAL ANSWER: The United States.",
            "FINAL ANSWER: 999",
            "FINAL ANSWER: wrong",
        ]
    )
    evaluator = GAIAEvaluator(agent=ArgusGAIAAgent(model_id="mock-gaia", llm=mock_llm), split="validation", local_data_dir=gaia_root, concurrency=1)
    report = evaluator.evaluate(max_samples=0)

    assert report.total_samples == 4
    assert report.exact_matches == 2
    assert report.exact_match_rate == pytest.approx(0.5)
    assert report.level_metrics[1]["accuracy"] == pytest.approx(1.0)
    assert report.level_metrics[2]["accuracy"] == pytest.approx(0.5)
    assert report.level_metrics[3]["accuracy"] == pytest.approx(0.0)
    assert report.drop_rates["1->2"] == pytest.approx(0.5)
    assert report.drop_rates["2->3"] == pytest.approx(1.0)
    assert report.avg_steps == pytest.approx(2.0)

    _assert_gaia_exports(evaluator, report, tmp_path)
