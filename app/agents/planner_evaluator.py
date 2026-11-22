"""
app/agents/planner_evaluator.py
=================================
[SPEC-227 / Matt Pocock Deep Module] 规划器动作缓存仲裁与响应解析深模块 (Planner Evaluator)

核心职责：
1. 经验缓存仲裁与脏数据物理淘汰：
   - 校验缓存版本指纹一致性；
   - 刚性业务契约：全量排查任务绝不采纳带 LIMIT 的抽样历史 SQL，就地执行物理淘汰；
   - 命中时生成包含标准证据链的只读字典。
2. 规划器 LLM 输出高保真解析：
   - 纯函数解析 Markdown 规划文本（支持 ### METHODOLOGY 与 ### TASKS 章节），分离方法论与任务清单；
   - 兼容纯列表兜底，自动过滤清洗无序与有序标号。
"""

from __future__ import annotations
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from loguru import logger


_CENSUS_KEYWORDS = ("排查", "全量", "全市", "字典", "名录", "普查", "层级", "全部")


def evaluate_action_cache(
    user_input: str,
    target_prompt_ver: str = "2.0",
) -> Optional[Dict[str, Any]]:
    """
    检查并仲裁语义动作缓存。若命中且符合版本与业务契约，返回规划字典；否则返回 None。
    """
    disable_cache = os.getenv("DISABLE_AUDIT_CACHE", "false").lower() == "true"
    if disable_cache or not user_input:
        return None

    from app.core.memory.semantic_memory import action_cache_manager

    candidate = action_cache_manager.search(user_input)
    if not candidate:
        return None

    # 1. 检查版本指纹
    cached_prompt_ver = candidate.get("prompt_version")
    if cached_prompt_ver != target_prompt_ver:
        logger.info(f"🔄 [PlannerEvaluator] 缓存版本陈旧 ({cached_prompt_ver} != {target_prompt_ver})，跳过缓存")
        return None

    # 2. 检查运行时业务契约
    cached_sql = str(candidate.get("sql", "") or "")
    sql_upper = cached_sql.upper()
    if any(kw in user_input for kw in _CENSUS_KEYWORDS) and "LIMIT" in sql_upper:
        logger.warning(f"⚠️ [PlannerEvaluator] 全量排查任务拒绝带 LIMIT 的脏缓存，执行物理淘汰: {cached_sql[:50]}")
        action_cache_manager.evict(candidate.get("question", user_input))
        return None

    logger.success("⚡ [PlannerEvaluator] 契约与指纹校验通过，命中动作链缓存")
    return {
        "tasks": candidate.get("tasks", ["执行已验证的精准 SQL"]),
        "methodology": candidate.get("methodology", "基于历史成功经验的快速路径"),
        "sql_query": candidate.get("sql"),
        "sql_history": [candidate.get("sql")] if candidate.get("sql") else [],
        "cache_hit": True,
        "messages": [],
    }


def parse_planner_response(content: str) -> Tuple[str, List[str]]:
    """
    纯函数解析大模型生成的规划内容，提取 (methodology, tasks)。
    """
    clean_content = str(content or "").strip()
    if not clean_content:
        return "", []

    methodology = ""
    tasks: List[str] = []

    _PREFIX_RE = re.compile(r"^(?:[\-\*]|\d+[\.\、\)])\s*")

    if "### METHODOLOGY" in clean_content:
        parts = clean_content.split("### TASKS")
        methodology = parts[0].replace("### METHODOLOGY", "").strip()
        if len(parts) > 1:
            task_part = parts[1].strip()
            tasks = [
                _PREFIX_RE.sub("", line).strip()
                for line in task_part.split("\n")
                if line.strip().startswith(("-", "*")) or re.match(r"^\d+[\.\、\)]", line.strip())
            ]
    else:
        tasks = [
            _PREFIX_RE.sub("", line).strip()
            for line in clean_content.split("\n")
            if line.strip().startswith(("-", "*")) or re.match(r"^\d+[\.\、\)]", line.strip())
        ]

    # 去除空条目
    tasks = [t for t in tasks if t]
    return methodology, tasks
