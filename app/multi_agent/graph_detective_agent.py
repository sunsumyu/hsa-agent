from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import StructuredTool
from loguru import logger

from app.infra.neo4j_ontology_provider import neo4j_ontology_provider
from app.multi_agent.contracts import GraphClueArtifact

_GRAPH_SYSTEM_TEMPLATE = """你是专职医保图谱反欺诈侦查专家 (GraphDetective)。
你只负责在 Neo4j 图数据库中挖掘共享联系方式、跨机构聚集就医等欺诈环，严禁编写任何关系型 SQL！

{ontology}

执行要求：
1. 优先调用 `federated_graph_sideloader` 工具提取嫌疑参保人 `psn_no` 并作为 `id` 返回（如 `RETURN DISTINCT p1.psn_no AS id`）。
2. 仅使用本体中声明的节点标签与关系类型。"""

DEFAULT_SHARED_PHONE_CYPHER = (
    "MATCH (p1:Patient)-[:HAS_PHONE]->(t:Phone)<-[:HAS_PHONE]-(p2:Patient) "
    "WHERE p1.psn_no <> p2.psn_no RETURN DISTINCT p1.psn_no AS id"
)

# 仅限连接性信号（小写比较）；语法错误、侧载写入失败等不属于离线。
_OFFLINE_SIGNALS = (
    "未连接",
    "serviceunavailable",
    "connection refused",
    "refused",
    "timed out",
    "timeout",
    "connect",
)


def _parse_entity_count(msg: str) -> int:
    match = re.search(r"发现了\s*(\d+)\s*个", msg or "")
    return int(match.group(1)) if match else 0


def _is_offline(err_text: str) -> bool:
    lowered = (err_text or "").lower()
    return any(signal in lowered for signal in _OFFLINE_SIGNALS)


async def _sideload_tool_impl(cypher: str, return_key: str = "id") -> Dict[str, Any]:
    from app.skills.federated.federated_graph_executor import execute_federated_sideloader
    return await execute_federated_sideloader(cypher, return_key=return_key)


async def _fraud_ring_tool_impl(cypher: str) -> Dict[str, Any]:
    from app.skills.federated.federated_graph_executor import execute_fraud_ring_cypher
    return await execute_fraud_ring_cypher(cypher)


def build_graph_only_tools() -> List[StructuredTool]:
    """图谱专用工具包装：描述中零关系表信息，复用同一底层执行器。"""
    sideloader = StructuredTool.from_function(
        coroutine=_sideload_tool_impl,
        name="federated_graph_sideloader",
        description=(
            "在 Neo4j 图数据库执行纯 Cypher 检索，并将返回的实体 ID 侧载为临时表。"
            "cypher 必须是 Cypher；return_key 为 Cypher 返回列别名（默认 id）。"
        ),
    )
    fraud_ring = StructuredTool.from_function(
        coroutine=_fraud_ring_tool_impl,
        name="query_fraud_ring",
        description="在 Neo4j 图数据库执行纯 Cypher 查询，用于发现隐蔽的欺诈团伙。",
    )
    return [sideloader, fraud_ring]


class GraphDetectiveSubagent:
    """上下文物理隔离的图谱侦查智能体：零关系表 Schema 暴露，根除 SQL/Cypher 混写。"""

    def __init__(
        self,
        llm_caller: Optional[Callable[..., Any]] = None,
        sideload_fn: Optional[Callable[..., Any]] = None,
    ):
        self._llm_caller = llm_caller
        self._sideload_fn = sideload_fn
        self._tools = build_graph_only_tools()

    def build_isolated_messages(self, user_query: str) -> List[BaseMessage]:
        ontology = neo4j_ontology_provider.get_audit_graph_hints()
        sys_msg = SystemMessage(content=_GRAPH_SYSTEM_TEMPLATE.format(ontology=ontology))
        return [sys_msg, HumanMessage(content=user_query)]

    async def _call_llm(self, messages: List[BaseMessage], config: Any) -> Any:
        if self._llm_caller is not None:
            chat_fn = self._llm_caller
        else:
            from app.core.llm_provider import llm_provider
            chat_fn = llm_provider.chat
        return await chat_fn(
            role="auditor",
            messages=messages,
            config=config,
            tools=self._tools,
            max_tokens=500,
        )

    async def _run_sideload(self, cypher: str, return_key: str) -> dict:
        if self._sideload_fn is not None:
            return await self._sideload_fn(cypher=cypher, return_key=return_key)
        return await _sideload_tool_impl(cypher=cypher, return_key=return_key)

    async def _plan_cypher(self, messages: List[BaseMessage], config: Any) -> tuple:
        try:
            resp = await self._call_llm(messages, config)
            tcs = getattr(resp, "tool_calls", None) or []
            if tcs:
                args = tcs[0].get("args") or {}
                return args.get("cypher") or DEFAULT_SHARED_PHONE_CYPHER, args.get("return_key") or "id"
            logger.warning("[GraphDetective] LLM 未返回 tool_calls，使用标准共享号码 Cypher 模板")
        except Exception as exc:
            logger.warning(f"[GraphDetective] LLM 推理异常，使用标准共享号码 Cypher 模板兜底: {exc}")
        return DEFAULT_SHARED_PHONE_CYPHER, "id"

    async def investigate(self, user_query: str, config: Any = None) -> GraphClueArtifact:
        messages = self.build_isolated_messages(user_query)
        cypher, return_key = await self._plan_cypher(messages, config)

        try:
            res = await self._run_sideload(cypher, return_key)
        except Exception as exc:
            logger.warning(f"[GraphDetective] 侧载调用异常，降级关系型路径: {exc}")
            return GraphClueArtifact(
                succeeded=False,
                degraded_to_relational=True,
                temp_table=None,
                cypher_used=cypher,
                summary=str(exc),
            )

        if res.get("status") == "SIDELOADED" and res.get("temp_table"):
            msg = str(res.get("message", ""))
            return GraphClueArtifact(
                succeeded=True,
                temp_table=res["temp_table"],
                entity_count=_parse_entity_count(msg),
                cypher_used=cypher,
                summary=msg,
            )

        err_text = str(res.get("error_message") or res.get("message") or "图谱未命中或未连接")
        return GraphClueArtifact(
            succeeded=False,
            degraded_to_relational=_is_offline(err_text),
            cypher_used=cypher,
            summary=err_text,
        )
