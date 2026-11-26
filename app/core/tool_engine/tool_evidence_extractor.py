"""
app/core/tool_engine/tool_evidence_extractor.py
=====================================
[V230.0 / Matt Pocock Deep Module] 工具执行结果与审计证据提取器 (Tool Evidence Extractor)

核心职责：
1. 工具执行响应反序列化与异常状态提取
2. 委托 evidence_truncation_policy 实施结构化截断与宏观保全
3. 委托 core_sql_resolver 仲裁主线核心审计 SQL
4. 证据链多轮 Append-Only 累加保全
"""

from __future__ import annotations

import ast
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
from loguru import logger
from langchain_core.messages import ToolMessage

from app.core.rag.citation_ledger import merge_citation_ledgers, parse_citations_from_tool_output
from app.skills.security.probe_guard import is_probe_query
from app.core.tool_engine.evidence_truncation_policy import truncate_evidence_data
from app.core.tool_engine.core_sql_resolver import resolve_core_audit_sql
from app.data.raw_data_sanitizer import RawDataSanitizer


@dataclass
class ProcessedToolResults:
    """工具处理结果领域对象"""
    tool_msgs: List[ToolMessage]
    raw_data: str
    sql_query: str
    sql_history: List[str]
    methodology: str
    execution_trace: List[str]
    has_error: bool
    error_msg: str
    evidence_row_count: int = 0
    retrieved_citations: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """向后兼容字典接口供 LangGraph State 使用"""
        return {
            "tool_msgs": self.tool_msgs,
            "raw_data": self.raw_data,
            "evidence_row_count": self.evidence_row_count,
            "sql_query": self.sql_query,
            "sql_history": self.sql_history,
            "methodology": self.methodology,
            "execution_trace": self.execution_trace,
            "has_error": self.has_error,
            "error_msg": self.error_msg,
            "retrieved_citations": self.retrieved_citations,
        }

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


def _harvest_citations(
    results: List[Tuple[Dict[str, Any], Any]],
    existing_citations: Optional[List[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Harvest structured RAG/law citations from tool outputs without resetting existing ledger."""
    ledger: List[Dict[str, Any]] = list(existing_citations or [])
    for t_call, res in results:
        parsed = parse_citations_from_tool_output(str(t_call.get("name", "")), str(res))
        if parsed:
            ledger = merge_citation_ledgers(ledger, [rec.model_dump(mode="json") for rec in parsed])
    return ledger


def _parse_tool_payload(res: Any) -> Any:
    if not (isinstance(res, str) and res.strip().startswith("{")):
        return res
    try:
        return json.loads(res)
    except (json.JSONDecodeError, ValueError, TypeError) as json_exc:
        try:
            return ast.literal_eval(res)
        except (ValueError, SyntaxError, TypeError) as ast_exc:
            logger.debug(f"[ToolEvidenceExtractor] Payload parse fallback skipped: json={json_exc}, ast={ast_exc}")
            return res


def _extract_non_probe_data(
    parsed_res: Dict[str, Any],
    truncate_fn: Callable[[Any], str],
    warn_on_empty: bool = False,
) -> Optional[str]:
    sql_logic = parsed_res.get("sql_logic", "")
    if sql_logic and is_probe_query(sql_logic):
        if warn_on_empty:
            logger.info(f"🔮 [EVIDENCE] Skipped probe query data extraction: {sql_logic[:80]}...")
        return None
    for data_field in ("data", "records_sample", "raw_evidence"):
        if parsed_res.get(data_field):
            return truncate_fn(parsed_res[data_field])
    if warn_on_empty and parsed_res.get("status") == "SUCCESS":
        logger.warning(f"🔮 [EVIDENCE] SUCCESS status but no data fields! Keys: {list(parsed_res.keys())}")
    return None


def _merge_append_only_raw_data(existing_raw: str, raw_data_list: List[str]) -> Tuple[str, bool, str]:
    new_chunk = "\n---\n".join(raw_data_list) if raw_data_list else ""
    if existing_raw and new_chunk:
        if new_chunk.strip() not in existing_raw:
            return f"{existing_raw}\n---\n{new_chunk}", True, new_chunk
        return existing_raw, False, new_chunk
    if new_chunk:
        return new_chunk, True, new_chunk
    return existing_raw, False, new_chunk


class ToolEvidenceExtractor:
    """审计证据链提取与工具结果标准化深模块"""

    def __init__(self, max_chars: int = 12000):
        self.max_chars = max_chars

    def truncate_data(self, data: Any) -> str:
        """委托至截断策略深模块"""
        return truncate_evidence_data(data, max_chars=self.max_chars)

    def process(self, results: List[Tuple[Dict[str, Any], Any]], state: Dict[str, Any]) -> ProcessedToolResults:
        """执行工具响应解析与证据链归集"""
        tool_msgs, raw_data_list, sql_logics, methodologies, tool_traces = [], [], [], [], []
        has_error, error_msg = False, ""

        for t_call, res in results:
            trace_id = hashlib.sha256(f"{t_call['name']}_{time.time()}".encode()).hexdigest()[:8].upper()
            tool_msgs.append(ToolMessage(content=str(res)[:2000], tool_call_id=t_call["id"]))
            parsed_res = _parse_tool_payload(res)
            if not isinstance(parsed_res, dict):
                continue
            if "sql_logic" in parsed_res:
                sql_logics.append(parsed_res["sql_logic"])
            if "methodology" in parsed_res:
                methodologies.append(parsed_res["methodology"])
            if "trace_hint" in parsed_res:
                tool_traces.append(f"[{trace_id}] {parsed_res['trace_hint']}")
            if parsed_res.get("status") == "ERROR":
                has_error = True
                error_msg = parsed_res.get("error_message") or "Tool execution failed"
            extracted = _extract_non_probe_data(parsed_res, self.truncate_data, warn_on_empty=True)
            if extracted:
                raw_data_list.append(extracted)

        accumulated_sql_history = state.get("sql_history", []) + sql_logics
        core_sql = resolve_core_audit_sql(accumulated_sql_history)
        if not raw_data_list:
            for _, res in results:
                parsed_res = _parse_tool_payload(res)
                if isinstance(parsed_res, dict):
                    extracted = _extract_non_probe_data(parsed_res, self.truncate_data)
                    if extracted:
                        raw_data_list.append(extracted)

        new_raw_data, appended, new_chunk = _merge_append_only_raw_data(state.get("raw_data", ""), raw_data_list)
        carried_before = int(state.get("evidence_row_count") or 0)
        evidence_row_count = (
            carried_before + len(RawDataSanitizer.sanitize_and_parse(new_chunk))
            if (appended and new_chunk) else carried_before
        )
        return ProcessedToolResults(
            tool_msgs=tool_msgs,
            raw_data=new_raw_data,
            evidence_row_count=evidence_row_count,
            sql_query=core_sql,
            sql_history=accumulated_sql_history,
            methodology="\n\n".join(methodologies) if methodologies else state.get("methodology", ""),
            execution_trace=state.get("execution_trace", []) + tool_traces,
            has_error=has_error,
            error_msg=error_msg,
            retrieved_citations=_harvest_citations(results, state.get("retrieved_citations")),
        )


tool_evidence_extractor = ToolEvidenceExtractor()
