# -*- coding: utf-8 -*-
"""
scripts/run_ci_eval.py
======================
[CI/CD 自动化门禁脚本] 医保审计智能体质量评测与数据集同步 CLI
基于 Matt Pocock 架构契约构建，调用 AuditEvaluationService 深模块。

用法：
1. 本地脱机快速回归 (适合 Git PR / 无云端凭据的 CI runner)：
   python scripts/run_ci_eval.py --mode local --dataset tests/eval/golden_dataset.json

2. 线上 LangSmith 批量评测 (适合 Nightly Build / 模型调优评估)：
   python scripts/run_ci_eval.py --mode cloud --dataset medical-audit-golden-cases

3. 本地黄金数据集一键同步至云端：
   python scripts/run_ci_eval.py --sync tests/eval/golden_dataset.json --name medical-audit-golden-cases
"""

import sys
import os
import argparse

# 设置 UTF-8 输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

# 引入项目根目录
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from app.core.bootstrap import register_services
from app.core.container import ServiceProvider


def main():
    parser = argparse.ArgumentParser(description="Argus 自动化评测与数据飞轮同步工具")
    parser.add_argument("--mode", choices=["local", "cloud"], default="local", help="评测模式：local(脱机回归) 或 cloud(云端评测)")
    parser.add_argument("--dataset", default="tests/eval/golden_dataset.json", help="数据集路径或云端名称")
    parser.add_argument("--sync", help="同步本地 JSON 用例集到 LangSmith 云端 (传入 JSON 路径)")
    parser.add_argument("--name", default="medical-audit-golden-cases", help="同步到云端时的目标数据集名称")
    parser.add_argument("--threshold", type=float, default=0.90, help="发布合格门禁阈值 (默认 0.90 即 90%)")
    args = parser.parse_args()

    # 初始化受管服务
    register_services()
    eval_svc = ServiceProvider.resolve("evaluation_service")
    eval_svc.pass_threshold = args.threshold

    # 1. 执行同步
    if args.sync:
        print(f">>> 正在同步本地数据集 [{args.sync}] 到 LangSmith 云端 [{args.name}]...")
        try:
            count = eval_svc.sync_dataset_to_langsmith(
                dataset_name=args.name,
                file_path=args.sync
            )
            print(f"🎉 成功同步 {count} 条黄金用例到云端数据集: {args.name}")
            sys.exit(0)
        except Exception as e:
            print(f"❌ 同步失败: {e}")
            sys.exit(1)

    # 2. 执行评测
    print("=" * 70)
    print(f"🚀 开始执行审计质量评测 (模式: {args.mode.upper()}, 目标: {args.dataset}, 门禁阈值: {args.threshold:.0%})")
    print("=" * 70)

    try:
        if args.mode == "local":
            summary = eval_svc.evaluate_local_dataset(args.dataset)
        else:
            summary = eval_svc.evaluate_dataset(args.dataset)

        print(f"用例总数:          {summary.total_examples}")
        print(f"SQL 语法合规率:    {summary.sql_accuracy:.2%}")
        print(f"违规金额吻合度:    {summary.amount_precision:.2%}")
        print(f"评测仪表盘链接:    {summary.experiment_url}")
        print("=" * 70)

        if summary.is_passing:
            print(f"✅ [PASS] 核心质量指标达到 {args.threshold:.0%} 门禁标准，准予合并发版！")
            sys.exit(0)
        else:
            print(f"❌ [FAIL] 核心质量指标未达到 {args.threshold:.0%} 门禁标准，阻断 CI/CD 流水线！")
            sys.exit(1)

    except Exception as e:
        print(f"💥 评测执行异常: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
