"""
GAIA 评估编排器：运行评测、计算分级准确率与难度递进下降率、导出官方 JSONL 与 Markdown 报告。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from tests.eval.gaia.agent import ArgusGAIAAgent, GAIAAgentResult
from tests.eval.gaia.dataset import GAIADataset, GAIASample
from tests.eval.gaia.scorer import quasi_exact_match


@dataclass
class GAIASampleRecord:
    task_id: str
    level: int
    question: str
    predicted_answer: str
    expected_answer: str
    exact_match: bool
    reason: str
    latency_ms: float
    reasoning_trace: str = ""
    num_steps: Optional[int] = None
    error: Optional[str] = None


@dataclass
class GAIAReport:
    model_id: str
    split: str
    level_filter: Optional[int]
    records: List[GAIASampleRecord] = field(default_factory=list)
    exact_match_rate: float = 0.0
    exact_matches: int = 0
    total_samples: int = 0
    level_metrics: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    drop_rates: Dict[str, Optional[float]] = field(default_factory=dict)
    avg_steps: Optional[float] = None
    avg_latency_ms: float = 0.0
    error_count: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y%m%d_%H%M%S"))


class GAIAEvaluator:
    """GAIA 评估执行器。"""

    def __init__(
        self,
        agent: ArgusGAIAAgent,
        split: str = "validation",
        level: Optional[int] = None,
        local_data_dir: Optional[str | Path] = None,
        token: Optional[str] = None,
        concurrency: int = 2,
    ):
        self.agent = agent
        self.split = split
        self.level = level
        self.local_data_dir = local_data_dir
        self.token = token
        self.concurrency = max(1, concurrency)

    async def _eval_one(self, sample: GAIASample, sem: asyncio.Semaphore) -> GAIASampleRecord:
        async with sem:
            res: GAIAAgentResult = await self.agent.predict(sample)

        if res.error:
            ok, reason = False, f"调用失败: {res.error}"
        else:
            ok, reason = quasi_exact_match(res.predicted_answer, sample.final_answer)

        steps_raw = sample.annotator_metadata.get("Number of steps")
        if steps_raw is None:
            num_steps: Optional[int] = None
        else:
            try:
                num_steps = int(steps_raw)
            except (TypeError, ValueError):
                num_steps = None

        return GAIASampleRecord(
            task_id=sample.task_id,
            level=sample.level,
            question=sample.question,
            predicted_answer=res.predicted_answer,
            expected_answer=sample.final_answer,
            exact_match=ok,
            reason=reason,
            latency_ms=res.latency_ms,
            reasoning_trace=res.raw_content,
            num_steps=num_steps,
            error=res.error,
        )

    @staticmethod
    def _compute_metrics(records: List[GAIASampleRecord]) -> Dict[str, Any]:
        total = len(records)
        correct = sum(1 for r in records if r.exact_match)
        emr = (correct / total) if total else 0.0

        level_metrics: Dict[int, Dict[str, Any]] = {}
        for lvl in (1, 2, 3):
            lvl_recs = [r for r in records if r.level == lvl]
            if lvl_recs:
                lvl_ok = sum(1 for r in lvl_recs if r.exact_match)
                level_metrics[lvl] = {
                    "total": len(lvl_recs),
                    "correct": lvl_ok,
                    "accuracy": lvl_ok / len(lvl_recs),
                }

        def _drop(a: int, b: int) -> Optional[float]:
            if a in level_metrics and b in level_metrics and level_metrics[a]["accuracy"] > 0:
                acc_a = level_metrics[a]["accuracy"]
                acc_b = level_metrics[b]["accuracy"]
                return (acc_a - acc_b) / acc_a
            return None

        drop_rates = {
            "1->2": _drop(1, 2),
            "2->3": _drop(2, 3),
        }

        correct_steps = [r.num_steps for r in records if r.exact_match and r.num_steps is not None]
        avg_steps = (sum(correct_steps) / len(correct_steps)) if correct_steps else None
        avg_lat = (sum(r.latency_ms for r in records) / total) if total else 0.0
        err_cnt = sum(1 for r in records if r.error is not None)

        return {
            "exact_match_rate": emr,
            "exact_matches": correct,
            "total_samples": total,
            "level_metrics": level_metrics,
            "drop_rates": drop_rates,
            "avg_steps": avg_steps,
            "avg_latency_ms": avg_lat,
            "error_count": err_cnt,
        }

    async def evaluate_async(self, max_samples: int = 5) -> GAIAReport:
        dataset = GAIADataset(
            split=self.split,
            level=self.level,
            local_data_dir=self.local_data_dir,
            token=self.token,
        )
        samples = dataset.load(max_samples=max_samples)
        sem = asyncio.Semaphore(self.concurrency)
        records = list(await asyncio.gather(*(self._eval_one(s, sem) for s in samples)))
        m = self._compute_metrics(records)
        return GAIAReport(
            model_id=self.agent.model_id,
            split=self.split,
            level_filter=self.level,
            records=records,
            **m,
        )

    def evaluate(self, max_samples: int = 5) -> GAIAReport:
        return asyncio.run(self.evaluate_async(max_samples=max_samples))

    @staticmethod
    def export_to_gaia_format(
        report: GAIAReport,
        output_path: Optional[str | Path] = None,
        include_reasoning: bool = True,
    ) -> Path:
        if output_path is None:
            lvl_tag = f"level{report.level_filter}" if report.level_filter else "all"
            out = Path("artifacts/gaia_results") / f"gaia_{lvl_tag}_{report.timestamp}.jsonl"
        else:
            out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        with out.open("w", encoding="utf-8") as f:
            for rec in report.records:
                entry: Dict[str, Any] = {
                    "task_id": rec.task_id,
                    "model_answer": rec.predicted_answer,
                }
                if include_reasoning:
                    entry["reasoning_trace"] = rec.reasoning_trace or rec.predicted_answer
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return out

    @staticmethod
    def generate_markdown_report(
        report: GAIAReport,
        output_path: Optional[str | Path] = None,
    ) -> Path:
        if output_path is None:
            out = Path("artifacts/gaia_reports") / f"gaia_report_{report.timestamp}.md"
        else:
            out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)

        bar_len = 40
        filled = int(round(report.exact_match_rate * bar_len))
        bar = "█" * filled + "░" * (bar_len - filled)

        lines = [
            "# Argus GAIA 通用智能体评估报告",
            "",
            f"- **评估时间**: {report.timestamp}",
            f"- **Argus 模型配置**: `{report.model_id}`",
            f"- **数据集 Split / Level**: `{report.split}` / `{report.level_filter or '全部'}`",
            f"- **准精确匹配率 (Quasi Exact Match)**: **{report.exact_match_rate:.2%}** ({report.exact_matches}/{report.total_samples})",
            f"- **平均延迟**: {report.avg_latency_ms:.1f} ms",
            f"- **异常/错误数**: {report.error_count}",
        ]
        if report.avg_steps is not None:
            lines.append(f"- **正确样本平均推理步数**: {report.avg_steps:.2f}")

        lines.extend([
            "",
            f"准确率: `{bar}` {report.exact_match_rate:.2%}",
            "",
            "## 分级准确率",
            "",
            "| 难度级别 | 正确数 | 总数 | 准确率 |",
            "|----------|--------|------|--------|",
        ])
        for lvl, st in sorted(report.level_metrics.items()):
            lines.append(f"| Level {lvl} | {st['correct']} | {st['total']} | {st['accuracy']:.2%} |")

        d12 = report.drop_rates.get("1->2")
        d23 = report.drop_rates.get("2->3")
        if d12 is not None or d23 is not None:
            lines.extend(["", "## 难度递进下降率", ""])
            if d12 is not None:
                lines.append(f"- **Level 1 → Level 2**: {d12:.2%}")
            if d23 is not None:
                lines.append(f"- **Level 2 → Level 3**: {d23:.2%}")

        lines.extend([
            "",
            "## 样本详情",
            "",
            "| 任务 ID | 级别 | 预测答案 | 标准答案 | 结果 | 耗时(ms) |",
            "|---------|------|----------|----------|------|----------|",
        ])
        for rec in report.records:
            status = "✅" if rec.exact_match else "❌"
            pred = rec.predicted_answer.replace("|", "\\|").replace("\n", " ")[:60]
            exp = rec.expected_answer.replace("|", "\\|").replace("\n", " ")[:60]
            lines.append(
                f"| `{rec.task_id}` | L{rec.level} | {pred} | {exp} | {status} | {rec.latency_ms:.0f} |"
            )

        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out
