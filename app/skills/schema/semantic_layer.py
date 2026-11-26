"""
app/skills/semantic_layer.py
============================
[Matt Pocock Deep Module / Facade]
医保审计语义召回层门面模块。
对外暴露统一的语义检索接口，内部委托至百科解析器、HyDE 生成器、向量索引器与提示词格式化器。
"""
import json
import os
from typing import List, Dict, Any, Optional
from loguru import logger

# [SSOT] 业务避坑指南统一归位至 app.core.memory.types.semantic
from app.core.memory.types.semantic import MetadataMappingLayer

# 引入深模块
from app.skills.schema.semantic_encyclopedia_parser import SemanticEncyclopediaParser
from app.skills.schema.semantic_hyde_generator import SemanticHydeGenerator
from app.skills.schema.semantic_prompt_formatter import SemanticPromptFormatter

# [V66.2] 物理常驻：模块级嵌入模型单例，消除重复加载开销
_GLOBAL_EMBEDDING_MODEL = None


def get_embedding_model():
    """获取模块级常驻嵌入模型单例"""
    global _GLOBAL_EMBEDDING_MODEL
    if _GLOBAL_EMBEDDING_MODEL is None:
        try:
            import torch
            torch.set_num_threads(2)
            from sentence_transformers import SentenceTransformer
            os.environ["HF_ENDPOINT"] = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")
            logger.info(">>> [语义层] 正在加载嵌入模型...")
            _GLOBAL_EMBEDDING_MODEL = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2", device="cpu")
        except Exception as e:
            logger.warning(f"⚠️ [语义层] 嵌入模型加载异常 (跳过向量检索降级为纯场景规则): {e}")
            return None
        except BaseException as e:
            logger.warning(f"⚠️ [语义层] 嵌入模型严重异常 (内存受限降级): {e}")
            return None
    return _GLOBAL_EMBEDDING_MODEL


class _MetadataExtractor(SemanticEncyclopediaParser):
    """向后兼容别名：从百科文档中提取字段语义元数据的基类"""
    pass


class SemanticRetriever(_MetadataExtractor):
    """
    [Deep Module / Facade] 医保全域语义向量检索门面。
    聚合了百科解析、HyDE 假设性推理、FAISS 向量检索及防踩坑提示注入。
    """

    def __init__(self, data_dir: str = "data/semantic_index", schema_file: Optional[str] = None):
        super().__init__(schema_file=schema_file)
        self.data_dir = data_dir
        self.index = None
        self.column_metadata: List[Dict[str, Any]] = []
        os.makedirs(self.data_dir, exist_ok=True)

    def _get_model(self):
        return get_embedding_model()

    def build_index(self):
        """构建向量索引容器并持久化"""
        import faiss

        index_path = os.path.join(self.data_dir, "vector.index")
        meta_path = os.path.join(self.data_dir, "metadata.json")

        # 优先从磁盘加载缓存索引
        if os.path.exists(index_path) and os.path.exists(meta_path):
            try:
                self.index = faiss.read_index(index_path)
                with open(meta_path, "r", encoding="utf-8") as f:
                    self.column_metadata = json.load(f)
                logger.info(f"✅ [语义层] 已从磁盘加载缓存索引 (字段数 {len(self.column_metadata)})")
                return
            except Exception as e:
                logger.warning(f"加载缓存索引失败: {e}，正在重新构建...")

        # 1. 提取元数据
        if not self.column_metadata:
            self.column_metadata = self.extract_metadata()

        # 2. 准备向量
        model = self._get_model()
        if model is None:
            logger.warning("⚠️ [语义层] 嵌入模型不可用，跳过向量索引构建")
            return

        texts = [item["full_text"] for item in self.column_metadata]
        logger.info(f">>> [语义层] 正在对 {len(texts)} 个字段进行向量编码...")
        embeddings = model.encode(texts, show_progress_bar=True)

        # 3. 建立 FAISS 索引
        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dimension)
        faiss.normalize_L2(embeddings)
        self.index.add(embeddings.astype("float32"))

        # 4. 持久化到磁盘
        try:
            faiss.write_index(self.index, index_path)
            tmp_path = f"{meta_path}.tmp.{os.getpid()}"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self.column_metadata, f, ensure_ascii=False)
            os.replace(tmp_path, meta_path)
            logger.info("✅ [语义层] 索引已成功持久化至磁盘")
        except Exception as e:
            logger.error(f"持久化索引失败: {e}")

        logger.success(f"✅ 语义索引构建成功 | 维度: {dimension}")

    async def _generate_hyde_context(self, query: str, config: Any = None) -> str:
        """HyDE 假设性审计上下文生成委托"""
        return await SemanticHydeGenerator.generate_hyde_context(query, config=config)

    async def get_relevant_columns(self, queries: list, k: int = 10, config: Any = None) -> List[Dict[str, Any]]:
        """执行语义搜索 [HyDE 增强检索 + 极速旁路]"""
        if not queries:
            return []

        user_query = " ".join(queries)

        # 极速旁路 (Bypass)：针对高频关键词直接返回核心维度，跳过 Embedding 加载
        FAST_KEYWORDS = {
            "医院": ["org_name", "org_id"],
            "费用": ["medfee_sumamt", "fund_pay_sumamt"],
            "天数": ["ipt_days", "stay_days"],
            "排名": ["org_name", "medfee_sumamt"],
            "年度": ["year", "setl_time"],
        }

        bypass_results = []
        if any(kw in user_query for kw in FAST_KEYWORDS):
            logger.info(">>> [⚡ HYPER-FAST] 检测到高频关键词，正在旁路向量检索以节省启动耗时...")
            for kw, cols in FAST_KEYWORDS.items():
                if kw in user_query:
                    for c in cols:
                        item = next((m for m in self.column_metadata if m["column"] == c), None)
                        if item:
                            bypass_results.append(item)

            if bypass_results:
                return bypass_results[:k]

        # 开启 HyDE 增强检索
        if self.index is None:
            self.build_index()

        if self.index is None or self._get_model() is None:
            logger.warning("⚠️ [语义层] 向量索引未就绪，降级为规则匹配")
            return bypass_results[:k]

        logger.info(f">>> [语义层] 正在启动 HyDE 增强推理: '{user_query[:30]}'")
        hyde_context = await self._generate_hyde_context(user_query, config)

        # 混合检索：原始问题 + 专家级上下文
        combined_query = f"{user_query} {hyde_context}"
        logger.info(f">>> [语义层] HyDE 推理结果: {hyde_context[:60]}...")
        logger.info(f">>> [语义层] 执行向量检索 '{combined_query[:50]}...'")

        import faiss

        # 1. 编码查询
        query_embedding = self._get_model().encode([combined_query])
        faiss.normalize_L2(query_embedding)

        # 2. 检索
        _, indices = self.index.search(query_embedding.astype("float32"), k)

        # 3. 过滤并返回结果
        results = []
        for idx in indices[0]:
            if idx < len(self.column_metadata):
                item = self.column_metadata[idx]
                results.append(item)

        return results

    def get_avoidance_guides(self, query_text: str) -> str:
        """获取避坑指南注入文本"""
        mapper = MetadataMappingLayer()
        return mapper.detect(query_text)

    def format_for_prompt(self, items: List[Dict[str, Any]]) -> str:
        """将检索结果格式化为带有防御性 Cast 建议的 Prompt 注入文本"""
        return SemanticPromptFormatter.format_for_prompt(items)


# 模块级单例 (向后兼容)
semantic_retriever = SemanticRetriever()
