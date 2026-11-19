"""
domains/legal/registry/precedent_registry.py
============================================
最高人民法院指导案例与民商事司法裁判要旨知识库 (Precedent & Case Law Registry)。
支持：
1. 按案由检索对应最高院指导案例与公报案例
2. 提取裁判要旨 (Referee Summary) 与司法审判规则 (Application Rule)
3. 赋能 JudgeAdjudicator 进行"同案同判"与案例引证
"""

from __future__ import annotations

import os
import yaml
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class PrecedentCase(BaseModel):
    case_id: str
    case_name: str
    court: str
    case_number: str
    cause_of_action: str
    keywords: List[str] = Field(default_factory=list)
    key_facts: str
    referee_summary: str
    application_rule: str


class PrecedentRegistry:
    def __init__(self, yaml_path: Optional[str] = None):
        if not yaml_path:
            yaml_path = os.path.join(os.path.dirname(__file__), "precedents.yaml")
        self.yaml_path = yaml_path
        self._cases: List[PrecedentCase] = []
        self._load()

    def _load(self):
        if not os.path.exists(self.yaml_path):
            return
        with open(self.yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if data and isinstance(data, list):
                self._cases = [PrecedentCase(**item) for item in data]

    def get_precedents_by_cause(self, cause: str) -> List[PrecedentCase]:
        return [c for c in self._cases if c.cause_of_action == cause]

    def match_precedents(self, cause: str, text: str, top_k: int = 2) -> List[PrecedentCase]:
        candidates = self.get_precedents_by_cause(cause)
        if not candidates:
            return self._cases[:top_k]
        
        # 简单关键词匹配计分
        scored: List[tuple[int, PrecedentCase]] = []
        for c in candidates:
            score = 1  # 基础分
            for kw in c.keywords:
                if kw in text:
                    score += 2
            scored.append((score, c))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item[1] for item in scored[:top_k]]


precedent_registry = PrecedentRegistry()
