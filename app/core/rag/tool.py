"""
app/core/rag/tool.py
====================
[V4.6] 企业级 RAG 专家知识库工具
提供多模态文档载入、结构化检索与知识管理能力。
"""

import os
from typing import List, Dict, Any, Optional
from loguru import logger
from app.core.memory import memory_hub
from app.core.memory.rag_utils import approx_token_len

class RAGTool:
    """
    RAG 工具集：负责将静态文档转化为 Agent 可调用的动态知识。
    """
    
    def __init__(self, knowledge_base_path: str = "data/knowledge_base"):
        self.kb_path = knowledge_base_path
        os.makedirs(self.kb_path, exist_ok=True)
        logger.info(f"🚀 [RAGTool] 知识库已挂载: {self.kb_path}")

    async def add_document(self, file_path: str, importance: float = 0.9) -> Dict[str, Any]:
        """
        [V4.6] 多模态文档注入接口
        1. 自动转换格式 (PDF/Office -> Markdown)
        2. 结构化分块 (Heading-Aware)
        3. 注入语义记忆
        """
        if not os.path.exists(file_path):
            return {"status": "ERROR", "message": f"文件不存在: {file_path}"}
        
        doc_name = os.path.basename(file_path)
        
        try:
            # 1. 物理层解析 (借用 PerceptualMemory 的转换能力)
            from app.core.memory.types.perceptual import PerceptualMemory
            # 这里我们直接手动执行转换逻辑
            content = self._extract_content(file_path)
            
            if not content.strip():
                return {"status": "ERROR", "message": "文档解析结果为空，可能格式不受支持或文件已加密。"}
            
            # 2. 注入语义记忆 (内部执行分块)
            await memory_hub.semantic.learn_document(
                text=content,
                doc_name=doc_name,
                importance=importance
            )
            
            return {
                "status": "SUCCESS",
                "document": doc_name,
                "approx_tokens": approx_token_len(content),
                "message": f"文档 '{doc_name}' 已成功索引至语义知识库。"
            }
            
        except Exception as e:
            logger.error(f"❌ [RAGTool] 文档入库失败: {e}")
            return {"status": "ERROR", "message": str(e)}

    async def search_knowledge(self, query: str, limit: int = 5) -> str:
        """基础语义检索 (Backward compatibility)"""
        return await self.search_knowledge_expanded(query, limit=limit, enable_mqe=False, enable_hyde=False)

    async def search_knowledge_expanded(
        self, 
        query: str, 
        limit: int = 5,
        enable_mqe: bool = True,
        enable_hyde: bool = True,
        candidate_pool_multiplier: int = 3
    ) -> str:
        """
        [V4.6] 扩展检索框架 (MQE + HyDE)
        通过生成多维度查询扩展，大幅提升复杂审计场景下的召回率。
        """
        from app.core.memory.rag_utils import generate_mqe_queries, generate_hyde_document, preprocess_markdown_for_embedding
        
        # 1. 构造扩展查询列表
        expansions = [query]
        if enable_mqe:
            mqe_list = await generate_mqe_queries(query)
            expansions.extend(mqe_list)
        if enable_hyde:
            hyde_doc = await generate_hyde_document(query)
            if hyde_doc: expansions.append(hyde_doc)
            
        # 去重
        expansions = list(dict.fromkeys(expansions))
        logger.info(f"🔍 [RAGTool] 执行扩展检索，查询数: {len(expansions)}")

        # 2. 并行检索
        pool_limit = limit * candidate_pool_multiplier
        agg_results = {} # {content_hash: MemoryItem}
        
        for q in expansions:
            # 预处理查询
            clean_q = preprocess_markdown_for_embedding(q)
            hits = await memory_hub.semantic.recall(clean_q, limit=pool_limit)
            
            for item in hits:
                # 使用内容 + 标题路径作为唯一标识进行去重
                uid = f"{item.metadata.get('heading_path','')}_{item.content[:50]}"
                if uid not in agg_results or item.score > agg_results[uid].score:
                    agg_results[uid] = item
        
        # 3. 排序与截断
        sorted_hits = sorted(agg_results.values(), key=lambda x: x.score, reverse=True)[:limit]
        
        if not sorted_hits:
            return "🔍 [RAG] 未在知识库中找到相关合规性依据。"
        
        formatted = [f"【RAG 专家检索报告 - 基于 {len(expansions)} 组查询扩展】"]
        for i, item in enumerate(sorted_hits, 1):
            source = item.metadata.get("source", "Unknown")
            path = item.metadata.get("heading_path", "ROOT")
            # 标记来源类型
            formatted.append(f"{i}. [来源: {source}] | [层级: {path}]\n   内容: {item.content.strip()}\n")
            
        return "\n".join(formatted)

    def _extract_content(self, path: str) -> str:
        """内部转换引擎：支持 MarkItDown 与基础 Fallback"""
        ext = os.path.splitext(path)[1].lower()
        
        # 尝试使用 MarkItDown
        try:
            from markitdown import MarkItDown
            md = MarkItDown()
            result = md.convert(path)
            return getattr(result, "text_content", "")
        except Exception:
            # Fallback: 基础读取
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            except: return ""

# 全局单例
rag_tool = RAGTool()
