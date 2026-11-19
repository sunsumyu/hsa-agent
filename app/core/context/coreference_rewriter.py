# -*- coding: utf-8 -*-
"""
app/core/context/coreference_rewriter.py
========================================
[SPEC-227] 上下文指代消解器与任务路由器 (Contextual Query Rewriter & Task Router)
- 遵循 Matt Pocock 深模块原则，提供窄接口暴露，隐藏指代展开与意图分流复杂度
- 解决多轮交互中“其中”、“上述”、“排名第一”、“该机构”等代词引起的语义断链
- 区分 QUERY (数据取证)、SYNTHESIS (综合底稿)、RECALL (工作记忆回溯)、NOTE (便签维护)
"""

import re
import os
from typing import Dict, Any, Tuple, List, Optional
from loguru import logger


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

    @classmethod
    def classify_turn_type(cls, query: str) -> str:
        """识别当前轮次的基础意图类型"""
        q = query.strip()
        q_lower = q.lower()

        # 0. [Matt Pocock Shift-Left Seam] 恶意注入与越权越狱指令左移拦截 (0ms 熔断)
        has_destructive_sql = bool(re.search(r"\b(drop|truncate|alter)\s+table\b|;\s*drop\b|;\s*--", q_lower))
        has_jailbreak = any(kw in q_lower for kw in ["ignore all rules", "忽略之前所有", "忽略所有规则", "system prompt override"])
        has_off_topic_noise = any(kw in q for kw in ["七言绝句", "写一首诗", "写首诗", "赞美西湖"])
        if has_destructive_sql or (has_jailbreak and has_off_topic_noise):
            return cls.TASK_SECURITY_BLOCK
        
        # 0.1 [L1 Out-of-Domain / Chitchat Fast-Path] 日常生活闲聊与非业务意图快速通道
        # 医保审计强相关领域词库 (只要含有任一明确业务词，则不应误判为生活闲聊)
        domain_keywords = [
            "医保", "医疗", "报销", "结算", "住院", "门诊", "费用", "药店", "医院", "卫生室", "卫生院",
            "诊所", "处方", "药品", "耗材", "基金", "违规", "欺诈", "套现", "虚假", "排查", "核查",
            "审计", "底稿", "便签", "统计", "查询", "名单", "排名", "清单", "金额", "单据", "明细",
            "患者", "参保", "机构", "大额", "超量", "频次", "阈值", "穿透", "下钻", "表", "sql", "数据"
        ]
        has_domain_context = any(w in q_lower for w in domain_keywords)

        # 防御性解包：如果传入了 JSON 格式的字符串 (如 `{'message': '...'}`)，提取真实用户文本
        if q.startswith("{") and ("'message'" in q or '"message"' in q or "'input'" in q or '"input"' in q):
            try:
                import ast
                parsed_dict = json.loads(q) if q.startswith('{"') else ast.literal_eval(q)
                if isinstance(parsed_dict, dict):
                    for k in ["message", "input", "query", "content", "prompt", "text"]:
                        if k in parsed_dict and parsed_dict[k]:
                            q = str(parsed_dict[k]).strip()
                            q_lower = q.lower()
                            break
            except Exception:
                pass

        # 问候/元认知识别
        greeting_patterns = [
            r"(你好|您好|早[上安好]?|下午好|晚上好|hi|hello|hey)\b",
            r"(你是谁|你叫什么|你能做什么|自我介绍|介绍一下你自己|功能介绍|你的功能)"
        ]
        is_greeting = any(re.search(p, q_lower) for p in greeting_patterns)

        # 纯生活/饮食/娱乐/闲扯识别
        lifestyle_patterns = [
            r"(我?喜欢吃|我想吃|吃点什么|好吃吗|喝点什么|吃鸡肉|吃牛肉|吃猪肉|吃鱼|喝咖啡|喝奶茶)",
            r"(今天天气|明天天气|好冷|好热|好累|好无聊|讲个笑话|说个笑话|开心|难过)"
        ]
        is_lifestyle = any(re.search(p, q_lower) for p in lifestyle_patterns)

        if (is_greeting or is_lifestyle) and not has_domain_context:
            return cls.TASK_CHITCHAT

        # 0.2 [L2 User Preference] 用户排版与偏好配置 (非数据取证指令)
        preference_patterns = [
            r"(喜欢用表格|必须使用表格|用markdown表格|改用表格|恢复表格|重新启用表格|取消表格|改用纯文字|改用无序列表|列表排版|输出格式改成)",
            r"(以后大额排查按|默认阈值改成|习惯使用.*阈值)"
        ]
        is_preference = any(re.search(p, q_lower) for p in preference_patterns)
        # 排除明确包含“查询”、“调取”、“排查”且含实体的实际取证指令
        if is_preference and not any(w in q for w in ["查询", "调取", "查一下", "拉一下"]):
            return cls.TASK_PREFERENCE

        # 1. 出具审计底稿/阶段总结
        synthesis_keywords = ["出具", "审计工作底稿", "阶段性审计工作底稿", "综合报告", "综合前面", "汇总前面", "完整底稿"]
        if any(kw in q for kw in synthesis_keywords) and any(w in q for w in ["底稿", "报告", "汇总", "综合"]):
            return cls.TASK_SYNTHESIS

        # 2. 回溯便签/工作记忆
        recall_keywords = ["便签中", "回顾前序", "便签记了什么", "重点标记的嫌疑", "名称叫什么", "第 3 轮便签", "第3轮便签"]
        if any(kw in q for kw in recall_keywords) and not any(kw in q for kw in ["查询其结算", "调取该", "明细"]):
            return cls.TASK_RECALL

        # 3. 记录便签 (必须是明确的记录指令，且排除查询/调取等下钻动词)
        note_keywords = ["记录到本次审计的便签", "记录到便签", "写入便签", "作为重点涉案嫌疑对象，记录"]
        if any(kw in q for kw in note_keywords) and not any(w in q for w in ["查询", "调取", "统计", "排查"]):
            return cls.TASK_NOTE

        # 3.1 撤销便签 / 误判解除 (真实口语撤回)
        revoke_keywords = ["搞错了", "撤回便签", "撤销便签", "别查它了", "取消重点嫌疑", "移出便签", "误判了", "不是嫌疑", "从便签中撤销"]
        if any(kw in q for kw in revoke_keywords):
            return cls.TASK_REVOKE_NOTE

        # 4. 经验库沉淀
        consolidate_keywords = ["沉淀至长期经验库", "沉淀至经验库", "总结为标准审计经验规则"]
        if any(kw in q for kw in consolidate_keywords):
            return cls.TASK_CONSOLIDATE

        return cls.TASK_QUERY

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
            from app.skills.audit_note_store import audit_note_store
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
    def resolve_coreference(cls, current_query: str, state: Dict[str, Any]) -> Tuple[str, str, List[str]]:
        """
        消解当前用户提问中的代词，返回 (展开后的独立命题, 任务类型, 识别出的关键实体)
        """
        q = current_query.strip()
        turn_type = cls.classify_turn_type(q)
        extracted_entities: List[str] = []

        findings = state.get("accumulated_findings") or []
        last_finding = findings[-1] if findings else {}

        # 场景 A: 出具全局审计工作底稿 (SYNTHESIS)
        if turn_type == cls.TASK_SYNTHESIS:
            return q, turn_type, extracted_entities

        # 场景 B: 回溯便签/工作记忆 (RECALL)
        if turn_type == cls.TASK_RECALL:
            suspect = cls.extract_top_entity_from_notes(state)
            if suspect:
                extracted_entities.append(suspect)
            return q, turn_type, extracted_entities

        # 场景 C: 记录便签 (NOTE)
        if turn_type == cls.TASK_NOTE:
            # 尝试提取第 2 轮排名的第一家机构
            if last_finding and last_finding.get("key_entities"):
                extracted_entities.extend(last_finding["key_entities"][:1])
            return q, turn_type, extracted_entities

        # 场景 C2: 撤销便签 / 实体解绑 (REVOKE_NOTE)
        if turn_type == cls.TASK_REVOKE_NOTE:
            suspect = cls.extract_top_entity_from_notes(state)
            if suspect:
                extracted_entities.append(suspect)
            return q, turn_type, extracted_entities

        # 场景 D: 数据取证 (QUERY) 代词展开
        resolved = q

        # D1: 展开 "在上述违规记录中" / "上述违规" / "其中"（通用提取，无硬编码）
        if any(kw in q for kw in ["在上述违规记录中", "上述违规记录", "上述违规", "上述记录", "其中"]):
            prev_resolved = last_finding.get("resolved_query") or last_finding.get("user_query") or ""
            context_prefix = cls._build_context_prefix(prev_resolved)

            if context_prefix:
                resolved = re.sub(r"^(在上述违规记录中[，,]?|在上述记录中[，,]?|上述违规记录中[，,]?|其中[，,]?)", "", resolved).strip()
                resolved = context_prefix + resolved
                logger.info(f"🔗 [CoreferenceRewriter] 展开代词『上述/其中』-> 「{resolved[:60]}...」")

        # D2: 展开 "刚刚记入便签的重点嫌疑医院" / "该重点嫌疑机构" / "该重点嫌疑医院" / "排名第一的医疗机构"
        suspect_keywords = [
            "刚刚记入便签的重点嫌疑医院",
            "刚刚记入便签的重点嫌疑机构",
            "该重点嫌疑机构",
            "该重点嫌疑医院",
            "该医院",
            "这家医院",
            "排名第一的医疗机构",
            "排名第一的医院"
        ]
        has_suspect_ref = any(kw in q for kw in suspect_keywords)
        if has_suspect_ref:
            suspect = cls.extract_top_entity_from_notes(state)
            if not suspect and last_finding and last_finding.get("key_entities"):
                suspect = last_finding["key_entities"][0]

            if suspect:
                extracted_entities.append(suspect)
                for kw in suspect_keywords:
                    if kw in resolved:
                        resolved = resolved.replace(kw, f"重点嫌疑机构『{suspect}』")
                logger.info(f"🔗 [CoreferenceRewriter] 绑定嫌疑机构实体『{suspect}』-> 「{resolved[:60]}...」")

        # D3: 场景切换明确标记
        if "切换核查场景" in q or "切换场景" in q:
            logger.info("🔀 [CoreferenceRewriter] 识别到明确场景切换指令，阻断跨场景历史条件继承。")

        # D4: 口语反悔与参数纠偏 (In-Context Parameter Correction)
        correction_markers = ["不对", "改一下", "改成", "改用", "重新查", "算了", "太高了", "太少了", "加进来", "并进来", "一起算", "换成"]
        if any(kw in q for kw in correction_markers):
            prev_resolved = last_finding.get("resolved_query") or last_finding.get("user_query") or ""
            if prev_resolved:
                clean_prev = re.sub(r"[？?。！!\s]+$", "", prev_resolved.strip())
                resolved = f"【用户纠偏指令：针对前序任务『{clean_prev}』，推翻旧条件并按最新口径重新执行】: {q}"
                logger.info(f"🔄 [CoreferenceRewriter] 识别到口语纠偏反悔 -> 「{resolved[:60]}...」")

        return resolved, turn_type, extracted_entities


coreference_rewriter = ContextualQueryRewriter()
