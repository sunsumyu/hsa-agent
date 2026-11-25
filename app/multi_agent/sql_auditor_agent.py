from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List, Optional

from langchain_core.messages import HumanMessage
from loguru import logger

from app.multi_agent.contracts import GraphClueArtifact, SQLAuditArtifact, SubTaskSpec
from app.reporting.audit_metric_evaluator import AuditMetricEvaluator
from app.reporting.report_renderer import report_renderer


def _enrich_instruction_with_graph_clue(
    instruction: str,
    graph_clue: Optional[GraphClueArtifact],
) -> str:
    if not graph_clue:
        return instruction
    if graph_clue.succeeded and graph_clue.temp_table:
        return (
            f"{instruction}\n【图谱侧载契约】：图谱侦查专员已将嫌疑参保人 psn_no 侧载至 ClickHouse 内存临时表 "
            f"`{graph_clue.temp_table}` (含单列 `id`)。请直接对 `fqz_gz_jzsj_all_ql` 与 `{graph_clue.temp_table}` "
            f"执行 `INNER JOIN {graph_clue.temp_table} ON fqz_gz_jzsj_all_ql.psn_no = {graph_clue.temp_table}.id` 核算金额与记录！"
        )
    if graph_clue.degraded_to_relational:
        return (
            f"{instruction}\n【关系库兜底指引】：图数据库当前离线，请在 `fqz_gz_jzsj_all_ql` 中使用子查询定位共享手机号："
            "`WHERE tel != '' AND tel IN (SELECT tel FROM fqz_gz_jzsj_all_ql WHERE tel != '' GROUP BY tel HAVING uniqExact(psn_no) > 1)` 统计涉案记录与金额！"
        )
    return instruction


def _build_isolated_state(
    subtask: SubTaskSpec,
    session_id: str,
    scoped_query: str,
    graph_clue: Optional[GraphClueArtifact],
) -> Dict[str, Any]:
    return {
        "session_id": f"{session_id}:{subtask.subtask_id}",
        "current_turn_query": scoped_query,
        "tasks": [subtask.focus_title],
        "methodology": f"专项独立取证：{subtask.focus_title}",
        "messages": [HumanMessage(content=scoped_query)],
        "metadata": {"user_question": scoped_query},
        "temp_table": graph_clue.temp_table if (graph_clue and graph_clue.succeeded) else None,
        "retry_count": 0,
        "sql_history": [],
    }


class SQLAuditorSubagent:
    """上下文物理隔离的数仓核算专员池：每个子任务独享临时状态栈，支持并发扇出。"""

    def __init__(self, coder_executor: Optional[Callable[..., Any]] = None):
        self._coder_executor = coder_executor

    async def _invoke_coder(self, isolated_state: Dict[str, Any], config: Any) -> Dict[str, Any]:
        if self._coder_executor is not None:
            return await self._coder_executor(isolated_state, config)
        from app.agents.coder_agent import coder_agent

        return await coder_agent.execute(isolated_state, config or {})

    async def run_subtask(
        self,
        subtask: SubTaskSpec,
        session_id: str,
        config: Any = None,
        graph_clue: Optional[GraphClueArtifact] = None,
    ) -> SQLAuditArtifact:
        scoped_query = _enrich_instruction_with_graph_clue(subtask.query_instruction, graph_clue)
        isolated_state = _build_isolated_state(subtask, session_id, scoped_query, graph_clue)

        try:
            res = await self._invoke_coder(isolated_state, config)
            raw_str = str((res or {}).get("raw_data") or "")
            parsed_rows = report_renderer.clean_and_parse_raw_data(raw_str)
            hard_count, hard_sum = AuditMetricEvaluator.extract_totals(parsed_rows)
        except Exception as exc:
            logger.warning(f"[SQLAuditor] 子任务 {subtask.subtask_id} 执行异常: {exc}")
            return SQLAuditArtifact(
                subtask_id=subtask.subtask_id,
                focus_title=subtask.focus_title,
                validated=False,
                error=str(exc),
            )

        return SQLAuditArtifact(
            subtask_id=subtask.subtask_id,
            focus_title=subtask.focus_title,
            sql_query=str(res.get("sql_query") or ""),
            raw_data=raw_str,
            row_count=hard_count,
            total_amount=hard_sum,
            validated=bool(res.get("sql_validated", False)),
            error=res.get("error_log"),
        )

    async def run_parallel(
        self,
        subtasks: List[SubTaskSpec],
        session_id: str,
        config: Any = None,
        graph_clue: Optional[GraphClueArtifact] = None,
    ) -> List[SQLAuditArtifact]:
        coros = [
            self.run_subtask(st, session_id=session_id, config=config, graph_clue=graph_clue)
            for st in subtasks
        ]
        return list(await asyncio.gather(*coros))
