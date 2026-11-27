"""
app/api/stream_protocol_renderer.py
===================================
[Matt Pocock Deep Module] 3D UI 表现层协议帧渲染与 Chunk 文本提取深模块

核心职责：
1. 将 LangGraph 状态机切换事件转化为前端 3D 舞台动作与状态帧 (STATUS, MOVE, SCHEMA)
2. 将工具执行事件转化为 3D 视觉交互帧 (MOVE, LOGIC, SQL, BOOKSHELF)
3. 算力 Token 消耗与成本遥测标签生成 (RESOURCE)
4. 证据链追踪 Markdown 容器渲染 (sql_trace)
5. 中断挂起场景专家校准卡片生成 (HUMAN_REVIEW)
6. 多模态/思维链 LLM 输出 Chunk 的规范化文本提取
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from loguru import logger


_NODE_DISPLAY_NAMES: Dict[str, str] = {
    "DATA_EXPERT": "数据外联专家",
    "AUDITOR": "政策合规专家",
    "FINANCIAL_EXPERT": "精算核算专家",
    "MULTI_AGENT_HUB": "异构多专家协同中枢",
    "REPORTER": "稽核报告终审",
    "SOLO_EXPERT": "全能审计专家",
}

_NODE_WORLDS: Dict[str, tuple[str, str]] = {
    "data_expert": (
        "[[[MOVE:default.fqz_all_yy_yd_1]]]",
        "[[[SCHEMA:default.fqz_all_yy_yd_1:fixmedins_code,medfee_sumamt,setl_time,psn_no]]]",
    ),
    "auditor": (
        "[[[MOVE:argus_policy_kb]]]",
        "[[[SCHEMA:argus_policy_kb:rule_id,rule_name,legal_basis,risk_weight]]]",
    ),
    "financial_expert": (
        "[[[MOVE:t_audit_task]]]",
        "[[[SCHEMA:t_audit_task:task_id,status,target_hosp_id,audit_amount]]]",
    ),
}


class StreamProtocolRenderer:
    """3D UI 协议帧渲染器"""

    def render_node_status(self, check_name: str, name: str) -> List[str]:
        """当 LangGraph 切换节点时生成一组前端协议标签"""
        out: List[str] = []
        if check_name not in _NODE_DISPLAY_NAMES:
            return out

        display_name = _NODE_DISPLAY_NAMES.get(check_name, check_name)
        if name != "solo_expert_node":
            out.append(f"[[[STATUS:正在激活 [{display_name}] 进行推演...]]]")

        world_packets = _NODE_WORLDS.get(name)
        if world_packets:
            out.extend(world_packets)

        return out

    def render_tool_start_events(self, name: str, inputs: Dict[str, Any]) -> List[str]:
        """工具启动时生成 3D UI 联动包 (MOVE/LOGIC/SQL/BOOKSHELF)"""
        out: List[str] = []

        if name in ("execute_audit_sql", "get_table_schema"):
            db = inputs.get("db_type", "clickhouse")
            table = inputs.get("table_name", "archives")
            if table == "archives":
                table = "fqz_all_yy_yd_1"

            world_key = f"default.{table}" if db == "clickhouse" else table
            out.append(f"[[[MOVE:{world_key}]]]")
            out.append(
                f"[[[LOGIC:正在执行交叉核验 -> 检索键: "
                f"{inputs.get('sql', 'Metadata Fetch')[:50]}...]]]"
            )

            if "sql" in inputs:
                sql_val = inputs["sql"]
                out.append(f"[[[SQL:{sql_val}]]]")
                try:
                    m = re.search(r"SELECT\s+(.+?)\s+FROM", sql_val, re.IGNORECASE)
                    if m:
                        raw_cols = m.group(1).strip()
                        if raw_cols != "*":
                            cols = [
                                c.strip().split(".")[-1].split(" ")[0]
                                for c in raw_cols.split(",")
                            ]
                            out.append(f"[[[BOOKSHELF:{world_key}:{','.join(cols)}]]]")
                        else:
                            out.append(f"[[[BOOKSHELF:{world_key}:*]]]")
                except Exception as exc:
                    logger.debug(f"[StreamProtocolRenderer] SQL column extraction skipped: {exc}")

        elif name == "search_expert_knowledge":
            out.append("[[[MOVE:argus_policy_kb]]]")
            out.append("[[[THOUGHT:正在检索核心政策库以比对违规特征...]]]")
            out.append("[[[LOGIC:输入诊断特征 -> 搜索高风险规则集...]]]")
            out.append("[[[BOOKSHELF:argus_policy_kb:rule_name,legal_basis]]]")

        elif name == "calculator":
            out.append("[[[MOVE:logic_core]]]")
            out.append("[[[THOUGHT:正在启动确证计算引擎，进行高精度金额核算...]]]")
            out.append("[[[LOGIC:输入数值对 -> 精算确认违规金额总计...]]]")

        return out

    def render_resource_telemetry(self, usage: Optional[Dict[str, Any]], node_or_role: str) -> Optional[str]:
        """计算算力 Token 消耗与成本，生成前端遥测标签 [[[RESOURCE:...]]]"""
        if not usage:
            return None
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        if not prompt_tokens and not completion_tokens:
            return None

        # 成本估算模型 (1k tokens: input=0.01元, output=0.03元)
        input_cost = (prompt_tokens / 1000) * 0.01
        output_cost = (completion_tokens / 1000) * 0.03
        total_cost = input_cost + output_cost

        return f"[[[RESOURCE:{{'role': '{node_or_role}', 'prompt': {prompt_tokens}, 'completion': {completion_tokens}, 'cost': {total_cost:.4f}}}]]]"

    def render_tool_trace(self, name: str, output: Any, max_len: int = 1000) -> Optional[str]:
        """针对关键审计取证工具生成 UI 追踪 Markdown 容器"""
        if name in ("execute_audit_sql", "search_expert_knowledge", "list_tables"):
            summary = str(output)[:max_len]
            return f"\n:::sql_trace\n-- [物理取证执行] 工具: {name}\n{summary}\n:::\n\n"
        return None

    def render_human_review_card(self, snapshot_values: Optional[Dict[str, Any]]) -> str:
        """当 LangGraph 图在中断点挂起（如人工介入审核）时，渲染指引卡片"""
        vals = snapshot_values or {}
        help_msg = ""
        error_log = str(vals.get("error_log") or "")
        if error_log.startswith("MODEL_REQUEST_HELP:"):
            help_msg = error_log.replace("MODEL_REQUEST_HELP:", "").strip()

        if help_msg:
            return (
                f"### 🚩 专家业务校准请求\n\n"
                f"Agent 在执行审计取证时遇到关键疑虑：\n\n> {help_msg}\n\n---\n"
                f"**💡 下一步指引**：\n"
                f"请根据上述疑虑，直接在对话框中输入您的决策建议（如：“请按XX口径继续查询”或“忽略此项”），系统将自动恢复审计链路。"
            )
        return (
            "\n\n> [!IMPORTANT]\n"
            "> **审计链路中断**: 模型由于逻辑过于复杂请求人工接管。请在下方输入您的业务指导意见。"
        )

    def extract_chunk_text(self, content: Any) -> str:
        """
        规范化提取 LLM 流式输出 Chunk 中的文本内容。
        兼容 str, dict (含 text/thought), 以及包含多模态/思维链 dict 对象的 list。
        """
        if not content:
            return ""
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            return str(content.get("text") or content.get("thought") or "")
        if isinstance(content, list):
            text_parts: List[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                item_type = item.get("type")
                if item_type in ("text", "thought", "reasoning", "thinking"):
                    val = item.get("text") or item.get("thought") or item.get("reasoning") or item.get("thinking") or ""
                    if val:
                        text_parts.append(str(val))
            return "".join(text_parts)
        return ""


    def render_meta_envelope(self, run_id: str, session_id: str) -> str:
        """渲染会话元数据帧，向前端透传 Run ID 与 Session ID"""
        import json
        payload = json.dumps({"run_id": str(run_id), "session_id": str(session_id)}, ensure_ascii=False)
        return f":::meta {payload}:::\n"


# 全局默认单例
stream_protocol_renderer = StreamProtocolRenderer()
