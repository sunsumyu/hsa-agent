"""
app/core/context/funnel.py
==========================
[V210.0 / Matt Pocock Deep Module] 语义漏斗执行器门面 (Semantic Funnel Facade)

提供非标口语提问到高精度 ClickHouse 物理查询的动态映射管线：
1. Query Rewrite: 口语化意图重写与医学常识翻译 -> funnel_intent_rewriter
2. Dictionary Mapping: ICD-10 及物理字段精确对齐 -> funnel_medical_aligner
3. Graph Hierarchy: 知识图谱上下位推理与 ClickHouse 联邦侧载 -> funnel_hierarchy_sideload
4. Dynamic Baseline: 自动构造双阶段探测基线参数 -> funnel_baseline_builder
"""

from typing import Dict, Any, List, Optional
from loguru import logger

from app.core.context.funnel_intent_rewriter import funnel_intent_rewriter, extract_json_payload
from app.core.context.funnel_medical_aligner import funnel_medical_aligner, FunnelMedicalAligner
from app.core.context.funnel_hierarchy_sideload import sideload_hospital_hierarchy
from app.core.context.funnel_baseline_builder import build_statistical_baseline


class SemanticFunnel:
    """语义漏斗高内聚纯门面"""

    def __init__(self, kb_path: str = "configs/audit_knowledge_base.json"):
        self.medical_aligner = FunnelMedicalAligner(kb_path=kb_path)
        self.intent_rewriter = funnel_intent_rewriter

    @property
    def medical_codes(self):
        return self.medical_aligner.medical_codes

    @property
    def ontology(self):
        return self.medical_aligner.ontology

    def _extract_json_payload(self, text: str) -> Optional[Dict[str, Any]]:
        """向后兼容提取方法"""
        return extract_json_payload(text)

    async def rewrite_intent(self, query: str, config: Any = None) -> Dict[str, Any]:
        """【漏斗第一层】Query Rewrite：将业务口语转换为结构化审计意图实体"""
        return await self.intent_rewriter.rewrite_intent(query, config)

    async def get_icd10_by_llm(self, keyword: str, config: Any = None) -> List[str]:
        """动态推理生成 ICD-10 物理前缀范围"""
        return await self.medical_aligner.get_icd10_by_llm(keyword, config)

    async def align_medical_codes(self, keywords: List[str], config: Any = None) -> List[str]:
        """【漏斗第二层】Vectorized RAG：通过向量相似度计算对齐 ICD-10 字典"""
        return await self.medical_aligner.align_medical_codes(keywords, config)

    async def sideload_hospital_hierarchy(self, levels: List[str]) -> Optional[str]:
        """【漏斗第三层】Graph Hierarchy：知识图谱多跳级联与联邦侧载至 ClickHouse 临时表"""
        return await sideload_hospital_hierarchy(levels)

    def build_statistical_baseline(
        self,
        rewritten: Dict[str, Any],
        aligned_codes: List[str],
        temp_table: Optional[str]
    ) -> Dict[str, Any]:
        """【漏斗第四层】Dynamic Baseline：自动封装双阶段探测大盘基线的策略结构"""
        return build_statistical_baseline(rewritten, aligned_codes, temp_table)

    async def execute_alignment_flow(self, query: str, config: Any = None) -> Dict[str, Any]:
        """一键穿透四层语义漏斗，完成物理映射对齐流程"""
        # 1. 意图重写
        rewritten = await self.rewrite_intent(query, config)
        
        # 2. 物理字典 ICD 映射
        aligned_codes = await self.align_medical_codes(rewritten.get("disease_keywords", []), config)
        
        # 3. 图谱上下位推理与 ClickHouse 联邦侧载
        temp_table = await self.sideload_hospital_hierarchy(rewritten.get("hospital_levels", []))
        
        # 4. 双阶段统计基线封装
        baseline_meta = self.build_statistical_baseline(rewritten, aligned_codes, temp_table)
        
        alignment_report = {
            "query": query,
            "rewritten_question": rewritten.get("rewritten_question", query),
            "hospital_levels": rewritten.get("hospital_levels", []),
            "disease_keywords": rewritten.get("disease_keywords", []),
            "aligned_codes": aligned_codes,
            "temp_table": temp_table,
            "baseline_meta": baseline_meta,
            "explanation": f"【前置语义漏斗白盒映射】：已将口语化提问重写为专业术语；将业务疾病词召回为 ICD-10 对齐范围 {aligned_codes}；"
                           f"通过图谱多跳侧载了符合“{rewritten.get('hospital_levels', [])}”的基层机构临时表 {temp_table or '（图谱未连接，降级模糊匹配）'}；"
                           f"已就绪基线探测策略：{baseline_meta.get('strategy', 'NONE')}。"
        }
        
        logger.success("🔮 [Funnel] 语义漏斗白盒对齐执行流全装配完毕。")
        return alignment_report


# 单例导出
semantic_funnel = SemanticFunnel()
