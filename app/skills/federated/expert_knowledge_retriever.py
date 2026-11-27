"""
app/skills/expert_knowledge_retriever.py
========================================
专家知识与医疗编码映射检索深模块（Deep Module）

职责：
- 从 YAML 文件加载并缓存医保审计专家提示知识库
- 主题级关键词语义检索与提示建议渲染
- 检索 ICD-10 / ICD-9 专业医疗编码映射分类建议
"""

from __future__ import annotations

import os
import json
from typing import Dict, Any, List, Optional
from loguru import logger

_DEFAULT_KB_YAML_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "configs", "expert_knowledge.yaml"
)
_DEFAULT_CODES_JSON_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "configs", "audit_knowledge_base.json"
)

_EXPERT_KB_CACHE: Optional[Dict[str, Any]] = None


def load_expert_kb(file_path: Optional[str] = None) -> Dict[str, Any]:
    """
    加载并缓存医保审计专家知识库。
    """
    global _EXPERT_KB_CACHE
    if _EXPERT_KB_CACHE is not None and file_path is None:
        return _EXPERT_KB_CACHE

    path = file_path or _DEFAULT_KB_YAML_PATH
    try:
        import yaml
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                loaded = yaml.safe_load(f) or {}
                if file_path is None:
                    _EXPERT_KB_CACHE = loaded
                return loaded
        else:
            logger.warning(f"[ExpertKB] 配置文件不存在: {path}")
    except Exception as e:
        logger.warning(f"[ExpertKB] load failed from {path}: {e}")

    return {}


def search_expert_knowledge_hints(query: str, kb_path: Optional[str] = None) -> str:
    """
    检索医保审计专家知识库。从 expert_knowledge.yaml 加载由主题索引的专家提示。
    """
    if not query or not query.strip():
        return "⚠️ 查询为空"

    kb = load_expert_kb(kb_path)
    topics: List[Dict[str, Any]] = kb.get("topics", [])
    if not topics:
        return "⚠️ 专家知识库未配置 (configs/expert_knowledge.yaml)"

    q_lower = query.lower()
    matched = []
    for topic in topics:
        keywords = topic.get("keywords", [])
        if any(kw.lower() in q_lower for kw in keywords):
            matched.append(
                f"【{topic.get('title', '')}】{topic.get('hint', '')}"
            )

    if not matched:
        return f"未检索到与 '{query}' 匹配的专家知识。已收录主题: " + ", ".join(
            t.get("title", "") for t in topics
        )

    return "\n\n".join(matched)


def resolve_medical_code_mapping(intent: str, kb_path: Optional[str] = None) -> str:
    """
    业务深度增强：从知识库检索医疗编码建议 (ICD-10/ICD-9)。
    """
    if not intent or not intent.strip():
        return "⚠️ 检索意图为空"

    path = kb_path or _DEFAULT_CODES_JSON_PATH
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                kb = json.load(f).get("medical_codes", {})
        else:
            kb = {}
    except Exception as e:
        logger.error(f"[MedicalCodes] 加载知识库异常: {e}")
        return "⚠️ 知识库加载失败"

    q = intent.strip()
    matched = []
    for k, v in kb.items():
        if k in q or q in k:
            res = f"【{k}】专业编码映射建议：\n"
            if "icd10" in v:
                res += f"- ICD-10 (疾病): {v['icd10'][0]} 至 {v['icd10'][1]}\n"
            res += f"- 业务说明: {v.get('desc', '')}"
            matched.append(res)

    if not matched:
        return f"未找到与 '{intent}' 相关的专业分类。建议直接尝试 LIKE '%{intent}%'。"

    return "\n\n".join(matched)
