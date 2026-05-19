"""
app/core/gates.py
=================
[V154.0] 自适应质量门控 (Adaptive Quality Gates)

负责根据消息元数据和内容评估执行质量，为 LangGraph 提供动态路由依据。
"""

from typing import Dict, Any, List, Optional
from loguru import logger
from langchain_core.messages import BaseMessage, AIMessage

class QualityGate:
    """
    质量门控：利用审计元数据驱动自愈逻辑。
    """
    
    @staticmethod
    def evaluate_response(message: BaseMessage) -> float:
        """
        评估响应质量 (0.0 ~ 1.0)
        """
        score = 1.0
        
        # 1. 提取元数据
        metadata = getattr(message, "additional_kwargs", {})
        latency = metadata.get("audit_latency_ms", 0)
        content = str(message.content)
        
        # 2. 启发式降权
        
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

    @staticmethod
    def evaluate_risk(state: Dict[str, Any]) -> float:
        """
        评估操作风险 (0.0 ~ 1.0)
        """
        risk = 0.0
        # [V178.0] 物理加固：防止 state['sql_query'] 为 None 时崩溃
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
        # 此处可以结合最近一次 ToolResponse 的 affected_rows
        messages = state.get("messages", [])
        for m in reversed(messages):
            if hasattr(m, "content") and "affected_rows" in str(m.content):
                import json
                try:
                    # 尝试解析 USP 响应
                    content_dict = json.loads(str(m.content))
                    rows = content_dict.get("affected_rows", 0)
                    if rows > 10000: risk += 0.5
                except: pass
                break
                
        return min(1.0, risk)

    @staticmethod
    def should_trigger_human_approval(state: Dict[str, Any]) -> bool:
        """
        判断是否需要人工介入 (HITL)
        """
        risk = QualityGate.evaluate_risk(state)
        # 风险阈值 > 0.6 或 显式标记
        if risk > 0.6:
            logger.warning(f"🚨 [Gate] 检测到高风险操作 (Risk: {risk:.2f})，正在挂起工作流等待人工审批。")
            return True
        return False

    @staticmethod
    def should_trigger_critic(state: Dict[str, Any]) -> bool:
        """
        判断是否需要触发 CRITIC 自愈节点
        """
        messages = state.get("messages", [])
        if not messages: return False
        
        last_msg = messages[-1]
        
        # 如果是 AI 消息，进行质量评估
        if isinstance(last_msg, AIMessage):
            # 如果有显式错误日志，直接触发
            if state.get("error_log"):
                return True
                
            # 否则通过元数据门控评估
            confidence = QualityGate.evaluate_response(last_msg)
            if confidence < 0.5:
                logger.info(f"🔄 [Gate] 信心值过低 ({confidence:.2f})，触发 CRITIC 自愈。")
                return True
                
        return False
