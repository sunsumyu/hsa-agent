import os
import re
from typing import Optional, List
from deepeval.metrics import BaseMetric, GEval
from deepeval.test_case import LLMTestCase, LLMTestCaseParams
from deepeval.models.base_model import DeepEvalBaseLLM
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

class QwenMaxJudge(DeepEvalBaseLLM):
    """多供应商裁判模型适配器。"""
    def __init__(self, model_name="gemma-4-31b-it"):
        self.model_name = model_name
        if "gemma" in model_name or "gemini" in model_name:
            from langchain_google_genai import ChatGoogleGenerativeAI
            self.model = ChatGoogleGenerativeAI(
                model=model_name,
                google_api_key=os.getenv("GOOGLE_API_KEY"),
                temperature=0.1
            )
        elif "doubao" in model_name or "ep-" in model_name:
             self.model = ChatOpenAI(
                model=model_name,
                openai_api_key=os.getenv("VOLC_API_KEY"),
                openai_api_base=os.getenv("VOLC_BASE_URL")
            )
        else:
            self.model = ChatOpenAI(
                model=model_name,
                openai_api_key=os.getenv("BAILIAN_API_KEY"),
                openai_api_base=os.getenv("BAILIAN_BASE_URL")
            )

    def load_model(self):
        return self.model

    def generate(self, prompt: str) -> str:
        chat_model = self.load_model()
        res = chat_model.invoke(prompt)
        # 确保返回的是纯字符串，处理可能出现的 List[dict] 类型 content
        if isinstance(res.content, list):
            return "".join([str(p.get("text", "")) for p in res.content if isinstance(p, dict)])
        return str(res.content)

    async def a_generate(self, prompt: str) -> str:
        chat_model = self.load_model()
        res = await chat_model.ainvoke(prompt)
        if isinstance(res.content, list):
            return "".join([str(p.get("text", "")) for p in res.content if isinstance(p, dict)])
        return str(res.content)

    def get_model_name(self):
        return self.model_name

# 实例化 Qwen-Max 裁判
qwen_judge = QwenMaxJudge()

def get_hsa_evidence_chain_metric():
    """证据链完整度指标：利用 GEval 评估是否满足医保稽核‘三要素’。"""
    return GEval(
        name="证据链完整度 (Evidence Chain)",
        criteria="""
        评估 Agent 的稽核报告是否满足以下‘医保证据链’要求：
        1. 必须明确指出违规现象或风险点 (Specific Behavior)。
        2. 必须包含具体的涉案金额 (Amount)，不能含糊其辞。
        3. 必须引用明确的政策条款依据 (Policy Basis)。
        4. 必须给出后续的稽核或处置建议 (Audit Suggestion)。
        5. 格式必须符合‘🚩卡片式’排版样式。
        """,
        evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
        model=qwen_judge
    )

def get_hsa_faithfulness_metric():
    """忠实度/事实一致性指标 (Faithfulness)：判定结论中提到的具体事实（医院、金额、日期）是否完全源于 SQL 检索。"""
    return GEval(
        name="事实忠实度 (Faithfulness)",
        criteria="""
        评估 Agent 的输出是否完全真实：
        1. [基准] 医院名、违规金额、结算日期等“事实性数据”必须出现在检索上下文（SQL 结果）中。
        2. [豁免] 允许 Agent 引用专家知识库中的政策名称或判定准则，甚至基于政策逻辑对数据进行解读。
        3. [违规] 严禁将政策库中的“示例数据”当作当前案件的“真实涉案数据”。
        4. [违规] 如果 SQL 结果中没有某个医院，但 Agent 合理化输出了该医院，即使逻辑正确也判定为事实不忠实。
        """,
        evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT, LLMTestCaseParams.RETRIEVAL_CONTEXT],
        model=qwen_judge
    )

def get_hsa_answer_relevance_metric():
    """答案相关性指标 (Answer Relevance)：利用 GEval 判定输出是否直接解决了用户核心诉求。"""
    return GEval(
        name="答案相关性 (Answer Relevance)",
        criteria="""
        评估 Agent 是否直接且清晰地回答了用户的核心稽核问题：
        1. 是否明确判定了是否存在违规。
        2. 是否清晰给出了违规金额或涉案范围。
        3. 避免大段无关的废话，聚焦于稽核结论。
        """,
        evaluation_params=[LLMTestCaseParams.INPUT, LLMTestCaseParams.ACTUAL_OUTPUT],
        model=qwen_judge
    )

class HSANumericalPrecisionMetric(BaseMetric):
    """数值精确度指标：检查回复中的金额是否与预期（或 SQL 结果）一致，支持多格式容错。"""
    def __init__(self, threshold: float = 0.01):
        super().__init__()
        self.threshold = threshold
        self.score = 0
        self.name = "数值精确度"
        self.criteria = "检查违规金额计算的准确性"

    def _parse_amount(self, text: str) -> List[float]:
        """从复杂文本中提取浮点数，支持货币符号、逗号。"""
        import re
        # 移除货币符号和逗号
        clean_text = text.replace(',', '').replace('¥', '').replace('￥', '').replace('元', '')
        # 匹配数字内容，包含带小数点的
        nums = re.findall(r'(-?\d+(?:\.\d+)?)', clean_text)
        return [float(n) for n in nums]

    def measure(self, test_case: LLMTestCase) -> float:
        actual_nums = self._parse_amount(test_case.actual_output)
        expected_nums = self._parse_amount(test_case.expected_output or "")
        
        logger.debug(f"Numerical Eval - Expected: {expected_nums}, Actual: {actual_nums}")
        
        if not expected_nums:
            self.score = 1.0 # 无预期目标时默认通过
            return 1.0
        
        if not actual_nums:
            self.score = 0.0 # 预期有数字但实际无数字
            return 0.0
            
        # 寻找匹配项
        match_count = 0
        for e in expected_nums:
            found = False
            for a in actual_nums:
                # 容差检查 (允许万分之一的误差 或 绝对值 0.05 的误差)
                if abs(e - a) <= max(self.threshold, e * 0.0001, 0.05):
                    match_count += 1
                    found = True
                    break
            if not found:
                logger.warning(f"Precision Failure: Expected {e} but not found in {actual_nums}")
        
        score = match_count / len(expected_nums)
        self.score = score
        return score

    async def a_measure(self, test_case: LLMTestCase) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return self.score >= 0.8

    @property
    def __name__(self):
        return "数值精确度"
