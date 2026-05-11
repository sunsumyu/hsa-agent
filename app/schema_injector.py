"""
app/schema_injector.py
======================
[企业级可复用模块] 精准 Schema 注入器 (V80.0)

基于物理真相中心（SchemaManager）动态生成提示，确保 Agent 看到的字段与物理库 100% 同步。
"""

from __future__ import annotations
import os
import re
from typing import List, Dict, Optional, Tuple
from loguru import logger
from app.schema_manager import schema_manager

class SchemaInjector:
    """
    [V80.0] 精准 Schema 注入器。
    """

    def __init__(
        self,
        external_schema_file: Optional[str] = None,
    ):
        self._external_file = external_schema_file
        self._extended_seeds: Optional[List[Dict]] = None 

    def _get_all_seeds(self) -> List[Dict]:
        """合并 SchemaManager 的物理元数据与外部文档定义"""
        if self._extended_seeds is not None:
            return self._extended_seeds

        # 1. 获取物理库全量字段
        all_seeds = list(schema_manager.get_metadata())

        # 2. 补齐搜索关键词（基于描述和字段名）
        for seed in all_seeds:
            if "keywords" not in seed:
                seed["keywords"] = [seed["field"]]
                if seed.get("desc"):
                    seed["keywords"].extend(re.split(r'[,，、]', seed["desc"]))

        # 3. 补齐外部文档定义
        if self._external_file and os.path.exists(self._external_file):
            try:
                extra = self._parse_external_schema(self._external_file)
                all_seeds.extend(extra)
                logger.debug(f"[SchemaInjector] 外部字典加载完成，新增 {len(extra)} 个字段")
            except Exception as e:
                logger.warning(f"[SchemaInjector] 外部字典解析失败（不影响使用）: {e}")

        self._extended_seeds = all_seeds
        return all_seeds

    def inject(
        self,
        user_question: str,
        top_k: int = 10,
        max_chars: int = 1200,
        include_warning: bool = True,
    ) -> str:
        """根据用户问题生成精准的 Schema Hint。"""
        if not user_question or not user_question.strip():
            return self._format_warning() if include_warning else ""

        seeds = self._get_all_seeds()
        scored = self._score_fields(user_question, seeds)
        top_fields = scored[:top_k]

        if not top_fields:
            return self._format_warning() if include_warning else ""

        lines = []
        if include_warning:
            lines.append("**[Schema 推荐] 以下为物理库中探测到的相关字段。严禁使用此处未列出的字段：**\n")

        seen_fields = set()
        for field_dict, score in top_fields:
            fname = field_dict["field"]
            if fname in seen_fields: continue
            seen_fields.add(fname)

            table = field_dict.get("table", "")
            desc = field_dict.get("desc", "")
            lines.append(f"- `{fname}` [{table}]: {desc}")

        result = "\n".join(lines)
        return result[:max_chars] if len(result) > max_chars else result

    def get_field_names(self, user_question: str, top_k: int = 10) -> List[str]:
        seeds = self._get_all_seeds()
        scored = self._score_fields(user_question, seeds)
        return [d["field"] for d, _ in scored[:top_k]]

    def _score_fields(self, user_question: str, seeds: List[Dict]) -> List[Tuple[Dict, float]]:
        text = user_question.lower()
        scored = []
        for seed in seeds:
            score = 0.0
            keywords = seed.get("keywords", [])
            desc = seed.get("desc", "")
            
            for kw in keywords:
                if kw.lower() in text: score += 2.0
            if seed["field"].lower() in text: score += 5.0
            if score > 0: scored.append((seed, score))
        return sorted(scored, key=lambda x: x[1], reverse=True)

    def _parse_external_schema(self, filepath: str) -> List[Dict]:
        extra = []
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
        pattern = re.compile(r'\|\s*(`?)(\w+)\1\s*\|[^|]*\|([^|]+)\|')
        for m in pattern.finditer(content):
            fname, desc = m.group(2).strip(), m.group(3).strip()
            if fname and desc and len(fname) > 2:
                extra.append({"field": fname, "desc": desc[:80], "table": "external"})
        return extra

    @staticmethod
    def _format_warning() -> str:
        return "**[Schema 警告] 未检索到物理字段，请确保查询逻辑符合 Physical Blueprint。**"

schema_injector = SchemaInjector(
    external_schema_file="e:/chain/hsa-agent-python/docs/db_schema_clickhouse.md"
)
