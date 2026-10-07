import json
from typing import Dict, List, Any
from loguru import logger
from app.infra.model_manager import model_manager

class AuditJudge:
    “””[V60.0] LLM Judge 自动化质检器（安全增强版）”””
    
    JUDGE_PROMPT = “””
    你是一位资深的医疗保险审计终审官。你的任务是审核初级审计员提交的违规线索。
    
    ### 审核目标：
    1. **识别误报**：寻找可能导致该行为属于”合法操作”的豁免条款或合理理由。
    2. **证据链强度**：判断 SQL 查询结果是否足以支撑违规结论。
    3. **最终判罚**：如果证据不足或存在合理解释，必须判定为”误报 (FALSE_POSITIVE)”。
    
    ### 待审核线索：
    {findings}
    
    ### 原始数据上下文：
    {raw_data}
    
    ### 输出要求 (JSON格式)：
    {{
        “is_valid”: bool,
        “confidence_score”: int (0-100),
        “refutation_reason”: “如果是误报，请给出反驳理由”,
        “action”: “PASS” 或 “RE_AUDIT”
    }}
    “””
    
    @staticmethod
    def _sanitize_for_prompt(text: str, max_length: int = 2000) -> str:
        “””[V60.0] 对拼入 LLM 提示词的文本进行标准化和脱敏”””
        if not text:
            return “”
        
        # 1. 限制长度
        text = text[:max_length]
        
        # 2. 脱敏敏感字段
        import re
        text = re.sub(r’”([^”]*psn[ _]no[^”]*)”’, ‘”***”’, text, flags=re.IGNORECASE)
        text = re.sub(r’”([^”]*phone[^”]*)”’, ‘”***”’, text, flags=re.IGNORECASE)
        text = re.sub(r’”([^”]*id_card[^”]*)”’, ‘”***”’, text, flags=re.IGNORECASE)
        
        # 3. 移除 SQL 代码块
        text = re.sub(r’sql:\s*```sql\s*.*?```’, ‘[SQL 查询已隐藏]’, text, flags=re.DOTALL)
        
        # 4. 去除控制字符
        text = re.sub(r’[\x00-\x1f\x7f]’, ‘’, text)
        
        return text
    
    @classmethod
    async def evaluate_finding(cls, finding: Dict, raw_data: str) -> Dict:
        “””对单条线索进行深度’审判’（安全增强版）”””
        logger.info(f”👨‍⚖️ [JUDGE] 正在审判线索: {finding.get(‘violation_type’)}”)
        
        # [V60.0] Step 1: 清理带敏感数据的数据
        sanitized_data = cls._sanitize_for_prompt(raw_data)
        
        prompt = cls.JUDGE_PROMPT.format(
            findings=json.dumps(finding, ensure_ascii=False),
            raw_data=sanitized_data
        )
        
        # 使用最高逻辑能力的模型进行终审
        llm, _ = model_manager.get_llm_by_role(“planner_heavy”) 
        response = await llm.ainvoke(prompt)
        
        try:
            # [V60.0] Step 2: 更健壮的 JSON 提取
            content = response.content
            
            # 方法1：尝试使用正则提取完整的 JSON 块
            json_match = re.search(r’\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}’, content, re.DOTALL)
            if json_match:
                content = json_match.group(0)
            
            result = json.loads(content)
            
            # [V60.0] Step 3: 验证结果格式
            required_keys = {“is_valid”, “confidence_score”, “action”}
            if not required_keys.issubset(result.keys()):
                raise ValueError(f”Judged result missing required keys: {required_keys}”)
            
            # 如果判为误报且 confidence_score 过低，强制判为误报
            if result.get(“is_valid”, True) and result.get(“confidence_score”, 50) < 70:
                logger.warning(f”⚠️ [JUDGE] Confidence score low ({result.get(‘confidence_score’)})，强制转为误报”)
                result[“is_valid”] = False
                result[“action”] = “RE_AUDIT”
                result[“refutation_reason”] = “Confidence score below threshold (70)”
            
            return result
            
        except (ValueError, KeyError, IndexError, json.JSONDecodeError) as e:
            # [V60.0] JSON 解析失败时返回明确错误
            logger.error(f”❌ [JUDGE] JSON 解析失败: {e}”)
            return {
                “is_valid”: False,  # 默认判为误报，而非默认通过
                “confidence_score”: 10,
                “refutation_reason”: f”Judgment failed due to parsing error: {str(e)[:100]}”,
                “action”: “RE_AUDIT”
            }

audit_judge = AuditJudge()
