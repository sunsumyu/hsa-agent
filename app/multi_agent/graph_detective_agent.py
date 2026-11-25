from __future__ import annotations

import re
from typing import Any, Callable, List, Optional

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from loguru import logger

from app.infra.neo4j_ontology_provider import neo4j_ontology_provider
from app.multi_agent.contracts import GraphClueArtifact
from app.skills.rules.analysis_tools import federated_graph_sideloader, query_fraud_ring

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


def _parse_entity_count(msg: str) -> int:
    match = re.search(r"发现了\s*(\d+)\s*个", msg or "")
    return int(match.group(1)) if match else 0


class GraphDetectiveSubagent:
    """上下文物理隔离的图谱侦查智能体：零关系表 Schema 暴露，根除 SQL/Cypher 混写。"""

    def __init__(
        self,
        llm_caller: Optional[Callable[..., Any]] = None,
        sideload_fn: Optional[Callable[..., Any]] = None,
    ):
        self._llm_caller = llm_caller
        self._sideload_fn = sideload_fn

    def build_isolated_messages(self, user_query: str) -> List[BaseMessage]:
        ontology = neo4j_ontology_provider.get_audit_graph_hints()
        sys_msg = SystemMessage(content=_GRAPH_SYSTEM_TEMPLATE.format(ontology=ontology))
        return [sys_msg, HumanMessage(content=user_query)]

    async def _call_llm(self, messages: List[BaseMessage], config: Any) -> Any:
        if self._llm_caller is not None:
            return await self._llm_caller(role="planner_heavy", messages=messages, config=config)
        from app.core.llm_provider import llm_provider
        return await llm_provider.chat(
            role="auditor",
            messages=messages,
            config=config,
            tools=[federated_graph_sideloader, query_fraud_ring],
            max_tokens=500,
        )

    async def _run_sideload(self, cypher: str, return_key: str) -> dict:
        if self._sideload_fn is not None:
            return await self._sideload_fn(cypher=cypher, return_key=return_key)
        from app.skills.federated.federated_graph_executor import execute_federated_sideloader
        return await execute_federated_sideloader(cypher=cypher, return_key=return_key)

    async def investigate(self, user_query: str, config: Any = None) -> GraphClueArtifact:
        messages = self.build_isolated_messages(user_query)
        cypher = DEFAULT_SHARED_PHONE_CYPHER
        return_key = "id"

        try:
            resp = await self._call_llm(messages, config)
            tcs = getattr(resp, "tool_calls", None) or []
            if tcs:
                args = tcs[0].get("args") or {}
                cypher = args.get("cypher") or cypher
                return_key = args.get("return_key") or "id"
        except Exception as exc:
            logger.warning(f"[GraphDetective] LLM 推理异常，使用标准共享号码 Cypher 模板兜底: {exc}")

        res = await self._run_sideload(cypher, return_key)
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
        is_offline = any(k in err_text for k in ("未连接", "offline", "refused", "timed out", "失败"))
        return GraphClueArtifact(
            succeeded=False,
            degraded_to_relational=is_offline,
            cypher_used=cypher,
            summary=err_text,
        )
