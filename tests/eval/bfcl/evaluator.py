"""
BFCL 评估编排器：运行评测、统计指标、导出官方 JSONL 格式、生成 Markdown 报告。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from tests.eval.bfcl.agent import AgentCallResult, ArgusFCAgent
from tests.eval.bfcl.checker import check_sample
from tests.eval.bfcl.dataset import BFCLDataset, BFCLSample


@dataclass
class SampleEvalRecord:
    id: str
    category: str
    question: str
    predicted_calls: List[Dict[str, Any]]
    ground_truth: Optional[List[Dict[str, Any]]]
    is_correct: bool
    reason: str
    latency_ms: float
    raw_content: str = ""
    error: Optional[str] = None


@dataclass
class BFCLReport:
    model_id: str
    categories: List[str]
    records: List[SampleEvalRecord] = field(default_factory=list)
    category_stats: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    overall_accuracy: float = 0.0
    correct_samples: int = 0
    total_samples: int = 0
    avg_latency_ms: float = 0.0
    error_count: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "categories": self.categories,
            "overall_accuracy": self.overall_accuracy,
            "correct_samples": self.correct_samples,
            "total_samples": self.total_samples,
            "avg_latency_ms": self.avg_latency_ms,
            "error_count": self.error_count,
            "category_stats": self.category_stats,
            "timestamp": self.timestamp,
        }


def _extract_question_text(sample: BFCLSample) -> str:
    for msg in sample.first_turn_messages:
        if msg.get("role") == "user":
            return msg.get("content", "")
    return str(sample.first_turn_messages)


def _format_official_result(predicted_calls: List[Dict[str, Any]]) -> Any:
    """
    转为 BFCL 官方 result JSONL 字段格式:
    [{func_name: json_str_or_dict}, ...]
    """
    return [{c["name"]: json.dumps(c.get("arguments") or {}, ensure_ascii=False)} for c in predicted_calls]


class BFCLEvaluator:
    """BFCL 评估执行器。"""

    def __init__(
        self,
        agent: ArgusFCAgent,
        bfcl_data_dir: Optional[str] = None,
        concurrency: int = 1,
    ):
        self.agent = agent
        self.bfcl_data_dir = bfcl_data_dir
        self.concurrency = max(1, concurrency)

    async def _eval_one(self, sample: BFCLSample, sem: asyncio.Semaphore) -> SampleEvalRecord:
        async with sem:
            res: AgentCallResult = await self.agent.predict(sample)

        if res.error:
            is_ok, reason = False, f"调用失败: {res.error}"
        else:
            is_ok, reason = check_sample(res.tool_calls, sample.ground_truth, sample.category)

        return SampleEvalRecord(
            id=sample.id,
            category=sample.category,
            question=_extract_question_text(sample),
            predicted_calls=res.tool_calls,
            ground_truth=sample.ground_truth,
            is_correct=is_ok,
            reason=reason,
            latency_ms=res.latency_ms,
            raw_content=res.raw_content,
            error=res.error,
        )

    async def evaluate_async(
        self,
        categories: Sequence[str] = ("simple_python",),
        max_samples: int = 5,
    ) -> BFCLReport:
        sem = asyncio.Semaphore(self.concurrency)
        all_records: List[SampleEvalRecord] = []
        cat_stats: Dict[str, Dict[str, Any]] = {}

        for cat in categories:
            dataset = BFCLDataset(category=cat, bfcl_data_dir=self.bfcl_data_dir)
            samples = dataset.load(max_samples=max_samples)
            cat_records = await asyncio.gather(*(self._eval_one(s, sem) for s in samples))
            all_records.extend(cat_records)

            cat_total = len(cat_records)
            cat_correct = sum(1 for r in cat_records if r.is_correct)
            cat_stats[cat] = {
                "total": cat_total,
                "correct": cat_correct,
                "accuracy": (cat_correct / cat_total) if cat_total else 0.0,
            }

        total = len(all_records)
        correct = sum(1 for r in all_records if r.is_correct)
        avg_lat = (sum(r.latency_ms for r in all_records) / total) if total else 0.0
        err_cnt = sum(1 for r in all_records if r.error is not None)

        return BFCLReport(
            model_id=self.agent.model_id,
            categories=list(categories),
            records=all_records,
            category_stats=cat_stats,
            overall_accuracy=(correct / total) if total else 0.0,
            correct_samples=correct,
            total_samples=total,
            avg_latency_ms=avg_lat,
            error_count=err_cnt,
        )

    def evaluate(
        self,
        categories: Sequence[str] = ("simple_python",),
        max_samples: int = 5,
    ) -> BFCLReport:
        return asyncio.run(self.evaluate_async(categories=categories, max_samples=max_samples))

    @staticmethod
    def export_to_bfcl_format(
        report: BFCLReport,
        output_dir: str | Path = "artifacts/bfcl_results",
        bfcl_model_name: Optional[str] = None,
    ) -> Dict[str, Path]:
        """
        按 BFCL 官方目录结构导出 JSONL:
        <output_dir>/<sanitized_model_name>/BFCL_v4_<category>_result.json
        """
        model_folder = (bfcl_model_name or report.model_id).replace("/", "_")
        target_dir = Path(output_dir) / model_folder
        target_dir.mkdir(parents=True, exist_ok=True)

        by_cat: Dict[str, List[SampleEvalRecord]] = {}
        for rec in report.records:
            by_cat.setdefault(rec.category, []).append(rec)

        written: Dict[str, Path] = {}
        for cat, recs in by_cat.items():
            out_file = target_dir / f"BFCL_v4_{cat}_result.json"
            with out_file.open("w", encoding="utf-8") as f:
                for rec in recs:
                    row = {
                        "id": rec.id,
                        "result": _format_official_result(rec.predicted_calls),
                        "input_token_count": 0,
                        "output_token_count": 0,
                        "latency": round(rec.latency_ms / 1000.0, 4),
                    }
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            written[cat] = out_file
        return written

    @staticmethod
    def generate_markdown_report(
        report: BFCLReport,
        output_path: Optional[str | Path] = None,
        official_summary: Optional[str] = None,
    ) -> Path:
        if output_path is None:
            out = Path("artifacts/bfcl_reports") / f"bfcl_report_{report.timestamp}.md"
        else:
            out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        bar_len = 40
        filled = int(round(report.overall_accuracy * bar_len))
        bar = "█" * filled + "░" * (bar_len - filled)

        lines = [
            "# Argus BFCL 工具调用评估报告",
            "",
            f"- **评估时间**: {report.timestamp}",
            f"- **Argus 模型配置**: `{report.model_id}`",
            f"- **评估类别**: {', '.join(f'`{c}`' for c in report.categories)}",
            f"- **总体准确率**: **{report.overall_accuracy:.2%}** ({report.correct_samples}/{report.total_samples})",
            f"- **平均延迟**: {report.avg_latency_ms:.1f} ms",
            f"- **异常/错误数**: {report.error_count}",
            "",
            f"准确率: `{bar}` {report.overall_accuracy:.2%}",
            "",
            "## 分类统计",
            "",
            "| 类别 | 正确数 | 总数 | 准确率 |",
            "|------|--------|------|--------|",
        ]
        for cat, st in report.category_stats.items():
            lines.append(f"| `{cat}` | {st['correct']} | {st['total']} | {st['accuracy']:.2%} |")

        if official_summary:
            lines.extend(["", "## BFCL 官方评估工具复核", "", "```text", official_summary.strip(), "```"])

        lines.extend([
            "",
            "## 样本详情",
            "",
            "| 样本 ID | 类别 | 结果 | 耗时(ms) | 说明 |",
            "|---------|------|------|----------|------|",
        ])
        for rec in report.records:
            status = "✅" if rec.is_correct else "❌"
            reason = rec.reason.replace("|", "\\|").replace("\n", " ")[:120]
            lines.append(
                f"| `{rec.id}` | `{rec.category}` | {status} | {rec.latency_ms:.0f} | {reason} |"
            )

        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out
