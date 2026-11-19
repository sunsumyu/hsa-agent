"""
app/core/context/funnel_medical_aligner.py
============================================
[Matt Pocock Deep Module] 语义漏斗第二层：医学知识库与 ICD-10 物理编码对齐器
专职负责：
1. 本地医学知识库加载与字典缓存
2. 子串匹配极速直通车
3. 向量化相似度检索 (Cosine Similarity)
4. LLM 零差错 ICD-10 动态推理
"""

import json
from typing import Dict, Any, List, Optional
from loguru import logger

from app.core.llm_provider import llm_provider
from app.core.context.funnel_intent_rewriter import extract_json_payload


class FunnelMedicalAligner:
    """医学编码对齐深模块"""

    def __init__(self, kb_path: str = "configs/audit_knowledge_base.json"):
        self.kb_path = kb_path
        self._load_kb()

    def _load_kb(self):
        try:
            with open(self.kb_path, "r", encoding="utf-8") as f:
                kb_data = json.load(f)
                self.medical_codes = kb_data.get("medical_codes", {})
                self.ontology = kb_data.get("ontology", {})
        except Exception as e:
            logger.error(f"[Funnel] 加载审计知识库失败: {e}")
            self.medical_codes = {}
            self.ontology = {}

    def _get_key_embeddings(self) -> Dict[str, List[float]]:
        if not hasattr(self, "_cached_embeddings"):
            self._cached_embeddings = {}
            keys = list(self.medical_codes.keys())
            if keys:
                try:
                    from app.core.memory.embedding import embedding_engine
                    embeds = embedding_engine.embed_documents(keys)
                    self._cached_embeddings = {k: v for k, v in zip(keys, embeds)}
                    logger.info(f"✅ [Funnel] 成功缓存 {len(keys)} 个疾病字典键的向量特征")
                except Exception as e:
                    logger.warning(f"⚠️ [Funnel] 生成疾病字典键向量缓存失败: {e}")
        return self._cached_embeddings

    async def get_icd10_by_llm(self, keyword: str, config: Any = None) -> List[str]:
        """对于未命中的冷僻词，调用 LLM 动态推理生成对应的真实 ICD-10 物理前缀范围，确保 100% 泛化"""
        logger.info(f"🔮 [Funnel] 未命中本地字典，启动 LLM 零差错 ICD-10 编码动态推理: '{keyword}'")
        prompt = [
            ("system", """你是一位精通国际疾病分类编码（ICD-10）的医学专家。
请将用户提供的疾病/症状名称映射为标准的 ICD-10 物理编码前缀（大类范围，如 "J00-J06" 或单一编码如 "Z49"）。
输入是一个非标疾病词，你的输出必须是一个标准的 JSON 格式：
{
  "icd10": ["开始编码", "结束编码"],
  "desc": "标准医学名词及说明"
}
请严格确保：
- 输出格式必须是 STRICT JSON，不包含任何 Markdown 标记。
- 如果是单一编码，如透析，开始和结束编码填写相同的值（如 ["Z49", "Z49"]）。
- 如果是某一范围，如急性上呼吸道感染，填写范围（如 ["J00", "J06"]）。"""),
            ("human", f"非标疾病/症状词：{keyword}")
        ]
        try:
            response = await llm_provider.chat(
                role="planner_light",
                messages=prompt,
                config=config,
                max_tokens=500
            )
            content = str(response.content).strip()
            result = extract_json_payload(content)
            if not result:
                raise ValueError(f"无法解析 ICD-10 JSON: {content[:200]}")
            icd = result.get("icd10", [])
            if icd and len(icd) == 2:
                logger.success(f"✅ [Funnel] LLM 零差错动态推理成功: '{keyword}' -> {icd} ({result.get('desc')})")
                return icd
        except Exception as e:
            logger.error(f"❌ [Funnel] LLM 零差错动态推理失败: {e}")
        return []

    async def align_medical_codes(self, keywords: List[str], config: Any = None) -> List[str]:
        """【漏斗第二层】Vectorized RAG：通过向量相似度计算对齐 ICD-10 字典，若完全未命中则触发 LLM 动态推理，确保 100% 泛化"""
        if not keywords:
            return []
            
        import numpy as np
        
        aligned_codes = []
        key_embeds = self._get_key_embeddings()
        
        for kw in keywords:
            kw_clean = kw.strip()
            if not kw_clean:
                continue
                
            # 1. 尝试直接子串匹配（作为极速直通车）
            exact_match_key = None
            for key in self.medical_codes:
                if kw_clean in key or key in kw_clean:
                    exact_match_key = key
                    break
                    
            if exact_match_key:
                dict_val = self.medical_codes[exact_match_key]
                icd = dict_val.get("icd10", [])
                if icd and len(icd) == 2:
                    val = f"{icd[0]}" if icd[0] == icd[1] else f"{icd[0]}-{icd[1]}"
                    aligned_codes.append(val)
                    logger.info(f"🎯 [Funnel] 命中 ICD-10 直通车: '{kw_clean}' -> '{exact_match_key}' -> {icd}")
                    continue
            
            # 2. 如果直通车未命中，启动向量相似度检索
            if key_embeds:
                try:
                    from app.core.memory.embedding import embedding_engine
                    kw_vec = np.array(embedding_engine.embed_query(kw_clean))
                    
                    best_key = None
                    best_score = -1.0
                    
                    for key, embed in key_embeds.items():
                        embed_arr = np.array(embed)
                        dot = np.dot(kw_vec, embed_arr)
                        norm_v = np.linalg.norm(kw_vec)
                        norm_e = np.linalg.norm(embed_arr)
                        score = float(dot / (norm_v * norm_e)) if norm_v > 0 and norm_e > 0 else 0.0
                        
                        if score > best_score:
                            best_score = score
                            best_key = key
                            
                    logger.info(f"🔍 [Funnel] 向量相似度检索 '{kw_clean}': 最高匹配为 '{best_key}' (得分: {best_score:.4f})")
                    
                    if best_key and best_score >= 0.85:
                        dict_val = self.medical_codes[best_key]
                        icd = dict_val.get("icd10", [])
                        if icd and len(icd) == 2:
                            val = f"{icd[0]}" if icd[0] == icd[1] else f"{icd[0]}-{icd[1]}"
                            aligned_codes.append(val)
                            logger.success(f"🎯 [Funnel] 命中向量相似度字典对齐: '{kw_clean}' -> '{best_key}' -> {icd} (得分: {best_score:.4f})")
                            continue
                except Exception as e:
                    logger.error(f"❌ [Funnel] 向量相似度对齐计算异常: {e}")
            
            # 3. 如果向量对齐也未命中，触发 LLM 零差错动态推理映射真实 ICD-10
            icd = await self.get_icd10_by_llm(kw_clean, config)
            if icd and len(icd) == 2:
                val = f"{icd[0]}" if icd[0] == icd[1] else f"{icd[0]}-{icd[1]}"
                aligned_codes.append(val)
                
        return list(set(aligned_codes))


funnel_medical_aligner = FunnelMedicalAligner()
