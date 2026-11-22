"""
app/agents/tool_evidence_extractor.py
=====================================
[V230.0 / Matt Pocock Deep Module] 工具执行结果与审计证据提取器 (Tool Evidence Extractor)

核心职责：
1. 工具执行响应反序列化与异常状态提取
2. 委托 evidence_truncation_policy 实施结构化截断与宏观保全
3. 委托 core_sql_resolver 仲裁主线核心审计 SQL
4. 证据链多轮 Append-Only 累加保全
"""

from __future__ import annotations

import json
import time
import hashlib
from dataclasses import dataclass
from typing import List, Dict, Any, Tuple
from loguru import logger
from langchain_core.messages import ToolMessage

from app.skills.security.probe_guard import is_probe_query
from app.agents.evidence_truncation_policy import truncate_evidence_data
from app.agents.core_sql_resolver import resolve_core_audit_sql
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
    evidence_row_count: int = 0  # [证据对账] 证据通道中实际可解析的行数 (Append-Only 累加)

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
        }

    def __getitem__(self, item: str) -> Any:
        """支持字典下标访问兼容现有代码"""
        return getattr(self, item)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)


class ToolEvidenceExtractor:
    """审计证据链提取与工具结果标准化深模块"""

    def __init__(self, max_chars: int = 12000):
        self.max_chars = max_chars

    def truncate_data(self, data: Any) -> str:
        """委托至截断策略深模块"""
        return truncate_evidence_data(data, max_chars=self.max_chars)

    def process(self, results: List[Tuple[Dict[str, Any], Any]], state: Dict[str, Any]) -> ProcessedToolResults:
        """执行工具响应解析与证据链归集"""
        tool_msgs = []
        raw_data_list = []
        sql_logics = []
        methodologies = []
        tool_traces = []
        has_error = False
        error_msg = ""

        for t_call, res in results:
            trace_id = hashlib.sha256(f"{t_call['name']}_{time.time()}".encode()).hexdigest()[:8].upper()
            tool_msg = ToolMessage(content=str(res)[:2000], tool_call_id=t_call["id"])
            tool_msgs.append(tool_msg)

            parsed_res = res
            if isinstance(res, str) and res.strip().startswith("{"):
                try:
                    parsed_res = json.loads(res)
                except Exception:
                    try:
                        import ast
                        parsed_res = ast.literal_eval(res)
                    except Exception:
                        pass

            if isinstance(parsed_res, dict):
                if "sql_logic" in parsed_res:
                    sql_logics.append(parsed_res["sql_logic"])
                if "methodology" in parsed_res:
                    methodologies.append(parsed_res["methodology"])
                if "trace_hint" in parsed_res:
                    tool_traces.append(f"[{trace_id}] {parsed_res['trace_hint']}")
                if parsed_res.get("status") == "ERROR":
                    has_error = True
                    error_msg = parsed_res.get("error_message") or "Tool execution failed"

                sql_logic = parsed_res.get("sql_logic", "")
                is_probe = bool(sql_logic and is_probe_query(sql_logic))

                if not is_probe:
                    data_extracted = False
                    for field in ["data", "records_sample", "raw_evidence"]:
                        if field in parsed_res and parsed_res[field]:
                            raw_data_list.append(self.truncate_data(parsed_res[field]))
                            data_extracted = True
                            break
                    if not data_extracted and parsed_res.get("status") == "SUCCESS":
                        logger.warning(f"🔮 [EVIDENCE] SUCCESS status but no data fields! Keys: {list(parsed_res.keys())}")
                else:
                    logger.info(f"🔮 [EVIDENCE] Skipped probe query data extraction: {sql_logic[:80]}...")

        # 委托核心审计 SQL 仲裁解析器
        accumulated_sql_history = state.get("sql_history", []) + sql_logics
        core_sql = resolve_core_audit_sql(accumulated_sql_history)

        # 兜底保障：若所有结果被过滤导致 raw_data_list 为空，提取非探针结果
        if not raw_data_list:
            for t_call, res in results:
                parsed_res = res
                if isinstance(res, str) and res.strip().startswith("{"):
                    try:
                        parsed_res = json.loads(res)
                    except Exception:
                        pass
                if isinstance(parsed_res, dict):
                    sql_logic = parsed_res.get("sql_logic", "")
                    if sql_logic and is_probe_query(sql_logic):
                        continue  # 探针数据绝不作为业务证据兜底
                    for field in ["data", "records_sample", "raw_evidence"]:
                        if field in parsed_res and parsed_res[field]:
                            raw_data_list.append(self.truncate_data(parsed_res[field]))
                            break

        # [V180.0 Pocock 证据链保全] 多轮执行采用 Append-Only 累加保全，杜绝后序辅助探针覆盖核心金额证据
        new_chunk = "\n---\n".join(raw_data_list) if raw_data_list else ""
        existing_raw = state.get("raw_data", "")

        appended = False
        if existing_raw and new_chunk:
            if new_chunk.strip() not in existing_raw:
                new_raw_data = f"{existing_raw}\n---\n{new_chunk}"
                appended = True
            else:
                new_raw_data = existing_raw
        elif new_chunk:
            new_raw_data = new_chunk
            appended = True
        else:
            new_raw_data = existing_raw

        # [证据对账] 用与 Reporter 完全相同的解析器统计通道实际可解析行数，Append-Only 累加。
        # 截断损失由 truncate_evidence_data 的 total_records 汇总行自证；此处计数是解析丢失的对照基准。
        carried_before = int(state.get("evidence_row_count") or 0)
        if appended and new_chunk:
            evidence_row_count = carried_before + len(RawDataSanitizer.sanitize_and_parse(new_chunk))
        else:
            evidence_row_count = carried_before

        final_methodology = "\n\n".join(methodologies) if methodologies else state.get("methodology", "")

        return ProcessedToolResults(
            tool_msgs=tool_msgs,
            raw_data=new_raw_data,
            evidence_row_count=evidence_row_count,
            sql_query=core_sql,
            sql_history=accumulated_sql_history,
            methodology=final_methodology,
            execution_trace=state.get("execution_trace", []) + tool_traces,
            has_error=has_error,
            error_msg=error_msg,
        )


tool_evidence_extractor = ToolEvidenceExtractor()
