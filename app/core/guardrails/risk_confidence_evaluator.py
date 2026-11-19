import json
from typing import Dict, Any, Optional
from loguru import logger
from langchain_core.messages import BaseMessage, AIMessage


def evaluate_response_confidence(message: BaseMessage) -> float:
    """[V154.0 / Matt Pocock Deep Module] 评估模型回复质量置信度 (0.0 ~ 1.0)
    
    隐藏细节：
    - 响应速度异常/幻觉降权
    - 拒答/元语噪声惩罚
    - 报错信号渗透惩罚
    - Token 消耗异常检测
    """
    score = 1.0
    
    metadata = getattr(message, "additional_kwargs", {}) or {}
    latency = metadata.get("audit_latency_ms", 0)
    content = str(getattr(message, "content", ""))
    
    # A. 响应速度异常 (过快可能意味着幻觉或复读)
    if latency < 150 and len(content) > 100:
        logger.warning(f"⚠️ [Gate] 响应速度异常过快 ({latency:.1f}ms)，疑似幻觉。")
        score -= 0.3
        
    # B. 内容噪音
    if "抱歉" in content or "无法提供" in content or "作为一个AI" in content:
        logger.warning("⚠️ [Gate] 命中拒绝服务关键词。")
        score -= 0.6
        
    # C. 逻辑矛盾信号 (如 SQL 报错信息出现在内容中)
    if "error" in content.lower() or "failed" in content.lower():
        score -= 0.5
        
    # D. Token 消耗异常 (空回复但有 tool_calls 时不降权)
    usage = getattr(message, "usage_metadata", {}) or {}
    out_tokens = usage.get("output_tokens", 0)
    if out_tokens < 5 and not getattr(message, "tool_calls", None):
        score -= 0.4
        
    return max(0.0, score)


def evaluate_execution_risk(state: Dict[str, Any]) -> float:
    """[V154.0 / Matt Pocock Deep Module] 评估当前 SQL 操作或状态风险 (0.0 ~ 1.0)
    
    隐藏细节：
    - DDL/DML 毁灭性关键词风控截断
    - 大跨表 JOIN/GROUP BY 查询风险加权
    - 受影响超大结果集动态反向探测
    """
    risk = 0.0
    sql_raw = state.get("sql_query", "")
    sql = str(sql_raw or "").upper()
    
    # 1. 关键词风险
    if "DELETE" in sql or "DROP" in sql or "TRUNCATE" in sql:
        risk += 0.9  # 极高风险
    if "UPDATE" in sql or "ALTER" in sql:
        risk += 0.7
        
    # 2. 数据量风险 (跨表大查询)
    if "JOIN" in sql and "GROUP BY" in sql:
        risk += 0.3
        
    # 3. 结果集风险 (如果已知结果集巨大)
    messages = state.get("messages", []) or []
    for m in reversed(messages):
        if hasattr(m, "content") and "affected_rows" in str(m.content):
            try:
                content_dict = json.loads(str(m.content))
                rows = content_dict.get("affected_rows", 0)
                if rows > 10000:
                    risk += 0.5
            except Exception:
                pass
            break
            
    return min(1.0, risk)


def should_trigger_human_approval(state: Dict[str, Any]) -> bool:
    """判断是否需要人工介入 (HITL)"""
    risk = evaluate_execution_risk(state)
    if risk > 0.6:
        logger.warning(f"🚨 [Gate] 检测到高风险操作 (Risk: {risk:.2f})，正在挂起工作流等待人工审批。")
        return True
    return False


def should_trigger_critic(state: Dict[str, Any]) -> bool:
    """判断是否需要触发 CRITIC 自愈节点"""
    messages = state.get("messages", []) or []
    if not messages:
        return False
        
    last_msg = messages[-1]
    
    if isinstance(last_msg, AIMessage):
        if state.get("error_log"):
            return True
            
        confidence = evaluate_response_confidence(last_msg)
        if confidence < 0.5:
            logger.info(f"🔄 [Gate] 信心值过低 ({confidence:.2f})，触发 CRITIC 自愈。")
            return True
            
    return False
