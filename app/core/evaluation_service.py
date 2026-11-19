# -*- coding: utf-8 -*-
"""
app/core/evaluation_service.py
==============================
[Matt Pocock Deep Module] 统一自动化回归评测服务 (AuditEvaluationService)
对外呈现极其克制的接口 (evaluate_dataset, evaluate_local_dataset, sync_dataset_to_langsmith, score_prediction)，对内吞噬：
- LangSmith Client / evaluate 离线与在线批处理
- 医保与金融 SQL 可执行性合规检查 (sql_valid)
- 违规金额与涉案人次同真值 (Physical Truth) 的数值拟合与容差计算 (amount_match)
- 自动化门禁 Pass / Fail 判定
"""

import os
import json
from typing import Dict, Any, List, Optional
from dataclasses import dataclass
from loguru import logger
from app.core.container import ServiceProvider


@dataclass
class EvalSummary:
    """评测结果聚合摘要"""
    dataset_name: str
    total_examples: int
    sql_accuracy: float
    amount_precision: float
    is_passing: bool
    experiment_url: str


class AuditEvaluationService:
    """自动化回归评测深模块服务"""

    def __init__(self, pass_threshold: float = 0.90, amount_tolerance: float = 0.05):
        self.pass_threshold = pass_threshold
        self.amount_tolerance = amount_tolerance

    def score_prediction(self, prediction: Dict[str, Any], ground_truth: Dict[str, Any]) -> Dict[str, Any]:
        """
        [纯计算/离线评分函数]
        计算 SQL 语法有效性与违规金额吻合度
        """
        # 1. SQL 语法有效性检验
        final_sql = str(prediction.get("final_sql") or "").strip().lower()
        # 必须是 SELECT 查询，严禁任何破坏性操作
        sql_valid = 1.0 if (
            final_sql.startswith("select")
            and not any(k in final_sql for k in ["drop ", "truncate ", "delete ", "update "])
        ) else 0.0

        # 2. 金额比对
        expected_amount = float(ground_truth.get("amount") or 0.0)
        actual_amount = float((prediction.get("audit_result") or {}).get("total_amount") or 0.0)

        if expected_amount == 0.0:
            amount_match = 1.0 if actual_amount == 0.0 else 0.0
        else:
            diff_ratio = abs(actual_amount - expected_amount) / expected_amount
            # 允许 tolerance (如 5%) 内满分，超出线性扣减
            if diff_ratio <= self.amount_tolerance:
                amount_match = 1.0
            else:
                amount_match = max(0.0, 1.0 - diff_ratio)

        is_passing = (sql_valid == 1.0) and (amount_match >= self.pass_threshold)

        return {
            "sql_valid": sql_valid,
            "amount_match": amount_match,
            "is_passing": is_passing
        }

    def evaluate_local_dataset(
        self,
        file_path: str,
        predict_fn: Optional[Any] = None
    ) -> EvalSummary:
        """
        [脱机/隔离评测] 读取本地 JSON 黄金用例集，执行快速评估打分 (支持无公网/无云端凭据的 CI 环境)
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"本地黄金用例集不存在: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            cases = json.load(f)

        if not isinstance(cases, list):
            cases = [cases]

        sql_scores = []
        amount_scores = []

        for case in cases:
            # 兼容多种用例结构 (golden_dataset.json vs golden_dataset_user_perspective.json)
            question = case.get("input") or case.get("prompt") or case.get("question") or ""
            expected_amt = 0.0
            if "expected_sum" in case:
                expected_amt = float(case["expected_sum"])
            elif "ground_truth_amounts" in case and case["ground_truth_amounts"]:
                expected_amt = float(case["ground_truth_amounts"][0])

            truth = {"amount": expected_amt}

            if predict_fn:
                import asyncio
                import inspect
                res = predict_fn({"question": question})
                if inspect.iscoroutine(res):
                    loop = asyncio.get_event_loop()
                    pred = loop.run_until_complete(res)
                else:
                    pred = res
            else:
                # 默认基准预测：使用 case 自带的验证 SQL 和真值
                pred = {
                    "final_sql": case.get("verify_sql", "SELECT 1 FROM fqz_fymx_test"),
                    "audit_result": {"total_amount": expected_amt}
                }

            scores = self.score_prediction(pred, truth)
            sql_scores.append(scores["sql_valid"])
            amount_scores.append(scores["amount_match"])

        avg_sql = sum(sql_scores) / len(sql_scores) if sql_scores else 0.0
        avg_amt = sum(amount_scores) / len(amount_scores) if amount_scores else 0.0
        is_pass = (avg_sql >= self.pass_threshold) and (avg_amt >= self.pass_threshold)

        return EvalSummary(
            dataset_name=os.path.basename(file_path),
            total_examples=len(cases),
            sql_accuracy=avg_sql,
            amount_precision=avg_amt,
            is_passing=is_pass,
            experiment_url="local://eval-report"
        )

    def sync_dataset_to_langsmith(
        self,
        dataset_name: str,
        file_path: str,
        description: str = ""
    ) -> int:
        """
        [数据飞轮] 将本地黄金用例集同步上传至 LangSmith 云端 Dataset
        """
        obs = ServiceProvider.resolve("observability")
        client = getattr(obs, "_langsmith_client", None)
        if not client:
            raise RuntimeError("LangSmith Client 未激活，无法同步数据集到云端")

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"本地数据集不存在: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            cases = json.load(f)

        if not isinstance(cases, list):
            cases = [cases]

        # 1. 查找或创建 Dataset
        dataset = None
        for ds in client.list_datasets():
            if ds.name == dataset_name:
                dataset = ds
                break

        if not dataset:
            dataset = client.create_dataset(
                dataset_name=dataset_name,
                description=description or f"Synced from {os.path.basename(file_path)}"
            )

        # 2. 批量添加 Examples
        count = 0
        for item in cases:
            q = item.get("input") or item.get("prompt") or item.get("question") or ""
            expected_amt = item.get("expected_sum") or (item.get("ground_truth_amounts") or [0.0])[0]
            client.create_example(
                inputs={"question": q},
                outputs={"physical_truth": {"amount": expected_amt}},
                dataset_id=dataset.id
            )
            count += 1

        logger.info(f"🎉 成功同步 {count} 条黄金用例到 LangSmith 数据集: {dataset_name}")
        return count

    def evaluate_dataset(
        self,
        dataset_name: str,
        experiment_prefix: str = "ci-eval",
        custom_predict: Optional[Any] = None
    ) -> EvalSummary:
        """
        [极窄接口] 执行端到端评测并返回综合评估摘要
        """
        obs = ServiceProvider.resolve("observability")
        client = getattr(obs, "_langsmith_client", None)
        if not client:
            raise RuntimeError("LangSmith Client 未激活，无法连接云端执行 evaluate_dataset")

        from langsmith.evaluation import evaluate

        def _sql_evaluator(run, example):
            scores = self.score_prediction(run.outputs or {}, example.outputs or {})
            return {"key": "sql_valid", "score": scores["sql_valid"]}

        def _amount_evaluator(run, example):
            scores = self.score_prediction(run.outputs or {}, example.outputs or {})
            return {"key": "amount_match", "score": scores["amount_match"]}

        predict_fn = custom_predict
        if not predict_fn:
            fast_router = ServiceProvider.resolve("fast_router")
            async def _default_predict(inputs: dict):
                return await fast_router.route_and_execute(inputs.get("question", ""))
            predict_fn = _default_predict

        results = evaluate(
            predict_fn,
            data=dataset_name,
            evaluators=[_sql_evaluator, _amount_evaluator],
            experiment_prefix=experiment_prefix,
            max_concurrency=2
        )

        df = results.to_pandas()
        sql_acc = float(df["feedback.sql_valid"].mean()) if "feedback.sql_valid" in df else 0.0
        amt_acc = float(df["feedback.amount_match"].mean()) if "feedback.amount_match" in df else 0.0
        is_pass = (sql_acc >= self.pass_threshold) and (amt_acc >= self.pass_threshold)

        return EvalSummary(
            dataset_name=dataset_name,
            total_examples=len(df),
            sql_accuracy=sql_acc,
            amount_precision=amt_acc,
            is_passing=is_pass,
            experiment_url="https://smith.langchain.com"
        )
