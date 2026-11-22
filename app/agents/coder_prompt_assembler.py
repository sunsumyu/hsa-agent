"""
app/agents/coder_prompt_assembler.py
====================================
[Matt Pocock Deep Module & SSOT]
审计代码生成智能体 (Coder Agent) 上下文组装与 Prompt 渲染器。

核心职责：
1. 上下文自包含命题解析 (resolve_user_query SSOT)
2. 历史消息紧凑压缩与排版公文剔除 (compact_coder_messages)
3. 场景推荐主表与业务安全警示生成 (build_schema_hint)
4. 意图抽象规划与场景防漂移指导组装 (build_scenario_guidelines)
5. 联邦图谱本体按需加载与剪枝 (resolve_ontology_context)
6. 顶层端到端 Prompt 组装渲染 (assemble_coder_prompt)
"""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Dict, Any, List, Optional, Tuple
from loguru import logger
from langchain_core.messages import HumanMessage, AIMessage, BaseMessage

from app.core.prompts import CODER_PROMPT
from app.infra.neo4j_manager import neo4j_manager
from app.agents.sql_evidence_resolver import resolve_user_query

if TYPE_CHECKING:
    from app.core.planning.audit_intent_planner import AuditIntent


@dataclass
class CoderPromptPayload:
    """Coder Prompt 渲染产物数据契约"""
    prompt_messages: List[BaseMessage]
    user_query: str
    primary_table: str
    related_tables: List[str] = field(default_factory=list)
    is_graph_task: bool = False
    scenario_guidelines: str = ""
    audit_intent: Optional["AuditIntent"] = None

    def __iter__(self):
        """支持直接迭代 prompt_messages，无缝兼容现有 LLM 调用接口"""
        return iter(self.prompt_messages)

    def __len__(self):
        return len(self.prompt_messages)

    def __getitem__(self, index):
        return self.prompt_messages[index]


def compact_coder_messages(
    messages: Optional[List[BaseMessage]], 
    fallback_query: str
) -> List[BaseMessage]:
    """
    [SPEC-227 精简 Coder 上下文]
    Coder 聚焦于当前轮次自包含命题，剔除长篇排版公文，严防 Token 膨胀导致模型思考截断。
    - 保留 human / user 提问
    - 保留带有 tool_calls 的关键工具决策
    - 文本长度 > 300 的 AI 历史公文压缩为前 150 字符并附加归档标记
    - 列表为空时自动回退为以 fallback_query 为内容的 HumanMessage
    """
    coder_msgs: List[BaseMessage] = []
    for m in (messages or []):
        m_type = getattr(m, "type", m.__class__.__name__).lower()
        if m_type in ("human", "user"):
            coder_msgs.append(m)
        elif m_type in ("ai", "assistant"):
            c = str(getattr(m, "content", "") or "")
            if getattr(m, "tool_calls", None):
                coder_msgs.append(m)
            elif len(c) > 300:
                coder_msgs.append(AIMessage(content=c[:150] + "... [前序审计结论已归档]"))
            elif c:
                coder_msgs.append(m)
        else:
            coder_msgs.append(m)

    if not coder_msgs:
        coder_msgs = [HumanMessage(content=fallback_query)]

    return coder_msgs


def build_schema_hint(user_q: str) -> Tuple[str, str, List[str]]:
    """
    [Matt Pocock 确定性接缝 & SSOT]
    提取目标场景物理主表及推荐关系表，明确推荐主表名称。
    底层 ClickHouse 引擎严禁查询 sqlite_master、information_schema 等元数据表。
    返回: (schema_hint_str, primary_tbl, related_tables)
    """
    from app.core.scene_table_selector import scene_table_selector
    from app.core.registry.schema_registry import schema_registry

    primary_tbl, related_tbls = scene_table_selector.select_tables(user_q)
    tables_to_expose = [primary_tbl] + [t for t in related_tbls if t != primary_tbl]

    entry = schema_registry.get_table(primary_tbl)
    primary_desc = entry.description if entry else "核心主表"
    related_repr = ", ".join([f"`{t}`" for t in tables_to_expose[1:3]]) if len(tables_to_expose) > 1 else "无"

    schema_hint = (
        f"【目标场景推荐物理主表】: `{primary_tbl}` ({primary_desc})\n"
        f"【候选关联物理表】: {related_repr}\n"
        "各表的完整字段定义与业务约束已由上下文引擎挂载于 <database_schema_context>（单一事实源 SSOT）。\n"
        "⚠️ 严格提示：底层引擎为 ClickHouse，严禁查询 sqlite_master、information_schema 等元数据表！"
    )
    return schema_hint, primary_tbl, tables_to_expose[1:]


