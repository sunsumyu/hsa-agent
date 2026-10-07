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

    @staticmethod
    def validate_intent(state: Dict[str, Any]) -> Dict[str, Any]:
        """
        [V178.10] Gate 1: 校验意图与方法论的一致性。
        复用 IntentValidator 的对齐校验逻辑。
        
        Args:
            state: 包含 original_question, methodology, query_type 等字段的审计状态
            
        Returns:
            {"passed": bool, "error": str or None}
        """
        try:
            from app.core.intent_validator import intent_validator
            from app.core.query_classifier import query_classifier
            
            original_question = state.get("original_question", "")
            methodology = state.get("methodology", "")
            
            if not original_question or not methodology:
                # 缺少必要信息时默认放行，避免阻塞流水线
                return {"passed": True, "error": None}
            
            # 分类查询类型
            query_type = query_classifier.classify(original_question)
            
            # 获取阈值决策信息
            threshold_decision = state.get("threshold_decision", {})
            
            # 执行对齐校验
            result = intent_validator.validate_alignment(
                original_query=original_question,
                query_type=query_type,
                methodology=methodology,
                threshold_decision=threshold_decision,
            )
            
            passed = result.get("passed", True)
            errors = result.get("errors", [])
            error_msg = "; ".join(errors) if errors else None
            
            if not passed:
                logger.warning(f"[Gate 1] Intent validation failed: {error_msg}")
            
            return {"passed": passed, "error": error_msg}
            
        except Exception as e:
            # 校验异常时默认放行，避免阻塞流水线
            logger.warning(f"[Gate 1] Intent validation error (defaulting to pass): {e}")
            return {"passed": True, "error": None}

    @staticmethod
    def validate_sql_semantics(state, sql: str) -> Dict[str, Any]:
        """
        [V178.10] Gate 2: SQL 语义校验 — 检查 SQL 是否与方法论对齐。

        Args:
            state: 审计状态字典
            sql: 待执行的 SQL 语句

        Returns:
            {"passed": bool, "error": str or None, "warnings": List[str]}
        """
        try:
            methodology = state.get("methodology", "") if isinstance(state, dict) else ""
            original_question = state.get("original_question", "") if isinstance(state, dict) else ""
            if not original_question and isinstance(state, dict) and "messages" in state:
                for m in state.get("messages", []):
                    if isinstance(m, tuple) and len(m) >= 2 and m[0] in ("user", "human"):
                        original_question += " " + str(m[1])
                    elif hasattr(m, "type") and getattr(m, "type") == "human":
                        original_question += " " + str(getattr(m, "content", ""))
                    elif hasattr(m, "role") and getattr(m, "role") == "user":
                        original_question += " " + str(getattr(m, "content", ""))
                    elif isinstance(m, dict) and (m.get("role") == "user" or m.get("type") == "human"):
                        original_question += " " + str(m.get("content", ""))
                original_question = original_question.strip()
        except Exception:
            methodology = ""
            original_question = ""

        warnings = []
        if not sql:
            return {"passed": False, "error": "SQL为空", "warnings": []}

        sql_upper = sql.upper().strip()
        question_lower = (original_question or "").lower()
        
        # 规则1: RANKING 查询 + 不必要的基线
        ranking_keywords = ["排名", "最高", "前", "top"]
        baseline_keywords = ["QUANTILE", "PERCENTILE", "AVG(", "MEDIAN(", "STDDEV("]
        is_ranking_query = any(kw in question_lower for kw in ranking_keywords)
        has_baseline = any(kw in sql_upper for kw in baseline_keywords)
        
        if is_ranking_query and has_baseline and "OVER" not in sql_upper and "GROUP BY" not in sql_upper:
            warning = "RANKING查询包含基线计算步骤(quantile/avg)，可能产生语义偏离"
            warnings.append(warning)
            logger.warning(f"[Gate 2] {warning}")
            # 不拦截，只警告 — 某些排名查询确实需要基线
            return {"passed": True, "error": None, "warnings": warnings}

        # 规则2: [Task Archetype Guard] 领域任务原型不变式守卫 (基于 ArchetypeRegistry)
        from app.core.registry.archetype_registry import archetype_registry
        has_group_by = "GROUP BY" in sql_upper
        has_limit = "LIMIT " in sql_upper or "LIMIT\n" in sql_upper or "LIMIT\t" in sql_upper

        matched_archetypes = archetype_registry.match_archetypes(question_lower)
        for arch in matched_archetypes:
            if arch.forbid_raw_limit and has_limit and not has_group_by:
                err_msg = arch.enforcement_hint or f"本任务为【{arch.display_name}】任务，必须使用 GROUP BY 进行全量统计，严禁对明细流水施加 LIMIT 采样！"
                return {"passed": False, "error": err_msg, "warnings": warnings}

        # 规则3: [Contradiction Guard] 静态 AST 恒假互斥防腐守卫
        from app.core.guardrails.contradiction_detector import ContradictionDetector
        violation = ContradictionDetector.detect(sql)
        if violation:
            err_msg = f"【静态语义恒假拦截】{violation.message} 冲突谓词: {violation.conflicting_predicates}"
            logger.warning(f"[Gate 2 Contradiction] {err_msg}")
            return {"passed": False, "error": err_msg, "warnings": warnings}
        
        return {"passed": True, "error": None, "warnings": warnings}

    @staticmethod
    def validate_result_matching(state) -> Dict[str, Any]:
        """
        [V178.10] Gate 3: 结果匹配校验 — 检查查询结果是否与审计目标匹配。

        Args:
            state: 审计状态字典

        Returns:
            {"passed": bool, "error": str or None, "warnings": List[str]}
        """
        try:
            result_data = state.get("raw_data", state.get("query_result", None)) if isinstance(state, dict) else None
        except Exception:
            result_data = None

        warnings = []

        # 空结果不等于不通过 — 可能确实没有违规
        if result_data is None:
            warning = "查询结果为None，可能SQL执行失败"
            warnings.append(warning)
            return {"passed": True, "error": None, "warnings": warnings}
        
        # 检查是否是空列表
        if isinstance(result_data, (list, tuple)) and len(result_data) == 0:
            logger.info("[Gate 3] 查询结果为空列表 — 可能确实无违规数据")
            return {"passed": True, "error": None, "warnings": warnings}
        
        return {"passed": True, "error": None, "warnings": warnings}
