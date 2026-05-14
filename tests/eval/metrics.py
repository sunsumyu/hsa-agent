"""
[V34.0] 生产级评估指标 — 三层验证体系
L1: 工具轨迹验证 (确定性, 无需 LLM)
L2: 数值精确度验证 (确定性, 无需 LLM)
L3: 报告质量评估 (LLM Judge, 仅此层)
"""
import os
import re
from typing import List
from loguru import logger
from deepeval.metrics import BaseMetric, GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from deepeval.models.base_model import DeepEvalBaseLLM
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()


# ============================================================
# LLM Judge (仅用于 L3)
# ============================================================

class QwenJudge(DeepEvalBaseLLM):
    """裁判模型适配器"""
    def __init__(self, model_name="qwen-max"):
        self.model_name = model_name
        self.model = ChatOpenAI(
            model=model_name,
            openai_api_key=os.getenv("BAILIAN_API_KEY"),
            openai_api_base=os.getenv("BAILIAN_BASE_URL"),
        )

    def load_model(self):
        return self.model

    def _clean_json_output(self, text: str) -> str:
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.strip()

    def generate(self, prompt: str) -> str:
        res = self.load_model().invoke(prompt)
        content = str(res.content) if not isinstance(res.content, list) else "".join(
            [str(p.get("text", "")) for p in res.content if isinstance(p, dict)]
        )
        return self._clean_json_output(content)

    async def a_generate(self, prompt: str) -> str:
        res = await self.load_model().ainvoke(prompt)
        content = str(res.content) if not isinstance(res.content, list) else "".join(
            [str(p.get("text", "")) for p in res.content if isinstance(p, dict)]
        )
        return self._clean_json_output(content)

    def get_model_name(self):
        return self.model_name


qwen_judge = QwenJudge()


# ============================================================
# L1: 工具轨迹验证器 (确定性, 无需 LLM)
# ============================================================

class ToolTrajectoryMetric(BaseMetric):
    """验证 Agent 是否调用了正确的工具并查询了正确的表"""
    
    def __init__(self):
        super().__init__()
        self.score = 0
        self.name = "工具轨迹正确性"
        self.criteria = "Agent 是否执行了有效的 SQL 查询"
    
    def measure(self, test_case: LLMTestCase) -> float:
        context = test_case.retrieval_context or []
        
        checks = {
            "has_sql_call": False,
            "has_data_result": False,
            "no_error": True,
        }
        
        for finding in context:
            f_str = str(finding)
            if "[SQL查询]" in f_str or "[execute_audit_sql]" in f_str or "[执行式]" in f_str:
                checks["has_sql_call"] = True
            if "行数据" in f_str or "查询结果" in f_str or "返回" in f_str or "Rows:" in f_str or "[SQL数据]" in f_str or "MockData" in f_str:
                checks["has_data_result"] = True
            if "失败" in f_str or "Error" in f_str or "failed" in f_str.lower():
                checks["no_error"] = False
        
        passed = sum(1 for v in checks.values() if v)
        self.score = passed / len(checks)
        
        logger.debug(f"[L1 轨迹验证] checks={checks}, score={self.score:.2f}")
        return self.score
    
    async def a_measure(self, test_case: LLMTestCase) -> float:
        return self.measure(test_case)
    
    def is_successful(self) -> bool:
        return self.score >= 0.67
    
    @property
    def __name__(self):
        return "工具轨迹正确性"


# ============================================================
# L2: 数值精确度验证器 (确定性, 无需 LLM)
# ============================================================

