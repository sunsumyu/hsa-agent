import json
from typing import Dict, List, Any, Tuple
from loguru import logger
from app.model_manager import model_manager

class AuditJudge:
    """[V52.0] LLM Judge 自动化质检器：专门降低误报率"""
    
    JUDGE_PROMPT = """
    你是一位资深的医疗保险审计终审官。你的任务是审核初级审计员提交的违规线索。
    
    ### 审核目标：
    1. **识别误报**：寻找可能导致该行为属于“合法操作”的豁免条款或合理理由。
    2. **证据链强度**：判断 SQL 查询结果是否足以支撑违规结论。
    3. **最终判罚**：如果证据不足或存在合理解释，必须判定为“误报 (FALSE_POSITIVE)”。
    
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

    @classmethod
    async def evaluate_finding(cls, finding: Dict, raw_data: str) -> Dict:
        """对单条线索进行深度‘审判’"""
        logger.info(f"👨‍⚖️ [JUDGE] 正在审判线索: {finding.get('violation_type')}")
        
        prompt = cls.JUDGE_PROMPT.format(
            findings=json.dumps(finding, ensure_ascii=False),
            raw_data=raw_data[:2000] # 防止过长
        )
        
        # 使用最高逻辑能力的模型进行终审
        llm, _ = model_manager.get_llm_by_role("planner_heavy") 
        response = await llm.ainvoke(prompt)
        
        try:
            # 提取 JSON
            result = json.loads(response.content[response.content.find("{"):response.content.rfind("}")+1])
            return result
        except (ValueError, KeyError, IndexError):
            return {"is_valid": True, "confidence_score": 50, "action": "PASS"}

audit_judge = AuditJudge()
