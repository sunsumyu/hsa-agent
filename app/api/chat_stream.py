"""
app.api.chat_stream — [重构 V90.0] chat() God Function 的拆解模块
================================================================
原 @app.main.chat() 374 行合并了 5 类不相关关注点:
  1. HTTP 请求解析
  2. LangGraph 事件流遍历
  3. 前端协议标签 ([[[ENGINE:...]]], [[[MOVE:...]]] 等) 的生成
  4. 节点/工具/模型流事件分发
  5. 异常分类与自愈

本模块拆出 #1、#3、#5 的纯函数/生成器。chat() 保留 #2、#4 的主循环编排。
"""
from __future__ import annotations

import json
import re
from typing import Any, AsyncGenerator, Dict, Optional, Tuple

from loguru import logger


# ──────────────────────────────────────────────────────────────
# #1 请求解析
# ──────────────────────────────────────────────────────────────

async def parse_chat_request(request) -> Tuple[str, Optional[str], str]:
    """
    从 FastAPI Request 中提取 (message, model_id, session_id)。
    
    兼容两种 payload:
      - JSON: {"input": "...", "modelId": "..."}
      - 原始文本: "..."
    """
    body = await request.body()
    try:
        data = json.loads(body.decode("utf-8"))
        message = data.get("input", str(data))
        model_id = data.get("modelId")
    except Exception:
        message = body.decode("utf-8")
        model_id = None

    session_id = request.headers.get("X-Session-Id", "default-python-session")
    return message, model_id, session_id


# ──────────────────────────────────────────────────────────────
# #3 前端协议标签生成
# ──────────────────────────────────────────────────────────────

_NODE_DISPLAY_NAMES = {
    "DATA_EXPERT": "数据外联专家",
    "AUDITOR": "政策合规专家",
    "FINANCIAL_EXPERT": "精算核算专家",
    "REPORTER": "稽核报告终审",
    "SOLO_EXPERT": "全能审计专家",
}

_NODE_WORLDS = {
    "data_expert": (
        "[[[MOVE:default.fqz_all_yy_yd_1]]]",
        "[[[SCHEMA:default.fqz_all_yy_yd_1:fixmedins_code,medfee_sumamt,setl_time,psn_no]]]",
    ),
    "auditor": (
        "[[[MOVE:hsa_policy_kb]]]",
        "[[[SCHEMA:hsa_policy_kb:rule_id,rule_name,legal_basis,risk_weight]]]",
    ),
    "financial_expert": (
        "[[[MOVE:t_audit_task]]]",
        "[[[SCHEMA:t_audit_task:task_id,status,target_hosp_id,audit_amount]]]",
    ),
}


def emit_node_status(check_name: str, name: str) -> list[str]:
    """
    当 LangGraph 切换节点时生成一组前端协议标签。
    
    Returns:
        待 yield 的字符串列表。
    """
    out: list[str] = []
    if check_name not in _NODE_DISPLAY_NAMES:
        return out

    display_name = _NODE_DISPLAY_NAMES.get(check_name, check_name)
    if name != "solo_expert_node":
        out.append(f"[[[STATUS:正在激活 [{display_name}] 进行推演...]]]")

    world_packets = _NODE_WORLDS.get(name)
    if world_packets:
        out.extend(world_packets)

    return out


def emit_tool_start_events(name: str, inputs: Dict[str, Any]) -> list[str]:
    """
    工具启动时生成 3D UI 联动包 (MOVE/LOGIC/SQL/BOOKSHELF)。
    """
    out: list[str] = []

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
            # 精确书架命中协议: 从 SELECT 中解析字段
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
            except Exception:
                pass

    elif name == "search_expert_knowledge":
        out.append("[[[MOVE:hsa_policy_kb]]]")
        out.append("[[[THOUGHT:正在检索核心政策库以比对违规特征...]]]")
        out.append("[[[LOGIC:输入诊断特征 -> 搜索高风险规则集...]]]")
        out.append("[[[BOOKSHELF:hsa_policy_kb:rule_name,legal_basis]]]")

    elif name == "calculator":
        out.append("[[[MOVE:logic_core]]]")
        out.append("[[[THOUGHT:正在启动确证计算引擎，进行高精度金额核算...]]]")
        out.append("[[[LOGIC:输入数值对 -> 精算确认违规金额总计...]]]")

    return out


# ──────────────────────────────────────────────────────────────
# #5 错误分类与自愈文案
# ──────────────────────────────────────────────────────────────

def classify_and_render_error(
    err_msg: str,
    resolved_id: Optional[str],
    usage_tracker,
    model_manager,
    background_tasks,
) -> list[str]:
    """
    根据错误类型返回 UI 需要的自愈文案列表。
    
    副作用 (black-listing / 后台健康检查) 也在此函数内执行。
    """
    out: list[str] = []

    # 1. Token 耗尽结构化建议原样透传
    if "[[[OUT_OF_TOKEN" in err_msg:
        out.append(f"\n{err_msg}")
        return out

    # 2. 供应商配额 / 403
    if any(kw in err_msg for kw in ("403", "Forbidden")) or "exhausted" in err_msg.lower():
        if resolved_id:
            consumed = usage_tracker.stats.daily_usage.get(resolved_id, 0)
            is_free_tier = (
                "FreeTierOnly" in err_msg or "free tier" in err_msg.lower()
            )
            if is_free_tier:
                platform = (
                    "阿里云百炼 (Bailian)"
                    if any(k in resolved_id for k in ("qwen", "deepseek", "llama"))
                    else "火山引擎 (Volcengine)"
                )
                usage_tracker.blacklist_model(
                    resolved_id,
                    reason="FreeTier Limit (Switch Required)",
                    permanent=True,
                )
                background_tasks.add_task(model_manager.run_health_check)
                out.append(
                    f"\n\n> [!CAUTION]\n"
                    f"> **检测到算力配额冲突 (403)**\n> \n"
                    f"> **平台来源**: {platform}\n"
                    f"> **架构自愈中**: 您的账号目前开启了\"仅限免费额度\"保护。"
                    f"系统已封禁该节点，并同步启动后台探测全场可用性。\n> \n"
                    f"> **📊 资源消耗公开**: 节点 `{resolved_id}` 今日消耗 `{consumed:,}` Tokens。"
                )
            else:
                usage_tracker.blacklist_model(
                    resolved_id,
                    reason="Provider Quota Exhausted (403)",
                    permanent=True,
                )
                background_tasks.add_task(model_manager.run_health_check)
                out.append(
                    f"\n\n> [!WARNING]\n"
                    f"> **算力配额熔断 (403)**\n"
                    f"> 当前模型 `{resolved_id}` 已耗尽。"
                    f"系统已启动后台自检排查，自动锁定健康的存活模型。"
                )
        return out

    # 3. 模型标识符缺失
    if "Model not found" in err_msg:
        out.append(
            "\n[算力链路异常]: 找不到模型标识符。请检查 llm_providers.json 配置。"
        )
        return out

    # 4. 兜底
    out.append(f"\n[核心审计异常]: 处理中断。详细信息: {err_msg[:50]}...")
    return out