class NumericalPrecisionMetric(BaseMetric):
    """[V35.0] 结构化数值精确度验证器：支持直接比对状态对象中的原始数值，避免文本干扰。"""
    
    def __init__(self, threshold: float = 0.05):
        super().__init__()
        self.threshold = threshold
        self.score = 0
        self.name = "数值精确度"
        self.criteria = "审计金额与种子数据的吻合程度（优先基于 Schema 比对）"
    
    def _extract_from_structured(self, additional_metadata: dict) -> List[float]:
        """从结构化报告对象中提取金额"""
        nums = []
        report = additional_metadata.get("structured_report")
        if not report: return []
        
        # 兼容 Pydantic 对象或 Dict
        findings = getattr(report, "findings", []) if hasattr(report, "findings") else report.get("findings", [])
        for f in findings:
            amt = getattr(f, "amount", 0.0) if hasattr(f, "amount") else f.get("amount", 0.0)
            nums.append(float(amt))
            
        total = getattr(report, "total_amount", 0.0) if hasattr(report, "total_amount") else report.get("total_amount", 0.0)
        nums.append(float(total))
        return nums

    def _extract_via_judge(self, text: str) -> List[float]:
        """兜底逻辑：使用 Judge 模型将 Markdown 转为 KeyValue 再提取数值"""
        prompt = f"""请从以下审计报告中提取所有核心财务数值（金额、次数），以 JSON 列表格式返回。
仅返回数字列表，不要包含 ID、年份或电话。
报告：{text}
JSON示例：[123.45, 678.90]"""
        try:
            res_str = qwen_judge.generate(prompt)
            # 简单解析 JSON 列表
            match = re.search(r'\[(.*?)\]', res_str.replace('\n', ''))
            if match:
                return [float(x.strip()) for x in match.group(1).split(',') if x.strip()]
        except:
            pass
        return []

    def measure(self, test_case: LLMTestCase) -> float:
        # 1. 提取实际值：尝试从透传的结构化状态中提取 (100% 确定性)
        meta = test_case.additional_metadata or {}
        actual_nums = self._extract_from_structured(meta)
        
        # 2. 如果结构化数据缺失，使用 Judge 智能提取 (比正则更准)
        if not actual_nums:
            logger.info("[L2 验证] 结构化数据缺失，切换至 Judge 键值对提取兜底。")
            actual_nums = self._extract_via_judge(test_case.actual_output or "")
            
        # 3. 提取预期值：直接从 Metadata 中获取标注好的 Ground Truth (100% 确定性)
        expected_nums = meta.get("ground_truth_amounts", [])
        
        # 4. 兜底提取预期值 (如果 Metadata 没传)
        if not expected_nums and test_case.expected_output:
            clean_expected = test_case.expected_output.replace(',', '')
            expected_nums = [float(n) for n in re.findall(r'(-?\d+(?:\.\d+)?)', clean_expected) if float(n) > 50 or "." in n]
            expected_nums = [n for n in expected_nums if n != 2021 and n != 2022]

        logger.info(f"[L2 Debug] Expected: {expected_nums}")
        logger.info(f"[L2 Debug] Actual: {actual_nums}")
        
        if not expected_nums:
            logger.info("[L2 Debug] No expected numbers, scoring 1.0")
            self.score = 1.0
            return 1.0
        
        if not actual_nums:
            logger.info("[L2 Debug] No actual numbers extracted, scoring 0.0")
            self.score = 0.0
            return 0.0
        
        match_count = 0
        for e in expected_nums:
            # 只要实际值列表中存在与预期值极接近的数，即计为匹配
            matched = False
            for a in actual_nums:
                if abs(e - a) <= max(self.threshold, abs(e) * 0.001):
                    match_count += 1
                    matched = True
                    break
            if matched:
                logger.debug(f"[L2 Debug] Matched: {e}")
            else:
                logger.debug(f"[L2 Debug] MISSED: {e}")
        
        self.score = min(1.0, match_count / len(expected_nums))
        logger.info(f"[L2 Debug] Final Score: {self.score:.2f} (Matched {match_count}/{len(expected_nums)})")
        return self.score

    async def a_measure(self, test_case: LLMTestCase) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return self.score >= 0.8
    
    @property
    def __name__(self):
        return "数值精确度"


# ============================================================
# L3: 证据链完整度 (LLM Judge)
# ============================================================

def get_hsa_evidence_chain_metric():
    return GEval(
        name="证据链完整度 (Evidence Chain)",
        criteria="""评估稽核报告是否满足以下要求：
1. 指出了具体的违规现象或风险点。
2. 包含具体的涉案金额数字。
3. 引用了政策条款依据。
4. 给出了稽核建议。""",
        evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
        model=qwen_judge
    )


def get_hsa_faithfulness_metric():
    return GEval(
        name="事实忠实度 (Faithfulness)",
        criteria="""评估输出是否忠实于检索上下文：
1. 报告中的金额数字必须出现在检索上下文 (SQL 结果) 中。
2. 允许引用政策名称。
3. 严禁编造检索上下文中不存在的数据。""",
        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.RETRIEVAL_CONTEXT],
        model=qwen_judge
    )
