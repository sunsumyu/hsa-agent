"""
app/core/memory/types/perceptual.py
===================================
[V4.0] 感知记忆层 (Perceptual Memory Type) - 多模态感知专家
"""

from typing import List, Any, Optional, Dict, Union
import os
from loguru import logger
from datetime import datetime
from app.core.memory.base import MemoryItem
from app.core.memory.storage.vector import VectorStorage

class PerceptualMemory:
    """
    感知记忆：支持图像、音频等多模态数据的向量化存储与跨模态检索。
    """
    def __init__(self, storage: VectorStorage):
        self.storage = storage
        self._clip_model = None
        self._init_failed = False
        self._init_models()

    def _init_models(self):
        """物理加载多模态感知模型 (CLIP)"""
        if self._init_failed:
            return
            
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("📡 [PerceptualMemory] 正在通过物理镜像站 (hf-mirror.com) 下载/加载感知模型...")
            
            # 使用正确的短名称，否则库会找不到核心配置文件并抛出假连接错误
            self._clip_model = SentenceTransformer('clip-ViT-B-32')
            logger.info("✅ [PerceptualMemory] 多模态感知模型 (clip-ViT-B-32) 物理挂载成功。")
        except Exception as e:
            logger.warning(f"⚠️ [PerceptualMemory] 感知模型 (CLIP) 物理加载失败，已自动降级为纯文本模式。原因: {str(e)[:100]}")
            self._clip_model = None
            self._init_failed = True

    def _convert_to_markdown(self, path: str) -> str:
        """
        [V4.6] 统一文档转换引擎
        将 PDF, Office, 图片等资产统一解析为 Markdown。
        """
        if not os.path.exists(path): return ""
        ext = os.path.splitext(path).lower()
        
        # 针对图片返回占位符（后续由 CLIP 处理）
        if ext in ('.jpg', '.jpeg', '.png', '.bmp'): return ""

        try:
            # 尝试使用企业级 MarkItDown 库
            from markitdown import MarkItDown
            md = MarkItDown()
            result = md.convert(path)
            return getattr(result, "text_content", "")
        except Exception:
            # Fallback: 基础文本读取
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            except: return ""

    async def add_image(self, image_path: str, description: str = "", importance: float = 0.5, **metadata):
        """
        [V4.6] 资产载入入口 (多模态升级)
        支持图像视觉特征提取与文档 Markdown 文本索引。
        """
        if not self._clip_model and not self._init_failed: 
            self._init_models()
        
        # 1. 物理转换：提取资产内容
        doc_content = self._convert_to_markdown(image_path)
        combined_content = f"{description}\n\n[Asset Content]:\n{doc_content}" if doc_content else description
        
        try:
            item = MemoryItem(
                content=combined_content,
                memory_type="perceptual",
                importance=importance,
                metadata={
                    "modality": "document" if doc_content else "image",
                    "file_path": image_path,
                    "has_text": bool(doc_content),
                    **metadata
                }
            )

            # 2. 视觉特征路径 (针对图片资产)
            ext = os.path.splitext(image_path)[1].lower()
            if ext in ('.jpg', '.jpeg', '.png') and self._clip_model:
                from PIL import Image
                img = Image.open(image_path)
                
                class ImageEmbeddingWrapper:
                    def __init__(self, model, image):
                        self.model = model
                        self.image = image
                    def embed_documents(self, _):
                        return self.model.encode([self.image]).tolist()
                
                await self.storage.add([item], embeddings_engine=ImageEmbeddingWrapper(self._clip_model, img))
                logger.info(f"📸 [Perceptual] 已完成视觉资产物理固化: {os.path.basename(image_path)}")
            
            # 3. 文本语义路径 (针对文档资产或模型缺失降级)
            else:
                await self.storage.add([item])
                logger.info(f"📄 [Perceptual] 已完成文档资产语义索引: {os.path.basename(image_path)}")
                
        except Exception as e:
            logger.error(f"❌ 资产载入物理失败: {e}")

    async def recall(self, query: Union[str, Any], limit: int = 5, tenant_id: str = "default") -> List[MemoryItem]:
        """[V4.6] 企业级感知召回：支持视觉对齐与元数据降级搜索"""
        if not self._clip_model and not self._init_failed: 
            self._init_models()
        
        # 路径 A: 视觉语义对齐 (文搜图)
        if isinstance(query, str) and self._clip_model:
            try:
                query_vector = self._clip_model.encode(query).tolist()
                return await self.storage.search(limit=limit, tenant_id=tenant_id, query_vector=query_vector)
            except Exception as e:
                logger.error(f"感知对齐搜索失败: {e}")
        
        # 路径 B: 元数据语义检索 (降级模式)
        # 直接使用文本进行搜索，召回 metadata.description 匹配的图像
        logger.debug("🔎 [Perceptual] 正在通过元数据语义路径执行召回...")
        return await self.storage.search(query=str(query), limit=limit, tenant_id=tenant_id)

    def format_perceptual_for_prompt(self, items: List[MemoryItem]) -> str:
        """将感知记忆格式化为提示词"""
        if not items: return "未找到相关的感知凭证（如图像、发票截图）。"
        
        lines = ["【关联的感知凭证与视觉证据】"]
        for i, item in enumerate(items, 1):
            desc = item.metadata.get("description", "无描述")
            path = item.metadata.get("file_path", "未知路径")
            lines.append(f"{i}. 凭证说明: {desc} (路径: {path})")
            
        return "\n".join(lines)
