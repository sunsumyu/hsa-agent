"""
app/core/context_selector.py
============================
[V200.0] 工业级自适应 Token 精选引擎 (Adaptive Token Selector)

核心职责：
基于 Token 预算感知，在运行时动态裁剪上下文中的表结构描述与历史审计经验，
防止超限引发的限流崩溃。
"""

from typing import List, Tuple, Any
from app.core.registry.schema_registry import SchemaRegistryEntry

class AdaptiveSelector:
    @staticmethod
    def calculate_tokens(text: str) -> int:
        """
        Token 计算估计器 (工业级鲁棒估算，中文字符与英文字符混合计算)
        中文字符算 0.8 token，英文单词算 0.3 token，安全基准线
        """
        if not text:
            return 0
        return int(len(text) * 0.8)

    @staticmethod
    def schema_to_xml(entry: SchemaRegistryEntry) -> str:
        """将 SchemaRegistryEntry 序列化为高解析效能的 XML"""
        xml = f'<table name="{entry.name}" description="{entry.description}">\n'
        for field in entry.fields:
            name = field.get("name", "")
            ftype = field.get("type", "")
            desc = field.get("description", "")
            xml += f'  <field name="{name}" type="{ftype}" description="{desc}" />\n'
        xml += '</table>'
        return xml

    @staticmethod
    def schema_to_header_only(entry: SchemaRegistryEntry) -> str:
        """预算紧张时的降级方案：仅输出表名与业务描述"""
        return f'<table name="{entry.name}" description="{entry.description}" status="FIELDS_OMMITTED_DUE_TO_BUDGET_LIMITS" />'

    def select_adaptively(
        self, 
        budget: int, 
        schemas: List[SchemaRegistryEntry], 
        memories: List[Any]
    ) -> Tuple[List[str], List[str]]:
        """
        基于当前 Token 预算弹性裁剪内容。
        优先级排布：用户指令与模板 (保留) > 数据库 Schema (Detail -> Header) > 经验库 (Top-N -> Top-1 -> 抛弃)
        """
        current_used = 0
        final_schemas: List[str] = []
        final_memories: List[str] = []

        # 1. 优先精选数据库 Schema
        # 分配总预算的 60% 给数据库结构，确保生成 SQL 字段准确
        schema_budget = budget * 0.6
        for entry in schemas:
            detail_xml = self.schema_to_xml(entry)
            detail_tokens = self.calculate_tokens(detail_xml)
            
            if current_used + detail_tokens < schema_budget:
                final_schemas.append(detail_xml)
                current_used += detail_tokens
            else:
                # 触发降级机制
                header_xml = self.schema_to_header_only(entry)
                final_schemas.append(header_xml)
                current_used += self.calculate_tokens(header_xml)

        # 2. 精选语义经验库
        # 分配总预算的 30% 给经验库，保证推理相似性
        experience_budget = budget * 0.9
        for mem in memories:
            content = ""
            if isinstance(mem, str):
                content = mem
            elif hasattr(mem, 'content'):
                content = getattr(mem, 'content')
            elif isinstance(mem, dict):
                content = mem.get('content', '') or mem.get('experience', '')
            
            if not content:
                continue

            token_cost = self.calculate_tokens(content)
            if current_used + token_cost < experience_budget:
                # 包装为标准的 XML 经验格式
                xml_mem = f'<experience>\n  {content}\n</experience>'
                final_memories.append(xml_mem)
                current_used += token_cost
            else:
                # 预算用尽，优雅丢弃后续经验
                break

        return final_schemas, final_memories
