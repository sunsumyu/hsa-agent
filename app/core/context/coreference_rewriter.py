# -*- coding: utf-8 -*-
"""
app/core/context/coreference_rewriter.py
========================================
[SPEC-227] 上下文指代消解器与任务路由器 (Contextual Query Rewriter & Task Router)
- 遵循 Matt Pocock 深模块原则，提供窄接口暴露，隐藏指代展开与意图分流复杂度
- 解决多轮交互中“其中”、“上述”、“排名第一”、“该机构”等代词引起的语义断链
- 区分 QUERY (数据取证)、SYNTHESIS (综合底稿)、RECALL (工作记忆回溯)、NOTE (便签维护)

[V228 重构] resolve_coreference 管道化：
- 拆解为三段：意图分类 -> 实体绑定注册表(按意图) -> 取证命题改写规则管道(仅 QUERY)
- 每条改写规则内聚「触发->剥除->改写」原子闭环：触发必可剥除，剥除必生效才改写，
  杜绝句中『其中』等非句首指代误触发上下文前置（旧 D1 缺陷）
- 非 QUERY 意图（CHITCHAT/PREFERENCE/CONSOLIDATE/SECURITY_BLOCK）不再进入改写管道
- 返回契约由裸三元组升级为 TurnAnalysis 数据类（迭代解包向后兼容），新增
  signals / matched_rules 结构化字段，使『场景切换』等纯信号规则显式可消费
"""

import re
from typing import Dict, Any, Tuple, List, Optional
from loguru import logger

from app.core.context.coreference_rules import (
    SIGNAL_ANAPHORA_EXPANDED,
    SIGNAL_SUSPECT_BOUND,
    SIGNAL_SCENE_SWITCH,
    SIGNAL_CORRECTION,
    TurnAnalysis,
    RewriteContext,
    RuleOutcome,
    _RewriteRule,
    _AnaphoraExpansionRule,
    _SuspectEntityRule,
    _SceneSwitchSignalRule,
    _CorrectionWrapRule,
    _REWRITE_PIPELINE,
    _run_rewrite_pipeline,
)


