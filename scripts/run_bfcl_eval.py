"""
scripts/run_bfcl_eval.py
=======================
Argus BFCL 一键评估命令行入口。

示例:
    python scripts/run_bfcl_eval.py --model ppio-lightweight --category simple_python --samples 5
    python scripts/run_bfcl_eval.py --model ppio-lightweight --category simple_python,multiple --samples 5 --official-eval
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.eval.bfcl.agent import ArgusFCAgent
from tests.eval.bfcl.evaluator import BFCLEvaluator
from tests.eval.bfcl.official import run_official_eval


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="在 Argus 中运行 BFCL 工具调用评估")
    parser.add_argument(
        "--model",
        default="ppio-lightweight",
        help="configs/llm_providers.json 中的模型 ID (默认: ppio-lightweight)",
    )
    parser.add_argument(
        "--category",
        default="simple_python",
        help="评估类别，支持逗号分隔 (默认: simple_python)",
    )
    parser.add_argument(
        "--samples",
        type=int,
        default=5,
        help="每个类别评估的样本数，0 表示全部 (默认: 5)",
    )
    parser.add_argument(
        "--data-dir",
        default=None,
        help="BFCL 数据目录路径 (默认自动探测 data/bfcl 或 .venv-bfcl)",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=2,
        help="异步并发数 (默认: 2)",
    )
    parser.add_argument(
        "--bfcl-model-name",
        default="Qwen/Qwen3-8B",
        help="导出与官方 bfcl evaluate 使用的模型名标识 (默认: Qwen/Qwen3-8B，需为 BFCL 注册名)",
    )
    parser.add_argument(
        "--official-eval",
        action="store_true",
        help="导出后调用 .venv-bfcl 中的官方 `bfcl evaluate --partial-eval` 复核",
    )
    parser.add_argument(
        "--output-dir",
        default="artifacts/bfcl_results",
        help="BFCL 结果导出目录 (默认: artifacts/bfcl_results)",
    )
    parser.add_argument(
        "--report-path",
        default=None,
        help="Markdown 报告输出路径 (默认: artifacts/bfcl_reports/bfcl_report_<ts>.md)",
    )
    return parser.parse_args()


def main() -> int:
    load_dotenv()
    args = parse_args()
    categories = [c.strip() for c in args.category.split(",") if c.strip()]

    print("=" * 60)
    print("Argus BFCL 工具调用评估")
    print("=" * 60)
    print(f"Argus 模型: {args.model}")
    print(f"评估类别: {', '.join(categories)}")
    print(f"每类样本数: {args.samples if args.samples > 0 else '全部'}")

    agent = ArgusFCAgent(model_id=args.model)
    evaluator = BFCLEvaluator(
        agent=agent,
        bfcl_data_dir=args.data_dir,
        concurrency=args.concurrency,
    )

    report = evaluator.evaluate(categories=categories, max_samples=args.samples)
    print(f"\n本地 AST 评估完成: {report.overall_accuracy:.2%} ({report.correct_samples}/{report.total_samples})")
    for cat, st in report.category_stats.items():
        print(f"  - {cat}: {st['accuracy']:.2%} ({st['correct']}/{st['total']})")

    exported = evaluator.export_to_bfcl_format(
        report,
        output_dir=args.output_dir,
        bfcl_model_name=args.bfcl_model_name,
    )
    for cat, path in exported.items():
        print(f"已导出官方格式 [{cat}]: {path}")

    official_summary = None
    if args.official_eval:
        print("\n正在运行 BFCL 官方评估工具复核...")
        res = run_official_eval(
            result_dir=args.output_dir,
            model_name=args.bfcl_model_name,
            categories=categories,
            partial_eval=True,
        )
        if not res["available"]:
            print(f"[跳过] {res['stderr']}")
        else:
            print(f"命令: {res['command']}")
            official_summary = (res["stdout"] or "") + ("\n" + res["stderr"] if res["stderr"] else "")
            print(official_summary)

    report_file = evaluator.generate_markdown_report(
        report,
        output_path=args.report_path,
        official_summary=official_summary,
    )
    print(f"\nMarkdown 报告已生成: {report_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
