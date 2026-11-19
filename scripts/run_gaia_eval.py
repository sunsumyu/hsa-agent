"""
scripts/run_gaia_eval.py
=======================
Argus GAIA 评估命令行入口。

示例:
    python scripts/run_gaia_eval.py --model ppio-lightweight --level 1 --samples 5
    python scripts/run_gaia_eval.py --model ppio-lightweight --split validation --samples 10 --data-dir data/gaia
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.eval.gaia.agent import ArgusGAIAAgent
from tests.eval.gaia.evaluator import GAIAEvaluator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="在 Argus 中运行 GAIA 基准评估")
    parser.add_argument(
        "--model",
        default="ppio-lightweight",
        help="configs/llm_providers.json 中的模型 ID (默认: ppio-lightweight)",
    )
    parser.add_argument(
        "--split",
        default="validation",
        choices=["validation", "test"],
        help="数据集 split (默认: validation)",
    )
    parser.add_argument(
        "--level",
        type=int,
        default=None,
        choices=[1, 2, 3],
        help="筛选难度级别 1/2/3 (默认: 全部)",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=5,
        help="评估样本数，0 表示全部 (默认: 5)",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="GAIA 本地数据目录 (默认自动探测 data/gaia 与 ../hello-agents/data/gaia)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=2,
        help="异步并发数 (默认: 2)",
    )
    parser.add_argument(
        "--output-jsonl",
        default=None,
        help="GAIA 官方提交格式 JSONL 输出路径 (默认: artifacts/gaia_results/gaia_<level>_<ts>.jsonl)",
    )
    parser.add_argument(
        "--report-path",
        default=None,
        help="Markdown 报告输出路径 (默认: artifacts/gaia_reports/gaia_report_<ts>.md)",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()

    print("=" * 60)
    print("Argus GAIA 通用智能体评估")
    print("=" * 60)
    print(f"Argus 模型: {args.model}")
    print(f"Split / Level: {args.split} / {args.level or '全部'}")
    print(f"样本数: {args.samples if args.samples > 0 else '全部'}")

    agent = ArgusGAIAAgent(model_id=args.model)
    evaluator = GAIAEvaluator(
        agent=agent,
        split=args.split,
        level=args.level,
        local_data_dir=args.data_dir,
        concurrency=args.concurrency,
    )

    try:
        report = evaluator.evaluate(max_samples=args.samples)
    except FileNotFoundError as exc:
        print(f"\n[缺少数据集] {exc}")
        return 2

    print(f"\n准精确匹配率: {report.exact_match_rate:.2%} ({report.exact_matches}/{report.total_samples})")
    for lvl, st in sorted(report.level_metrics.items()):
        print(f"  - Level {lvl}: {st['accuracy']:.2%} ({st['correct']}/{st['total']})")

    jsonl_path = evaluator.export_to_gaia_format(report, output_path=args.output_jsonl)
    print(f"已导出 GAIA 官方格式: {jsonl_path}")

    report_file = evaluator.generate_markdown_report(report, output_path=args.report_path)
    print(f"Markdown 报告已生成: {report_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