class ContextualQueryRewriter:
    """轻量确定性上下文指代消解与任务意图分类引擎"""

    # 任务类型常量
    TASK_QUERY = "QUERY"
    TASK_SYNTHESIS = "SYNTHESIS"
    TASK_RECALL = "RECALL"
    TASK_NOTE = "NOTE"
    TASK_REVOKE_NOTE = "REVOKE_NOTE"
    TASK_PREFERENCE = "PREFERENCE"
    TASK_CHITCHAT = "CHITCHAT"
    TASK_CONSOLIDATE = "CONSOLIDATE"
    TASK_SECURITY_BLOCK = "SECURITY_BLOCK"

    _DOMAIN_KEYWORDS = (
        "医保", "医疗", "报销", "结算", "住院", "门诊", "费用", "药店", "医院", "卫生室", "卫生院",
        "诊所", "处方", "药品", "耗材", "基金", "违规", "欺诈", "套现", "虚假", "排查", "核查",
        "审计", "底稿", "便签", "统计", "查询", "名单", "排名", "清单", "金额", "单据", "明细",
        "患者", "参保", "机构", "大额", "超量", "频次", "阈值", "穿透", "下钻", "表", "sql", "数据",
    )

    @classmethod
    def _is_security_violation(cls, q: str, q_lower: str) -> bool:
        q_norm = re.sub(r"/\*.*?\*/", " ", q_lower).replace("；", ";")
        has_destructive_sql = bool(re.search(
            r"\b(drop|truncate|alter|rename)\s+(table|database|dictionary|view|column)\b"
            r"|\bcreate\s+(table|database|dictionary|view)\b"
            r"|\b(delete\s+from|insert\s+into)\b"
            r"|\bupdate\s+[a-zA-Z0-9_.]+\s+set\b"
            r"|\bgrant\s+.*\s+to\b|\brevoke\s+.*\s+from\b|\bkill\s+query\b"
            r"|\bsystem\s+(reload|drop|shutdown|flush|sync)\b|\bset\s+readonly\s*=\s*0\b"
            r"|;\s*(drop|delete|insert|update|create|alter|truncate|grant|revoke|kill|system|rename|set\s+readonly)\b"
            r"|;\s*(--|#)",
            q_norm,
        ))
        has_direct_jailbreak = bool(re.search(
            r"\bignore\s+(all\s+rules|previous\s+instructions|all\s+previous)\b"
            r"|\b(system\s+prompt\s+override|system\s+instruction)\b"
            r"|\bdisregard\s+all\s+(previous|safety)\b|\b(dan\s+mode|developer\s+mode)\b"
            r"|忽略(?:之前的?|全部)?(?:所有|全部)(?:规则|设定|指令|限制)"
            r"|无视所有(安全|合规|系统)?(限制|规则|要求|审查)"
            r"|从现在[起开始].*(开发者模式|没有任何限制|扮演.*黑客)|\[system\s+message:.*\]|<system>.*</system>",
            q_norm,
        ))
        has_jb_kw = any(kw in q_lower for kw in ("ignore all rules", "忽略之前所有", "忽略所有规则", "system prompt override"))
        has_noise = any(kw in q for kw in ("七言绝句", "写一首诗", "写首诗", "赞美西湖", "write a poem", "write me a poem"))
        return has_destructive_sql or has_direct_jailbreak or (has_jb_kw and has_noise)

    @classmethod
    def _unwrap_json_query(cls, q: str) -> str:
        if not (q.startswith("{") and ("'message'" in q or '"message"' in q or "'input'" in q or '"input"' in q)):
            return q
        try:
            import ast
            parsed_dict = ast.literal_eval(q)
            if isinstance(parsed_dict, dict):
                for k in ("message", "input", "query", "content", "prompt", "text"):
                    if k in parsed_dict and parsed_dict[k]:
                        return str(parsed_dict[k]).strip()
        except (ValueError, SyntaxError, TypeError) as exc:
            logger.debug(f"[CoreferenceRewriter] JSON payload unwrap skipped: {exc}")
        return q

    @classmethod
    def _is_chitchat_turn(cls, q_lower: str, has_domain_context: bool) -> bool:
        if has_domain_context:
            return False
        chitchat_patterns = (
            r"(你好|您好|早[上安好]?|下午好|晚上好|hi|hello|hey)\b",
            r"(你是谁|你叫什么|你能做什么|自我介绍|介绍一下你自己|功能介绍|你的功能)",
            r"(我?喜欢吃|我想吃|吃点什么|好吃吗|喝点什么|吃鸡肉|吃牛肉|吃猪肉|吃鱼|喝咖啡|喝奶茶)",
            r"(今天天气|明天天气|好冷|好热|好累|好无聊|讲个笑话|说个笑话|开心|难过)",
        )
        return any(re.search(p, q_lower) for p in chitchat_patterns)

    @classmethod
    def _classify_workflow_intent(cls, q: str, q_lower: str) -> str:
        pref_patterns = (
            r"(喜欢用表格|必须使用表格|用markdown表格|改用表格|恢复表格|重新启用表格|取消表格|改用纯文字|改用无序列表|列表排版|输出格式改成)",
            r"(以后大额排查按|默认阈值改成|习惯使用.*阈值)",
        )
        if any(re.search(p, q_lower) for p in pref_patterns) and not any(w in q for w in ("查询", "调取", "查一下", "拉一下")):
            return cls.TASK_PREFERENCE
        if any(kw in q for kw in ("出具", "审计工作底稿", "阶段性审计工作底稿", "综合报告", "综合前面", "汇总前面", "完整底稿")) and any(
            w in q for w in ("底稿", "报告", "汇总", "综合")
        ):
            return cls.TASK_SYNTHESIS
        if any(kw in q for kw in ("搞错了", "撤回便签", "撤销便签", "别查它了", "取消重点嫌疑", "移出便签", "误判了", "不是嫌疑", "从便签中撤销")):
            return cls.TASK_REVOKE_NOTE
        if any(kw in q for kw in ("便签中", "回顾前序", "便签记了什么", "重点标记的嫌疑", "名称叫什么", "第 3 轮便签", "第3轮便签")) and not any(
            w in q for w in ("查询其结算", "调取该", "明细")
        ):
            return cls.TASK_RECALL
        if any(kw in q for kw in ("记录到本次审计的便签", "记录到便签", "写入便签", "作为重点涉案嫌疑对象，记录")) and not any(
            w in q for w in ("查询", "调取", "统计", "排查")
        ):
            return cls.TASK_NOTE
        if any(kw in q for kw in ("沉淀至长期经验库", "沉淀至经验库", "总结为标准审计经验规则")):
            return cls.TASK_CONSOLIDATE
        return cls.TASK_QUERY

    @classmethod
    def classify_turn_type(cls, query: str) -> str:
        """识别当前轮次的基础意图类型"""
        q = query.strip()
        q_lower = q.lower()
        if cls._is_security_violation(q, q_lower):
            return cls.TASK_SECURITY_BLOCK

        has_domain_context = any(w in q_lower for w in cls._DOMAIN_KEYWORDS)
        q = cls._unwrap_json_query(q)
        q_lower = q.lower()
        if cls._is_chitchat_turn(q_lower, has_domain_context):
            return cls.TASK_CHITCHAT
        return cls._classify_workflow_intent(q, q_lower)

    @classmethod
    def extract_top_entity_from_notes(cls, state: Dict[str, Any]) -> Optional[str]:
        """从便签簿或历史便签文件中提取最近标记的嫌疑实体名称"""
        medical_suffixes = ["医院", "卫生院", "诊所", "中心", "门诊部", "卫生室", "药房", "药店"]
        invalid_patterns = [
            "第一的", "第二的", "第三的", "涉案金额第一", "排名第一", "金额第一", 
            "涉案第一", "金额最高", "重点涉案", "重点嫌疑", "涉案金额最高", 
            "这家医院", "该机构", "该医院", "上述机构", "上述医院"
        ]

        def _is_valid_entity(name: str) -> bool:
            if not name or len(name) < 4:
                return False
            name = name.strip()
            # 排除指代性代词与相对修饰语 (允许第一人民医院等真实合法命名)
            if any(p in name for p in invalid_patterns):
                return False
            return any(s in name for s in medical_suffixes)

        # 1. 优先从内存 audit_notes 状态提取括号中的具体机构名称
        notes = state.get("audit_notes") or []
        for note in reversed(notes):
            m_paren = re.search(r"[（(]([^\s，。：()（）]+(?:医院|卫生院|诊所|中心|门诊部|卫生室|药房|药店))[)）]", note)
            if m_paren and _is_valid_entity(m_paren.group(1)):
                return m_paren.group(1).strip()
            m = re.search(r"【重点线索】.*?([^\s，。：()（）]+(?:医院|卫生院|诊所|中心|门诊部|卫生室|药房|药店))", note)
            if m and _is_valid_entity(m.group(1)):
                return m.group(1).strip()
            m2 = re.search(r"嫌疑对象[：:\s]*([^\s，。]+)", note)
            if m2 and _is_valid_entity(m2.group(1)):
                return m2.group(1).strip()

        # 2. 仅在内存无便签且非会话隔离模式时，检查物理便签文件
        if not notes:
            from app.skills.federated.audit_note_store import audit_note_store
            content = audit_note_store.read_raw_text()
            if content:
                m_paren = re.findall(r"[（(]([^\s，。：()（）]+(?:医院|卫生院|诊所|中心|门诊部|卫生室|药房|药店))[)）]", content)
                for cand in reversed(m_paren):
                    if _is_valid_entity(cand):
                        return cand.strip()
                matches = re.findall(r"【重点线索】.*?([^\s，。：()（）]+(?:医院|卫生院|诊所|中心|门诊部|卫生室|药房|药店))", content)
                for cand in reversed(matches):
                    if _is_valid_entity(cand):
                        return cand.strip()

        # 3. 从 accumulated_findings 提取真实物理实体（坚固的单一事实源保底）
        findings = state.get("accumulated_findings") or []
        for finding in reversed(findings):
            entities = finding.get("key_entities", [])
            for e in entities:
                cand = str(e).strip()
                if _is_valid_entity(cand):
                    return cand

        return None

    @classmethod
    def _build_context_prefix(cls, prev_query: str) -> str:
        """
        [SPEC-227 工业级通用消解] 动态从上一轮任务命题中提取限定从句，严禁任何业务词硬编码。
        通用适配任意场景：男性妇科、儿童成人药、重复住院、分解住院、高额耗材、大额结算等。
        """
        if not prev_query:
            return ""

        # 1. 清洗末尾问号及标点
        cleaned = re.sub(r"[？?。！!\s]+$", "", str(prev_query).strip())

        # 2. 剥离口语化祈使动词前缀
        action_prefixes = [
            r"^请(?:重点)?(?:排查|核查|调查|查询|调取|统计|分析)",
            r"^帮我(?:拉一下|查一下|调取|统计|看下|看看)",
            r"^查一下",
            r"^查询",
            r"^拉一下",
            r"^先帮我",
        ]
        for pattern in action_prefixes:
            cleaned = re.sub(pattern, "", cleaned).strip()

        # 3. 剥离“是否存在”与“的情况”
        cleaned = re.sub(r"^是否存在", "", cleaned).strip()
        cleaned = re.sub(r"(?:的情况|的违规情况|的违规记录)$", "", cleaned).strip()

        # 4. 根据语法形态动态组装从句
        if cleaned.startswith("在") and (cleaned.endswith("中") or "违规记录中" in cleaned):
            return f"{cleaned}，"
        elif cleaned.startswith("在"):
            return f"{cleaned}的违规记录中，"
        else:
            return f"在『{cleaned}』的违规记录中，"

    @classmethod
    def resolve_coreference(cls, current_query: str, state: Dict[str, Any]) -> TurnAnalysis:
        """
        消解当前用户提问中的代词，产出 TurnAnalysis（意图分类 + 命题消解 + 实体绑定 + 管道信号）。
        兼容旧三元组解包：`query, turn_type, entities = resolve_coreference(...)`。

        三段式结构：
        1. 意图分类 -> 命题原样透传，实体按意图绑定注册表提取；
        2. 取证意图 (QUERY) -> 命题改写规则管道（anaphora -> suspect -> scene_switch -> correction）；
        3. 其余非取证意图 -> 不做命题改写（旧实现误入改写链，已修正）。
        """
        q = current_query.strip()
        turn_type = cls.classify_turn_type(q)

        findings = state.get("accumulated_findings") or []
        last_finding = findings[-1] if findings else {}

        # 1. 非取证意图：命题原样透传，实体按意图绑定器提取
        binder = _TURN_TYPE_ENTITY_BINDERS.get(turn_type)
        if binder is not None:
            return TurnAnalysis(query=q, turn_type=turn_type,
                                entities=tuple(binder(state, last_finding)))

        # 2. 取证意图 (QUERY)：走命题改写规则管道
        if turn_type == cls.TASK_QUERY:
            ctx = RewriteContext(
                original_query=q,
                state=state,
                last_finding=last_finding,
                prev_resolved=last_finding.get("resolved_query") or last_finding.get("user_query") or "",
                prefix_builder=cls._build_context_prefix,
                entity_extractor=cls.extract_top_entity_from_notes,
            )
            resolved, matched_rules, signals, entities = _run_rewrite_pipeline(q, ctx)
            return TurnAnalysis(
                query=resolved,
                turn_type=turn_type,
                entities=tuple(entities),
                signals=signals,
                matched_rules=tuple(matched_rules),
            )

        # 3. 其余意图（CHITCHAT/PREFERENCE/CONSOLIDATE/SECURITY_BLOCK）：不做取证命题改写
        return TurnAnalysis(query=q, turn_type=turn_type)

    _UNRESOLVED_ANAPHORA_MARKERS: Tuple[str, ...] = (
        "它", "他", "她", "这家", "那家", "这个", "那个", "那几个", "这几个",
        "第二名", "第三名", "前几名", "刚才", "上面", "前面", "前一个", "上一个",
        "其余", "另外", "后者", "前者", "那批", "这批", "再查下", "再看看",
    )

    @classmethod
    def needs_llm_coreference_fallback(
        cls,
        raw_query: str,
        resolved_query: str,
        turn_type: str,
        state: Dict[str, Any],
    ) -> bool:
        """
        条件兜底门控：仅当正则未改写、属于取证查询、存在前序上下文且句子含未消解指代/过短残缺时，
        才触发轻量 LLM 上下文指代改写；常规直白查询保持 0ms / 0 Token 零开销。
        """
        if turn_type != cls.TASK_QUERY:
            return False
        q = (raw_query or "").strip()
        if not q or resolved_query.strip() != q:
            return False

        msgs = state.get("messages") or []
        findings = state.get("accumulated_findings") or []
        if len(msgs) < 2 and not findings:
            return False

        has_marker = any(marker in q for marker in cls._UNRESOLVED_ANAPHORA_MARKERS)
        is_short_fragment = len(q) <= 10
        return has_marker or is_short_fragment

    @classmethod
    async def llm_fallback_rewrite(
        cls,
        raw_query: str,
        state: Dict[str, Any],
        config: Any = None,
    ) -> str:
        """
        [长尾指代兜底] 调用轻量模型结合最近几轮上下文将残缺指代句改写为自包含审计命题。
        任何异常均安全降级为原句，绝不阻断主流程。
        """
        q = (raw_query or "").strip()
        try:
            from langchain_core.messages import SystemMessage, HumanMessage
            from app.core.llm_provider import llm_provider

            history_lines: List[str] = []
            for msg in (state.get("messages") or [])[-4:]:
                role_name = getattr(msg, "type", msg.__class__.__name__)
                content = str(getattr(msg, "content", "") or "").strip()
                if content:
                    history_lines.append(f"[{role_name}]: {content[:240]}")

            findings = state.get("accumulated_findings") or []
            if findings:
                last_f = findings[-1]
                prev_q = last_f.get("resolved_query") or last_f.get("user_query")
                ents = last_f.get("key_entities") or []
                if prev_q or ents:
                    history_lines.append(f"[最近取证上下文]: 命题={prev_q} | 实体={ents}")

            history_block = "\n".join(history_lines) if history_lines else "无"
            prompt_msgs = [
                SystemMessage(
                    content=(
                        "你是医保审计系统的指代消解助手。请结合对话历史，把用户当前包含代词或省略主语的提问，"
                        "改写为一句主语完整、独立清晰的中文审计查询命题。\n"
                        "要求：1) 只输出改写后的单句，不要解释；2) 严禁臆造历史中不存在的机构名、金额或时间条件；"
                        "3) 若无法确定指代对象，原样返回当前提问。"
                    )
                ),
                HumanMessage(
                    content=f"对话历史：\n{history_block}\n\n当前用户提问：{q}\n\n改写后的独立命题："
                ),
            ]

            resp = await llm_provider.chat(
                role="planner_light",
                messages=prompt_msgs,
                config=config,
                temperature=0.0,
            )
            rewritten = str(getattr(resp, "content", "") or "").strip().strip("「」\"'")
            if rewritten and len(rewritten) <= 300:
                logger.info(f"🪄 [CoreferenceFallback] 轻量 LLM 长尾消解: 「{q}」 -> 「{rewritten[:60]}」")
                return rewritten
        except Exception as e:
            logger.warning(f"⚠️ [CoreferenceFallback] 轻量 LLM 消解降级为原句: {e}")
        return q


# ============ 意图->实体绑定注册表（"每种意图从哪取实体"的知识收敛于一处） ============

def _bind_entities_from_notes(state: Dict[str, Any], last_finding: Dict[str, Any]) -> List[str]:
    """RECALL/REVOKE_NOTE：从便签簿提取最近标记的嫌疑实体"""
    suspect = ContextualQueryRewriter.extract_top_entity_from_notes(state)
    return [suspect] if suspect else []


def _bind_entities_from_last_finding(state: Dict[str, Any], last_finding: Dict[str, Any]) -> List[str]:
    """NOTE：从最近一轮取证发现中提取首个关键实体"""
    return list(last_finding.get("key_entities") or [])[:1]


_TURN_TYPE_ENTITY_BINDERS: Dict[str, Any] = {
    ContextualQueryRewriter.TASK_RECALL: _bind_entities_from_notes,
    ContextualQueryRewriter.TASK_REVOKE_NOTE: _bind_entities_from_notes,
    ContextualQueryRewriter.TASK_NOTE: _bind_entities_from_last_finding,
}


coreference_rewriter = ContextualQueryRewriter()
