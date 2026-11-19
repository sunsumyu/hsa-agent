"""
app/agents/audit_tool_executor.py
=================================
[SPEC-227 / Matt Pocock Deep Module] 审计工具安全调度与探针拦截深模块 (Audit Tool Executor)

核心职责：
1. 建立安全的工具分发与执行环境，封装底层 inspect.signature 参数适配与异步 ainvoke 调度。
2. 强制实施算力安全红线拦截：在尚未执行核心对碰 SQL 之前，阻断一切非必要的前置探针 SQL，
   同时豁免 DESC/SHOW COLUMNS 等秒级元数据表探查。
3. 异常安全沙箱：捕获工具执行期间的任意意外异常，转化为标准格式，严防未捕获异常崩溃整个状态图。
"""

from __future__ import annotations
import inspect
import re
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple
from loguru import logger
from app.skills.probe_guard import is_probe_query


_METADATA_PROBE_REGEX = re.compile(
    r"^\s*(?:DESC|DESCRIBE(?:\s+TABLE)?|SHOW\s+COLUMNS\s+FROM)\s+",
    re.IGNORECASE,
)


async def invoke_tools_safely(
    tool_calls: Sequence[Mapping[str, Any]],
    tools: Sequence[Any],
    state: Mapping[str, Any],
    is_probe_fn: Optional[Callable[[str], bool]] = None,
) -> List[Tuple[Dict[str, Any], Any]]:
    """
    安全执行给定的工具调用列表。
    
    :return: List of (tool_call_dict, result_dict)
    """
    if is_probe_fn is None:
        is_probe_fn = is_probe_query

    # 计算是否已经成功物理执行过核心对碰 SQL
    has_run_core = False
    for prev_sql in state.get("sql_history", []):
        if not is_probe_fn(prev_sql):
            has_run_core = True
            break

    async def _single_call(tc_mapping: Mapping[str, Any]) -> Tuple[Dict[str, Any], Any]:
        tc = dict(tc_mapping)
        tool_name = tc.get("name", "")
        t_instance = next((t for t in tools if getattr(t, "name", "") == tool_name), None)
        
        if not t_instance:
            return tc, {
                "status": "ERROR",
                "error_message": f"Unknown tool: {tool_name}"
            }

        try:
            raw_args = tc.get("args")
            args = raw_args.copy() if isinstance(raw_args, dict) else {}
            target_func = getattr(t_instance, "func", None) or getattr(t_instance, "coroutine", None)

            if tool_name == "execute_audit_sql" or (
                target_func and "state" in inspect.signature(target_func).parameters
            ):
                args["state"] = dict(state)

            # 刚性物理拦截：如果尚未执行过核心 SQL，禁止执行任何探针探路 SQL
            if tool_name == "execute_audit_sql" and not has_run_core:
                sql_arg = args.get("sql", "")
                is_meta_probe = bool(_METADATA_PROBE_REGEX.match((sql_arg or "").strip()))
                if not is_meta_probe and is_probe_fn(sql_arg):
                    logger.warning(f"🚨 [PROBE_INTERCEPT] 物理算力引擎拦截了前置探针 SQL: {sql_arg}")
                    return tc, {
                        "status": "ERROR",
                        "error_message": (
                            "【算力安全红线拦截】物理算力引擎已禁止前置数据探查！你绝对不能预先执行 DISTINCT med_type 或其他探路 SQL。"
                            "你必须且只能在第一步中，直接根据 methodology 编写并物理执行最终的核心业务审计 SQL（必须包含 lagInFrame / row_number / OVER / 复杂对碰关联等），"
                            "哪怕该表物理数据为空，这也是留存物理审计证据的唯一合规方式！"
                        ),
                        "sql_logic": sql_arg,
                    }

            res = await t_instance.ainvoke(args)
            return tc, res

        except Exception as e:
            return tc, {"status": "ERROR", "error_message": str(e)}

    raw_results = []
    for tc in tool_calls:
        res = await _single_call(tc)
        raw_results.append(res)

    return raw_results
