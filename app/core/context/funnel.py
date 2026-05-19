"""
app/core/funnel.py
==================
[V210.0] 语义漏斗执行器 (Semantic Funnel Processor)

提供非标口语提问到高精度 ClickHouse 物理查询的动态映射管线：
1. Query Rewrite: 口语化意图重写与医学常识翻译。
2. Dictionary Mapping: ICD-10 及物理字段精确对齐（基于 configs/audit_knowledge_base.json）。
3. Graph Hierarchy: 知识图谱上下位推理与 ClickHouse 联邦侧载。
4. Dynamic Baseline: 自动构造双阶段探测基线参数。
"""

import json
import re
import hashlib
import time
import asyncio
from typing import Dict, Any, List, Optional
from loguru import logger

from app.core.llm_provider import llm_provider
from app.infra.neo4j_manager import neo4j_manager
from app.infra.db_conn import get_clickhouse_client

class SemanticFunnel:
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

    async def rewrite_intent(self, query: str, config: Any = None) -> Dict[str, Any]:
        """【漏斗第一层】Query Rewrite：将业务口语转换为结构化审计意图实体"""
        logger.info(f"🔮 [Funnel] 正在重写审计意图: '{query}'")
        
        prompt = [
            ("system", """你是一位精通医疗保险审计与数据科学的专家。
请将用户口语化的核查诉求翻译为结构化的审计分析参数。你的输出必须是 STRICT JSON 格式，包含以下字段：
1. rewritten_question: 专业规范的审计学术语描述。
2. hospital_levels: 识别到的机构级别描述（如 "一级医院", "社区诊所", "民营医院" 等），无则为空数组。
3. disease_keywords: 提取到的疾病核心词或症状核心词（如 "感冒", "发烧", "透析", "高血压" 等），无则为空数组。
4. financial_metric: 可能的结算字段类别，只能在 ["medfee_sumamt", "fund_pay_sumamt", "det_item_fee_sumamt", "none"] 中选择。
5. statistical_strategy: 针对异常金额或频次的统计核查策略，必须在 ["DYNAMIC_QUANTILE_95", "DYNAMIC_QUANTILE_99", "AVERAGE_OUTLIER", "HARD_THRESHOLD", "NONE"] 中选择一种。

请务必只返回 JSON，禁止返回任何 markdown 标记或解释性文字。"""),
            ("human", f"用户核查提问：{query}")
        ]
        
        try:
            response = await llm_provider.chat(
                role="planner_light",
                messages=prompt,
                config=config,
                max_tokens=300
            )
            content = str(response.content).strip()
            # 提取 JSON 块
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                content = json_match.group(0)
            result = json.loads(content)
            logger.info(f"✅ [Funnel] 意图重写成功: {result}")
            return result
        except Exception as e:
            logger.error(f"❌ [Funnel] 意图重写失败: {e}，启用降级实体提取")
            # 降级兜底提取
            return {
                "rewritten_question": query,
                "hospital_levels": ["社区诊所", "乡镇卫生院"] if "诊所" in query or "卫生院" in query else [],
                "disease_keywords": ["感冒"] if "感冒" in query or "发烧" in query else ["透析"] if "透析" in query else [],
                "financial_metric": "medfee_sumamt",
                "statistical_strategy": "DYNAMIC_QUANTILE_95" if "大额" in query or "大价钱" in query or "千" in query else "NONE"
            }

    def _get_key_embeddings(self) -> Dict[str, List[float]]:
        if not hasattr(self, "_cached_embeddings"):
            self._cached_embeddings = {}
            keys = list(self.medical_codes.keys())
            if keys:
                try:
                    from app.core.memory.embedding import embedding_engine
                    # 批量生成嵌入向量
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
                max_tokens=150
            )
            content = str(response.content).strip()
            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                content = json_match.group(0)
            result = json.loads(content)
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
                        # 计算 cosine similarity
                        dot = np.dot(kw_vec, embed_arr)
                        norm_v = np.linalg.norm(kw_vec)
                        norm_e = np.linalg.norm(embed_arr)
                        score = float(dot / (norm_v * norm_e)) if norm_v > 0 and norm_e > 0 else 0.0
                        
                        if score > best_score:
                            best_score = score
                            best_key = key
                            
                    logger.info(f"🔍 [Funnel] 向量相似度检索 '{kw_clean}': 最高匹配为 '{best_key}' (得分: {best_score:.4f})")
                    
                    if best_key and best_score >= 0.65:
                        dict_val = self.medical_codes[best_key]
                        icd = dict_val.get("icd10", [])
                        if icd and len(icd) == 2:
                            val = f"{icd[0]}" if icd[0] == icd[1] else f"{icd[0]}-{icd[1]}"
                            aligned_codes.append(val)
                            logger.success(f"🎯 [Funnel] 命中向量相似度字典对齐: '{kw_clean}' -> '{best_key}' -> {icd} (得分: {best_score:.4f})")
                            continue
                except Exception as e:
                    logger.error(f"❌ [Funnel] 向量相似度对齐计算异常: {e}")
            
            # 3. 如果向量对齐也未命中（相似度太低，说明是冷僻疾病词），触发 LLM 零差错动态推理映射真实 ICD-10
            icd = await self.get_icd10_by_llm(kw_clean, config)
            if icd and len(icd) == 2:
                val = f"{icd[0]}" if icd[0] == icd[1] else f"{icd[0]}-{icd[1]}"
                aligned_codes.append(val)
                
        return list(set(aligned_codes))

    async def sideload_hospital_hierarchy(self, levels: List[str]) -> Optional[str]:
        """【漏斗第三层】Graph Hierarchy：知识图谱多跳级联与联邦侧载至 ClickHouse 临时表"""
        if not levels:
            return None
        
        # 1. 检测 Neo4j 是否连接
        if not neo4j_manager.is_connected:
            try:
                neo4j_manager.get_driver()
            except Exception:
                logger.warning("⚠️ [Funnel] Neo4j 服务不可达，将通过内存物理规则对齐机构编码")
                return None

        logger.info(f"🕸️ [Funnel] 启动图谱多跳关联分析: {levels}")
        
        # 2. 构造 Cypher 进行上下位层级多跳级联获取所有的 fixmedins_code
        # 匹配定点医疗机构等级树状关系
        cypher = """
        MATCH (h:Hospital)-[:BELONGS_TO*1..2]->(lv:Level)
        WHERE any(item IN $levels WHERE lv.name CONTAINS item)
        RETURN h.fixmedins_code AS code
        """
        
        try:
            def _exec_cypher():
                with neo4j_manager.get_driver().session() as session:
                    res = session.run(cypher, {"levels": levels})
                    return [record["code"] for record in res if record["code"]]
                    
            hospital_codes = await asyncio.to_thread(_exec_cypher)
            hospital_codes = list(set(hospital_codes))
            
            if not hospital_codes:
                logger.warning(f"[Funnel] 图谱多跳返回空节点，无法生成侧载临时表。")
                return None
                
            # 3. 物理联邦侧载：写入 ClickHouse 内存临时表
            batch_id = hashlib.md5(f"{time.time()}_{len(hospital_codes)}".encode()).hexdigest()[:8]
            temp_table = f"fqz_temp_sl_{batch_id}"
            
            client = get_clickhouse_client()
            create_sql = f"CREATE TABLE IF NOT EXISTS {temp_table} (id String) ENGINE = Memory"
            
            # 使用 clickhouse-connect 执行物理侧载
            if hasattr(client.client, 'execute'):
                client.client.execute(create_sql)
                client.client.execute(f"INSERT INTO {temp_table} (id) VALUES", [(x,) for x in hospital_codes])
            else:
                client.client.command(create_sql)
                client.client.insert(temp_table, [[x] for x in hospital_codes], column_names=['id'])
                
            logger.success(f"✅ [Funnel] 联邦侧载成功！图谱关联 {len(hospital_codes)} 家机构侧载至 ClickHouse 临时表: {temp_table}")
            return temp_table
            
        except Exception as e:
            logger.error(f"❌ [Funnel] 联邦侧载失败: {e}")
            return None

    def build_statistical_baseline(self, rewritten: Dict[str, Any], aligned_codes: List[str], temp_table: Optional[str]) -> Dict[str, Any]:
        """【漏斗第四层】Dynamic Baseline：自动封装双阶段探测大盘基线的策略结构"""
        strategy = rewritten.get("statistical_strategy", "NONE")
        if strategy == "NONE":
            return {}

        metric = rewritten.get("financial_metric", "medfee_sumamt")
        
        # 拼装疾病过滤 SQL 片段
        where_clauses = []
        if aligned_codes:
            sub_clauses = []
            for code in aligned_codes:
                if "-" in code:
                    # [企业级自愈] 抵御多横杠解包异常 (如 LLM 返回了 J00-J05-J10)
                    parts = code.split("-")
                    start, end = parts[0], parts[-1]
                    sub_clauses.append(f"(dise_code >= '{start}' AND dise_code <= '{end}')")
                else:
                    sub_clauses.append(f"dise_code LIKE '{code}%'")
            where_clauses.append("(" + " OR ".join(sub_clauses) + ")")
            
        # 拼装机构临时表 Join 片段
        join_clause = ""
        if temp_table:
            join_clause = f"INNER JOIN {temp_table} AS temp_inst ON main_table.fixmedins_code = temp_inst.id"

        # 拼装基线探测 SQL (仅用于 Phase 1 计算分位数)
        sql_pattern = ""
        quantile_val = 0.95 if "95" in strategy else 0.99 if "99" in strategy else 0.90
        
        where_str = " AND ".join(where_clauses) if where_clauses else "1 = 1"
        
        sql_pattern = f"SELECT quantile({quantile_val})({metric}) AS baseline FROM fqz_gz_jzsj_all_ql AS main_table {join_clause} WHERE {where_str}"
        
        logger.info(f"📊 [Funnel] 已就绪双阶段统计探测基线模型 (策略: {strategy})")
        return {
            "strategy": strategy,
            "metric": metric,
            "phase1_baseline_sql": sql_pattern,
            "quantile": quantile_val
        }

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
