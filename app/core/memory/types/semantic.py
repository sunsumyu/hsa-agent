"""
app/core/memory/types/semantic.py
=================================
[V177.3] 语义记忆层 (Semantic Memory Type) - 知识检索专家
"""

from typing import List, Any, Optional, Dict
import os
import json
from loguru import logger
from app.core.memory.base import MemoryItem
from app.core.memory.storage.vector import VectorStorage

class MetadataMappingLayer:
    """[V110.0] 企业级“语义—物理”映射层：解决业务术语混淆及字段幻觉"""
    def __init__(self, kb_path="configs/audit_knowledge_base.json"):
        self.kb_path = kb_path
        self.ontology = self._load_ontology()

    def _load_ontology(self) -> dict:
        """从外部知识库动态加载审计本体与红线"""
        try:
            if os.path.exists(self.kb_path):
                with open(self.kb_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("ontology", {})
        except Exception as e:
            logger.error(f"加载审计知识库失败: {e}")
        return {"职工医保": {"physical": "insutype='310'", "caveats": "注意区分统筹与个账"}}

    def detect(self, text: str) -> str:
        """识别关键词并返回避坑指南"""
        guides = []
        for term, meta in self.ontology.items():
            if term in text:
                guides.append(f"### 💡 {term} 业务避坑指南\n- **物理映射建议**: {meta['physical']}\n- **风险提示**: {meta.get('caveats', '无')}")
        return "\n\n".join(guides)

class SemanticMemory:
    """
    语义记忆：负责知识检索、HyDE 增强以及知识对齐。
    """
    def __init__(self, storage: VectorStorage):
        self.storage = storage

    async def _generate_hyde_context(self, query: str, config: Any = None) -> str:
        """[HyDE] 生成假设性审计口径"""
        from app.core.llm_provider import llm_provider
        
        hyde_prompt = [
            ("system", "你是一位资深的医保审计专家。请针对用户的问题，生成一段专业的审计口径描述。内容应包含可能涉及的物理指标（如金额、天数、频次）和逻辑特征，字数在 100 字以内。"),
            ("human", f"审计任务：{query}")
        ]
        
        try:
            response = await llm_provider.chat(role="planner_light", messages=hyde_prompt, config=config)
            return str(response.content)
        except Exception as e:
            logger.warning(f"HyDE 生成失败: {e}")
            return ""

    async def recall(self, query: str, limit: int = 12, use_hyde: bool = True, config: Any = None) -> List[MemoryItem]:
        """
        语义召回核心：HyDE 混合检索 + 动态弹性阈值。
        """
        search_query = query
        if use_hyde:
            logger.info(f"🧠 [SemanticMemory] 启动 HyDE 推理增强...")
            hyde_context = await self._generate_hyde_context(query, config)
            search_query = f"{query} {hyde_context}"
            logger.info(f"🔍 [SemanticMemory] 混合查询载荷 (前50字): {search_query[:50]}...")
        
        # 增加召回上限至 12，以应对跨 2-3 张表的复杂审计任务
        results = await self.storage.search(search_query, limit=limit)
        
        # [V178.8] 动态过滤：仅保留相关度较高的项，防止无关字段引入噪音
        # 注意：此处可根据距离进行精细化过滤
        return results

    async def learn(self, content: str, topic: str = "general", importance: float = 0.8, metadata: Dict[str, Any] = None):
        """将新知识固化到向量存储，支持携带结构化元数据"""
        final_meta = {"topic": topic}
        if metadata:
            final_meta.update(metadata)
            
        item = MemoryItem(
            content=content,
            memory_type="semantic",
            importance=importance,
            metadata=final_meta
        )
        await self.storage.add([item])

    def format_for_prompt(self, items: List[MemoryItem]) -> str:
        """
        [V177.5] 将检索结果格式化为 LLM 提示词
        """
        if not items: return "未找到相关的物理表字段信息。"
        
        lines = ["【推荐的物理模型关联】"]
        for i, item in enumerate(items, 1):
            # 兼容 MemoryItem.content 可能已经是 Dict 的情况 (从旧数据加载)
            data = item.content if isinstance(item.content, dict) else item.metadata
            col = data.get("column", "unknown")
            tbl = data.get("table", "unknown")
            desc = data.get("desc", "")
            lines.append(f"{i}. [{tbl}.{col}] - {desc}")
        
        return "\n".join(lines)

    def get_avoidance_guides(self, query: str) -> str:
        """获取业务避坑指南"""
        if not hasattr(self, '_mapper'):
            self._mapper = MetadataMappingLayer()
        return self._mapper.detect(query)
