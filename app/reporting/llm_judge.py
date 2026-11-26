import json
import re
from typing import Any, Dict

from loguru import logger


class AuditJudge:
    """[V60.0] LLM Judge 自动化质检器（安全增强版）"""

    JUDGE_PROMPT = """
    你是一位资深的医疗保险审计终审官。你的任务是审核初级审计员提交的违规线索。

    ### 审核目标：
    1. **识别误报**：寻找可能导致该行为属于"合法操作"的豁免条款或合理理由。
    2. **证据链强度**：判断 SQL 查询结果是否足以支撑违规结论。
    3. **最终判罚**：如果证据不足或存在合理解释，必须判定为"误报 (FALSE_POSITIVE)"。

    ### 待审核线索：
    {findings}

    ### 原始数据上下文：
    {raw_data}

    ### 输出要求 (JSON格式)：
    {{
        "is_valid": bool,
        "confidence_score": int (0-100),
        "refutation_reason": "如果是误报，请给出反驳理由",
        "action": "PASS" 或 "RE_AUDIT"
    }}
    """

    @staticmethod
    def _sanitize_for_prompt(text: str, max_length: int = 2000) -> str:
        """[V60.0] 对拼入 LLM 提示词的文本进行标准化和脱敏"""
        if not text:
            return ""

        sanitized = text[:max_length]
        sanitized = re.sub(r'"([^"]*psn[ _]no[^"]*)"', '"***"', sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r'"([^"]*phone[^"]*)"', '"***"', sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r'"([^"]*id_card[^"]*)"', '"***"', sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r'sql:\s*```sql\s*.*?```', '[SQL 查询已隐藏]', sanitized, flags=re.DOTALL)
        return re.sub(r'[\x00-\x1f\x7f]', '', sanitized)

    @staticmethod
    def _parse_judge_response(content: str) -> Dict[str, Any]:
        """解析并校验终审模型返回的 JSON 结构。"""
        json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content or "", re.DOTALL)
        raw_json = json_match.group(0) if json_match else content
        result = json.loads(raw_json)

        required_keys = {"is_valid", "confidence_score", "action"}
        if not required_keys.issubset(result.keys()):
            raise ValueError(f"Judged result missing required keys: {required_keys}")

        if result.get("is_valid", True) and result.get("confidence_score", 50) < 70:
            logger.warning(
                f"⚠️ [JUDGE] Confidence score low ({result.get('confidence_score')})，强制转为误报"
            )
            result["is_valid"] = False
            result["action"] = "RE_AUDIT"
            result["refutation_reason"] = "Confidence score below threshold (70)"

        return result

    @classmethod
    async def evaluate_finding(cls, finding: Dict, raw_data: str) -> Dict:
        """对单条线索进行深度'审判'（安全增强版）"""
        logger.info(f"👨‍⚖️ [JUDGE] 正在审判线索: {finding.get('violation_type')}")

        sanitized_data = cls._sanitize_for_prompt(raw_data)
        prompt = cls.JUDGE_PROMPT.format(
            findings=json.dumps(finding, ensure_ascii=False),
            raw_data=sanitized_data,
        )

        from app.core.llm_provider import llm_provider
        from langchain_core.messages import HumanMessage

        response = await llm_provider.chat(
            role="planner_heavy",
            messages=[HumanMessage(content=prompt)],
            config={"metadata": {"role": "judge", "target": "evaluate_finding"}},
        )

        try:
            return cls._parse_judge_response(response.content)
        except (ValueError, KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
            logger.error(f"❌ [JUDGE] JSON 解析失败: {e}")
            return {
                "is_valid": False,
                "confidence_score": 10,
                "refutation_reason": f"Judgment failed due to parsing error: {str(e)[:100]}",
                "action": "RE_AUDIT",
            }


audit_judge = AuditJudge()
