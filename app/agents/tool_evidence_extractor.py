"""
app/agents/tool_evidence_extractor.py
=====================================
[V230.0] 工具执行结果与审计证据提取器 (Tool Evidence Extractor)

重构自 AuditCoderAgent._process_tool_results：
将 120+ 行充斥反序列化、探针过滤、数据截断、证据链拼装的私有逻辑
提取为高内聚、易测试、强类型的深模块 (Deep Module)。
"""

from __future__ import annotations

import json
import time
import hashlib
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional
from loguru import logger
from langchain_core.messages import ToolMessage

from app.skills.probe_guard import is_probe_query


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

    def to_dict(self) -> Dict[str, Any]:
        """向后兼容字典接口供 LangGraph State 使用"""
        return {
            "tool_msgs": self.tool_msgs,
            "raw_data": self.raw_data,
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
        """截断超长数据集防止上下文溢出"""
        data_str = str(data)
        if len(data_str) > self.max_chars:
            logger.warning(f"🚨 [State Safeguard] 结果集过大 ({len(data_str)} chars)，自动截断至 {self.max_chars} chars。")
            return (
                data_str[:self.max_chars]
                + f"... \n\n[WARNING: Data truncated due to excessive length. Original length: {len(data_str)} chars]"
            )
        return data_str

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

        # 筛选核心审计 SQL
        accumulated_sql_history = state.get("sql_history", []) + sql_logics
        core_sql = ""
        if accumulated_sql_history:
            audit_queries = [sql for sql in accumulated_sql_history if not is_probe_query(sql)]
            core_sql = audit_queries[-1] if audit_queries else accumulated_sql_history[-1]

        has_new_core_query = any(not is_probe_query(s) for s in sql_logics)

        # 兜底保障：若所有结果被过滤导致 raw_data_list 为空，仅提取非探针结果
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

        new_raw_data = "\n---\n".join(raw_data_list)
        if not has_new_core_query and not new_raw_data:
            new_raw_data = state.get("raw_data", "")

        final_methodology = "\n\n".join(methodologies) if methodologies else state.get("methodology", "")

        return ProcessedToolResults(
            tool_msgs=tool_msgs,
            raw_data=new_raw_data,
            sql_query=core_sql,
            sql_history=accumulated_sql_history,
            methodology=final_methodology,
            execution_trace=state.get("execution_trace", []) + tool_traces,
            has_error=has_error,
            error_msg=error_msg,
        )


tool_evidence_extractor = ToolEvidenceExtractor()
