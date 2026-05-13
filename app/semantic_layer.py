import os
import re
import faiss
from loguru import logger

# [重构 V90.0] 原文件存在两个重复的 SemanticRetriever 类定义，第二个会覆盖第一个。
# 导致 extract_metadata 方法丢失。现在合并 _MetadataExtractor 作为辅助基类,
# SemanticRetriever 为唯一对外入口。
class _MetadataExtractor:
    """从百科文档中提取字段语义元数据的辅助类。"""

    def __init__(self, schema_file="e:/chain/hsa-agent/docs/medical_audit_encyclopedia.md"):
        self.schema_file = schema_file
        self.model_name = "BAAI/bge-small-zh-v1.5"

    def extract_metadata(self):
        """解析 v3.0 百科文档，提取全域 32 表分区业务含义"""
        CORE_SEMANTIC_SEEDS = [
            {"table": "v_audit_hospital_monthly", "column": "total_amount", "desc": "医院报销排行榜，医疗机构总金额排名，费用趋势, 医院月度统计, 大盘数据"},
            {"table": "v_audit_patient_annual", "column": "annual_amount", "desc": "个人年度总费用，患者年度风险画像，高频就医, 跨院套现识别, 年度行为分析"},
            {"table": "fqz_all_yy_yd_1", "column": "setl_time", "desc": "结算时间, 入院时间, 就医结算日期, 年度统计, 跨年分析, 近几年"},
            {"table": "fqz_all_yy_yd_1", "column": "medfee_sumamt", "desc": "医疗总金额，结算金额, 费用总额, 统筹支付底盘, 高风险大额监控"},
            {"table": "fqz_all_yy_yd_1", "column": "hifp_pay", "desc": "统筹基金支付, 医保报销金额, 审计骗保监控对象, 核心违规金额"},
            {"table": "fqz_all_yy_yd_1", "column": "vix", "desc": "变异指数, 离散系数, 异常增长风险标识, 高风险指标, 离群点识别"},
            {"table": "fqz_all_yy_yd_1", "column": "psn_no", "desc": "个人编号, 患者 ID, 参保人标识, 人员轨迹分析"},
            {"table": "fqz_all_yy_yd_1", "column": "ipt_days", "desc": "住院天数, 入院时长, 分解住院风险"}
        ]
        
        extracted_data = []
        for seed in CORE_SEMANTIC_SEEDS:
            full_text = f"表 {seed['table']} 的字段 {seed['column']} 核心含义是 {seed['desc']}"
            extracted_data.append({**seed, "type": "Core", "full_text": full_text})

        if not os.path.exists(self.schema_file):
            logger.error(f"百科字典文件缺失: {self.schema_file}")
            return extracted_data

        with open(self.schema_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 逻辑：按 Domain (📂) 进行初步物理划分，然后按子标题 (###) 拆分表
        domain_blocks = re.split(r'## 📂 ', content)[1:]
        
        for dom_block in domain_blocks:
            domain_name_match = re.search(r'^(.*?)\n', dom_block)
            domain_name = domain_name_match.group(1).strip() if domain_name_match else "未知域"
            
            # 拆分表块
            table_blocks = re.split(r'### ', dom_block)[1:]
            for block in table_blocks:
                # 物理提取：支持 "### 2. fqz_gz_jzsj_all_ql - 原始就诊全库" 格式
                title_line = block.split('\n')[0]
                table_match = re.search(r'(fqz_[^\s-]+)', title_line)
                if not table_match:
                    continue
                table_name = table_match.group(1)
                table_desc = title_line.replace(table_name, "").strip(" .-\t")
                
                # 提取表元数据 (Summary)
                summary_match = re.search(r'【业务价值】：(.*?)\n', block)
                table_summary = summary_match.group(1) if summary_match else table_desc

                # --- [物理补强 A]：解析 Markdown 表格格式 ---
                rows = re.findall(r'\|\s*`?([^`\|]+?)`?\s*\|\s*([^\|]+?)\s*\|\s*([^\|]+?)\s*\|\s*([^\|]*?)\s*\|', block)
                if not rows:
                    rows = re.findall(r'\|\s*`?([^`\|]+?)`?\s*\|\s*([^\|]+?)\s*\|\s*([^\|]*?)\s*\|', block)

                for r in rows:
                    col = r[0].strip()
                    if col in ["物理字段", "字段名", ":---"]:
                        continue
                    # 适应 V3.0 百科结构：| 字段 | 含义 | 类型 | 审计意义 |
                    desc = r[1].strip() if len(r) > 1 else "业务字段"
                    dtype = r[2].strip() if len(r) > 2 else "String"
                    meaning = r[3].strip() if len(r) > 3 else ""
                    extracted_data.append(self._make_semantic_item(domain_name, table_name, table_summary, col, desc, meaning, dtype))

                # --- [物理补强 B]：解析无序列表格式 (针对全量流水表 Domain A) ---
                # 寻找格式如 - **`field`**: desc
                bullet_matches = re.findall(r'-\s*\*\*`?([^`\s\*]+)`?\*\*[:：]\s*(.*?)\n', block)
                for col, desc in bullet_matches:
                    extracted_data.append(self._make_semantic_item(domain_name, table_name, table_summary, col, desc, "列表定义"))

        # --- [物理补强 C]：全局通用字典注入 (针对 Domain B) ---
        # 扫描文档中名为 "Common Metrics" 或 "通用业务指标字典" 的区域
        common_metrics_match = re.search(r'## 🏛️ 通用业务指标字典 (.*?)\n(.*?)\n##', content, re.DOTALL)
        if common_metrics_match:
            common_text = common_metrics_match.group(2)
            metrics = re.findall(r'-\s*\*\*`?([^`\s\*]+)`?\*\*[:：]\s*(.*?)\n', common_text)
            # 将这些通用指标物理广播到 Domain B (CGZHAN) 的所有关联表中
            b_tables = {item["table"] for item in extracted_data if item.get("domain") == "CGZHAN - Production Stats"}
            for t_name in b_tables:
                for col, desc in metrics:
                    extracted_data.append(self._make_semantic_item("General", t_name, "通用统计维度", col, desc, "继承自全局字典"))

        self.column_metadata = extracted_data
        logger.info(f"✅ 百科语义捕获完成: 共激活 {len(extracted_data)} 个审计知识锚点。")
        return extracted_data

    def _make_semantic_item(self, domain, table, summary, col, desc, meaning, dtype="String"):
        full_text = f"[{domain}] 表 {table} ({summary}) 的字段 {col} (类型: {dtype}) 含义是 {desc}。审计价值 {meaning}"
        return {
            "domain": domain,
            "table": table,
            "column": col,
            "type": dtype,
            "desc": f"{desc} {meaning}",
            "full_text": full_text
        }

class MetadataMappingLayer:
    """[V110.0] 企业级“语义—物理”映射层：解决业务术语混淆及字段幻觉"""
    def __init__(self, kb_path="configs/audit_knowledge_base.json"):
        self.kb_path = kb_path
        self.ontology = self._load_ontology()

    def _load_ontology(self) -> dict:
        """[企业级] 从外部知识库动态加载审计本体与红线"""
        try:
            import json
            if os.path.exists(self.kb_path):
                with open(self.kb_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("ontology", {})
        except Exception as e:
            logger.error(f"加载审计知识库失败: {e}")
        
        # 兜底硬编码（仅防灾）
        return {"职工医保": {"physical": "insutype='310'"}}

    def detect(self, text: str) -> str:
        """识别关键词并返回避坑指南"""
        guides = []
        for term, meta in self.ontology.items():
            if term in text:
                guides.append(f"### 💡 {term} 业务避坑指南\n- **物理映射建议**: {meta['physical']}\n- **风险提示**: {meta['caveats']}")
        return "\n\n".join(guides)

# [V66.2] 物理常驻：模块级嵌入模型单例，消除重复加载开销
_GLOBAL_EMBEDDING_MODEL = None

def get_embedding_model():
    global _GLOBAL_EMBEDDING_MODEL
    if _GLOBAL_EMBEDDING_MODEL is None:
        from sentence_transformers import SentenceTransformer
        os.environ["HF_ENDPOINT"] = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")
        logger.info(f">>> [语义层] 镜像链路已激活 (HF_ENDPOINT={os.environ['HF_ENDPOINT']})")
        logger.info(">>> [语义层] 正在从初始化文件加载嵌入模型...")
        _GLOBAL_EMBEDDING_MODEL = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
    return _GLOBAL_EMBEDDING_MODEL

class SemanticRetriever(_MetadataExtractor):
    def __init__(self, data_dir="data/semantic_index",
                 schema_file="e:/chain/hsa-agent/docs/medical_audit_encyclopedia.md"):
        super().__init__(schema_file=schema_file)
        self.data_dir = data_dir
        self.index = None
        self.column_metadata = []
        os.makedirs(self.data_dir, exist_ok=True)
        
    def _get_model(self):
        """调用模块级单例模型"""
        return get_embedding_model()

    def build_index(self):
        """构建向量索引容器并持久化"""
        import faiss
        import numpy as np
        import pickle
        
        index_path = os.path.join(self.data_dir, "vector.index")
        meta_path = os.path.join(self.data_dir, "metadata.pkl")

        # [V66.1] 物理提速：优先从磁盘加载缓存索引
        if os.path.exists(index_path) and os.path.exists(meta_path):
            try:
                self.index = faiss.read_index(index_path)
                with open(meta_path, 'rb') as f:
                    self.column_metadata = pickle.load(f)
                logger.info(f"✅ [语义层] 已从磁盘加载缓存索引 (字段数 {len(self.column_metadata)})")
                return
            except Exception as e:
                logger.warning(f"加载缓存索引失败: {e}，正在重新构建...")

        # 1. 提取元数据
        if not self.column_metadata:
            self.extract_metadata()
        
        # 2. 准备向量
        texts = [item["full_text"] for item in self.column_metadata]
        logger.info(f">>> [语义层] 正在对 {len(texts)} 个字段进行向量编码...")
        embeddings = self._get_model().encode(texts, show_progress_bar=True)
        
        # 3. 建立 FAISS 索引
        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatIP(dimension) 
        faiss.normalize_L2(embeddings) 
        self.index.add(embeddings.astype('float32'))
        
        # 4. 持久化到磁盘
        try:
            faiss.write_index(self.index, index_path)
            with open(meta_path, 'wb') as f:
                pickle.dump(self.column_metadata, f)
            logger.info("✅ [语义层] 索引已成功持久化至磁盘")
        except Exception as e:
            logger.error(f"持久化索引失败: {e}")
        
        logger.success(f"✅ 语义索引构建成功 | 维度: {dimension}")

    def get_relevant_columns(self, queries: list, k=10):
        """执行语义搜索，增加关键词旁路加速"""
        if not queries: return []
        
        query_text = " ".join(queries)
        
        # [V66.5] 极速旁路 (Bypass)：针对高频关键词直接返回核心维度，跳过 Embedding 加载
        FAST_KEYWORDS = {
            "医院": ["org_name", "org_id"],
            "费用": ["medfee_sumamt", "fund_pay_sumamt"],
            "天数": ["ipt_days", "stay_days"],
            "排名": ["org_name", "medfee_sumamt"],
            "年度": ["year", "setl_time"]
        }
        
        bypass_results = []
        if any(kw in query_text for kw in FAST_KEYWORDS):
            logger.info(">>> [⚡ HYPER-FAST] 检测到高频关键词，正在旁路向量检索以节省 15s 启动耗时...")
            # 快速构造一些核心元数据
            for kw, cols in FAST_KEYWORDS.items():
                if kw in query_text:
                    for c in cols:
                        # 从已加载的 metadata 中找
                        item = next((m for m in self.column_metadata if m["column"] == c), None)
                        if item: bypass_results.append(item)
            
            if bypass_results:
                return bypass_results[:k]

        # 如果没中旁路，再走向向量检索
        if self.index is None:
            self.build_index()
            
        combined_query = query_text
        logger.info(f">>> [语义层] 执行向量检索 '{combined_query[:50]}...'")
        
        # 1. 编码查询
        query_embedding = self._get_model().encode([combined_query])
        faiss.normalize_L2(query_embedding)
        
        # 2. 检索
        distances, indices = self.index.search(query_embedding.astype('float32'), k)
        
        # 3. 返回结果
        results = []
        for idx in indices[0]:
            if idx < len(self.column_metadata):
                results.append(self.column_metadata[idx])
        
        return results

    def get_avoidance_guides(self, query_text: str) -> str:
        """[V110.0] 获取避坑指南注入文本"""
        mapper = MetadataMappingLayer()
        return mapper.detect(query_text)

    def format_for_prompt(self, items):
        """将检索结果格式化为带有防御性 Cast 建议的 Prompt 注入文本"""
        if not items:
            return "暂未检索到相关物理字段。"
        
        lines = ["| 表名 | 字段名 | 物理类型 | 语义/审计价值 | 核心编写建议 |", "| :--- | :--- | :--- | :--- | :--- |"]
        for it in items:
            dtype = it.get("type", "String")
            suggestion = "直接使用"
            
            # --- 企业级防御性 Cast 逻辑生成 ---
            if "String" in dtype:
                if any(x in it["column"].lower() for x in ["amt", "fee", "pay", "days", "count", "age"]):
                    suggestion = f"String 数值，必须使用 toInt32OrZero({it['column']}) 或 toFloat64OrZero()"
                elif "date" in it["column"].lower() or "time" in it["column"].lower():
                    suggestion = f"String 日期，必须使用 toDate({it['column']}) 或 toDateTime()"
            
            lines.append(f"| {it['table']} | {it['column']} | {dtype} | {it['desc']} | {suggestion} |")
        
        return "\n".join(lines)

if __name__ == "__main__":
    # 局部验证
    retriever = SemanticRetriever()
    results = retriever.get_relevant_columns(["入院时间", "结算金额", "患者编号"])
    print("\n--- 检索到的物理主权字典 ---")
    print(retriever.format_for_prompt(results))