def build_scenario_guidelines(
    user_q: str,
    scene_enforcement: Optional[str] = None,
    audit_intent: Optional["AuditIntent"] = None,
) -> str:
    """
    [企业级 v2.0] 场景化 SQL 刚性防漂移指引注入。
    - 审计意图抽象规划 (Plan-and-Solve: 认知解耦)
    - 场景表格选择器刚性提示优先
    - 支持注入已消解的 AuditIntent，避免同轮重复抽取 (SSOT)
    """
    scenario_guidelines = ""

    from app.core.planning.audit_intent_planner import AuditIntentPlanner
    if audit_intent is None:
        audit_intent = AuditIntentPlanner.extract_intent(user_q)
    if audit_intent.enforcement_guidance:
        scenario_guidelines += f"\n\n{audit_intent.enforcement_guidance}\n"

    if not scene_enforcement and user_q:
        from app.core.scene_table_selector import scene_table_selector
        scene_enforcement = scene_table_selector.get_enforcement_hint(user_q)

    if scene_enforcement:
        scenario_guidelines += scene_enforcement

    return scenario_guidelines.strip()


def resolve_ontology_context(user_q: str, methodology: str = "") -> str:
    """
    [Token 剪枝] 仅在涉及图谱团伙、手机号关联等联邦场景时注入庞大的 Neo4j 本体与 Cypher 模板。
    """
    is_graph_task = any(
        kw in user_q.lower() or kw in str(methodology or "").lower()
        for kw in ["团伙", "欺诈环", "共用", "联邦", "图谱", "多层关联", "graph", "cypher", "phone", "手机号"]
    )
    if is_graph_task:
        return neo4j_manager.get_ontology()
    return "（当前任务为单表/两表关系查询，暂无需加载图谱本体）"


def assemble_coder_prompt(
    state: Dict[str, Any], 
    metadata: Optional[Dict[str, Any]] = None
) -> CoderPromptPayload:
    """
    顶层深模块对外装配入口：
    接收 Agent 状态机 state 与 metadata，一次性输出 CoderPromptPayload 与格式化好的 Prompt 消息。
    """
    meta = metadata or state.get("metadata") or {}
    tasks_list = state.get("tasks", [])
    scene_enforcement = meta.get("scene_enforcement")

    # 1. 意图与当前轮自包含命题消解 (AuditIntent 单次抽取，作为 Payload 与场景指引的共同来源)
    user_q = resolve_user_query(state, max_chars=300)

    from app.core.planning.audit_intent_planner import AuditIntentPlanner
    audit_intent = AuditIntentPlanner.extract_intent(user_q)

    # 2. Schema 提示组装与主表提取
    schema_hint, primary_tbl, related_tbls = build_schema_hint(user_q)

    # 3. 经验与场景防漂移指引注入
    experiences_combined = "【已启用 GSSC 统一上下文引擎：相关的向量专家经验与外部便签线索已挂载于消息流尾部】"
    scenario_guidelines = build_scenario_guidelines(user_q, scene_enforcement, audit_intent=audit_intent)
    if scenario_guidelines:
        experiences_combined = f"{experiences_combined}\n\n{scenario_guidelines}" if experiences_combined else scenario_guidelines

    # 4. Neo4j 图谱本体按需加载
    methodology = state.get("methodology", "")
    is_graph_task = any(
        kw in user_q.lower() or kw in str(methodology or "").lower()
        for kw in ["团伙", "欺诈环", "共用", "联邦", "图谱", "多层关联", "graph", "cypher", "phone", "手机号"]
    )
    ontology_context = resolve_ontology_context(user_q, methodology)

    # 5. 上下文历史消息紧凑裁剪
    coder_msgs = compact_coder_messages(state.get("messages"), fallback_query=user_q)

    # 6. Prompt 渲染
    prompt_messages = CODER_PROMPT.format_messages(
        original_question=user_q,
        messages=coder_msgs,
        ontology=ontology_context,
        schema_info=schema_hint,
        methodology=methodology,
        tasks="\n".join(tasks_list),
        experiences=experiences_combined
    )

    return CoderPromptPayload(
        prompt_messages=prompt_messages,
        user_query=user_q,
        primary_table=primary_tbl,
        related_tables=related_tbls,
        is_graph_task=is_graph_task,
        scenario_guidelines=scenario_guidelines,
        audit_intent=audit_intent,
    )
