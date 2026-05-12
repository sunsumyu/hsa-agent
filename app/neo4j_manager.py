"""
[V59.3 Phase 3-B] Neo4j 图数据库连接管理 + 字段知识图谱层

新增：FieldKnowledgeGraph
    - 将字段别名关系（hosp_code → fixmedins_code）和禁用关系
      存入图结构，实现确定性字段映射（取代概率性 FAISS 相似度）
    - 当 Neo4j 未连接时，自动回退到内存图谱
    - 对外提供统一接口，schema_injector 优先查图
"""
import os
import re
from loguru import logger
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()


# ──────────────────────────────────────────────────────────────
# 字段知识图谱：确定性别名注册表（不依赖 Neo4j 服务）
# ──────────────────────────────────────────────────────────────

FIELD_ALIAS_REGISTRY: List[Dict] = [
    {
        "canonical": "fixmedins_code",
        "aliases": ["医疗机构编码", "机构代码", "hospital_id", "hosp_id", "inst_code"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "医疗机构唯一编码（必须使用此字段，严禁使用 hosp_code）",
        "forbidden_aliases": ["hosp_code"]
    },
    {
        "canonical": "fixmedins_name",
        "aliases": ["医院名称", "机构名称", "hosp_name", "hospital_name", "provider_name", "med_inst_name"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "医疗机构名称",
        "forbidden_aliases": ["hosp_name"]
    },
    {
        "canonical": "psn_no",
        "aliases": ["patient_id", "person_id", "psn_id", "insured_no", "psn_no", "patient_no"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "参保人唯一标识",
        "forbidden_aliases": []
    },
    {
        "canonical": "gend",
        "aliases": ["性别代码"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "性别代码：1=男，2=女",
        "forbidden_aliases": ["gender", "sex"]
    },
    {
        "canonical": "dise_name",
        "aliases": ["diagnosis", "disease_name", "diag_name", "diagnosis_code", "diag_code", "dise_code"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "主要诊断名称",
        "forbidden_aliases": ["diagnosis", "disease_name"]
    },
    {
        "canonical": "start_date",
        "aliases": ["adm_date", "admit_date", "in_date", "admission_date", "start_time"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "住院开始日期",
        "forbidden_aliases": ["adm_date", "admit_date"]
    },
    {
        "canonical": "end_date",
        "aliases": ["dis_date", "discharge_date", "out_date", "finish_date"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "住院结束日期",
        "forbidden_aliases": ["dis_date", "discharge_date"]
    },
    {
        "canonical": "medfee_sumamt",
        "aliases": ["医疗总费用", "结算金额", "total_fee", "total_amount", "medfee", "total_expense", "total_bill", "gross_amount", "medical_cost", "fee_amt", "pay_amount", "fee_amount"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "医疗总费用（必须使用此字段，严禁使用 total_fee 或 amount 或 fee_amt）",
        "forbidden_aliases": ["total_fee", "total_amount", "amount", "fee_amt", "pay_amount"]
    },
    {
        "canonical": "fund_pay_sumamt",
        "aliases": ["insurance_pay", "medical_pay", "fund_pay", "reimbursement_amount", "fund_amt", "reimbursement", "benefit_amount", "covered_amount"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "医保基金实际支付金额",
        "forbidden_aliases": ["insurance_pay", "medical_pay"]
    },
    {
        "canonical": "setl_time",
        "aliases": ["settle_time", "settlement_date", "setl_time"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "医疗费用结算时间",
        "forbidden_aliases": ["settle_time"]
    },
    {
        "canonical": "setl_id",
        "aliases": ["settlement_id", "settle_id", "bill_id", "record_id", "admission_id"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "结算流水唯一标识",
        "forbidden_aliases": ["settlement_id"]
    },
    {
        "canonical": "med_type",
        "aliases": ["medical_type", "visit_type", "med_type", "medical_category", "treatment_type", "admission_type", "visit_category", "treat_type"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "就医类型（门诊/住院/药店）",
        "forbidden_aliases": ["medical_type", "medical_category"]
    },
    {
        "canonical": "hilist_name",
        "aliases": ["item_name", "drug_name", "treat_name", "project_name", "fee_name", "hilist_name", "det_item_name"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "费用明细项目名称（药品/诊疗/耗材）",
        "forbidden_aliases": ["drug_name", "treat_name", "item_name", "det_item_name"]
    },
    {
        "canonical": "hilist_code",
        "aliases": ["item_code", "drug_code", "treat_code", "list_code", "hilist_code", "service_code", "project_code", "fee_code", "item_id"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "医保标准项目编码",
        "forbidden_aliases": ["drug_code", "item_code"]
    },
    {
        "canonical": "det_item_fee_sumamt",
        "aliases": ["item_fee", "detail_amount", "item_amount", "det_item_fee_sumamt"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "明细项目总金额",
        "forbidden_aliases": ["item_fee", "item_amount"]
    },
    {
        "canonical": "tel",
        "aliases": ["手机号", "电话", "联系方式", "mobile", "phone", "tel"],
        "table": "fqz_gz_jzsj_all_ql",
        "desc": "参保人联系电话（提示：结算明细表中该字段可能为空，建议优先调用 query_fraud_ring 查图）",
        "forbidden_aliases": []
    },
    # ── 虚拟计算指标：物理不存在，需告知 LLM 如何计算 ──
    {
        "canonical": "__COMPUTED__",
        "aliases": [],
        "table": "__VIRTUAL__",
        "desc": "以下字段是常见幻觉字段，物理不存在，必须通过 SQL 公式计算",
        "forbidden_aliases": [
            "vix", "variation_index", "变异指数",
            "overlap_hours", "overlap_days",
            "department_id", "dept_id", "dept_code",
            "visit_count", "admission_count",
            "age", "patient_age",
            "readmission_flag", "is_readmission",
            "los", "length_of_stay",
        ]
    },
]

# 构建快速查找索引（别名 → 正规字段名）
_ALIAS_TO_CANONICAL: Dict[str, str] = {}
_FORBIDDEN_SET: set = set()

for _entry in FIELD_ALIAS_REGISTRY:
    _canonical = _entry["canonical"].strip()
    for _alias in _entry.get("aliases", []):
        _ALIAS_TO_CANONICAL[_alias.strip().lower()] = _canonical
    for _forbidden in _entry.get("forbidden_aliases", []):
        _FORBIDDEN_SET.add(_forbidden.strip().lower())


class FieldKnowledgeGraph:
    """
    [Phase 3-B] 确定性字段知识图谱。

    用图结构存储字段别名关系和禁用关系，
    为 schema_injector 和 SQLGuardian 提供确定性字段名验证和纠错能力。

    完全不依赖 Neo4j 服务（有则用图DB，无则用内存注册表）。
    提供与 FAISS 语义检索完全不同的确定性查询路径。
    """

    def __init__(self):
        self._registry = FIELD_ALIAS_REGISTRY
        self._alias_map = _ALIAS_TO_CANONICAL
        self._forbidden = _FORBIDDEN_SET
        logger.info(
            f"[FieldKnowledgeGraph] 已激活，注册 {len(self._registry)} 个字段映射，"
            f"{len(self._forbidden)} 个禁用别名"
        )

    def resolve(self, field_name: str) -> Optional[str]:
        """
        将一个字段名（可能是别名）解析为正规字段名。

        Returns:
            正规字段名（如 'fixmedins_code'），或 None（未知字段）
        """
        fn = field_name.lower().strip()
        if fn in self._alias_map:
            canonical = self._alias_map[fn]
            logger.debug(f"[FieldKG] 别名解析: {field_name} -> {canonical}")
            return canonical
        for entry in self._registry:
            if entry["canonical"].lower() == fn:
                return entry["canonical"]
        return None

    def is_forbidden(self, field_name: str) -> bool:
        """判断一个字段名是否是已知的错误/不存在字段"""
        return field_name.lower().strip() in self._forbidden

    def sanitize_sql(self, sql: str):
        """
        [V119.1] 工业级纠错：扫描 SQL 中的禁用字段名并替换，但【严格保护别名】。
        """
        warnings = []
        fixed = sql

        def _safe_replace(target_sql, forbidden_word, canonical_word):
            # 使用正则捕获组：(AS 关键字)? + (目标词)
            # 我们通过 lambda 逻辑，如果前面是 AS，则原样返回，不替换
            pattern = r'(\bAS\s+)?\b' + re.escape(forbidden_word) + r'\b'
            
            def _sub_func(match):
                if match.group(1): # 命中了 AS 别名定义
                    return match.group(0) # 原样返回，不纠错
                return canonical_word
            
            new_sql = re.sub(pattern, _sub_func, target_sql, flags=re.IGNORECASE)
            return new_sql

        # 第一阶段：纠错禁用别名
        for forbidden in self._forbidden:
            if re.search(r'\b' + re.escape(forbidden) + r'\b', fixed, re.IGNORECASE):
                canonical = self._alias_map.get(forbidden)
                if canonical:
                    new_fixed = _safe_replace(fixed, forbidden, canonical)
                    if new_fixed != fixed:
                        fixed = new_fixed
                        msg = f"[FieldKG] 自动纠错: {forbidden} -> {canonical}"
                        warnings.append(msg)
                        logger.warning(msg)

        # 第二阶段：对齐普通别名 (同样保护 AS)
        for alias, canonical in self._alias_map.items():
            if alias in self._forbidden: continue
            fixed = _safe_replace(fixed, alias, canonical)
                    
        return fixed, warnings

    def get_canonical_fields(self, table: Optional[str] = None) -> List[Dict]:
        """返回正规字段列表，可按表过滤"""
        if table:
            return [e for e in self._registry if e.get("table") == table]
        return list(self._registry)

    def format_for_prompt(self, table: Optional[str] = None, max_fields: int = 8) -> str:
        """
        生成用于 Prompt 注入的字段清单（确定性版本）。
        格式与 schema_injector.inject() 兼容，优先级更高。
        """
        entries = self.get_canonical_fields(table)[:max_fields]
        lines = ["**[字段知识图谱] 以下为推荐的物理映射参考。若任务涉及手机号、亲属关系、聚集性分析，请务必优先尝试调用 query_fraud_ring (图查询)：**\n"]
        for e in entries:
            forbidden_hint = ""
            if e.get("forbidden_aliases"):
                forbidden_hint = f"（禁用: {', '.join(e['forbidden_aliases'][:2])}）"
            lines.append(
                f"- `{e['canonical']}` [{e['table']}]: {e['desc']}{forbidden_hint}"
            )
        return "\n".join(lines)


# ──────────────────────────────────────────────────────────────
# 原有 Neo4j 连接管理（保持不变）
# ──────────────────────────────────────────────────────────────

class Neo4jManager:
    def __init__(self):
        self.uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        self.user = os.getenv("NEO4J_USER", "neo4j")
        self.password = os.getenv("NEO4J_PASSWORD", "")
        if not self.password:
            logger.warning("[SECURITY] NEO4J_PASSWORD 未设置，Neo4j 连接将失败。请在 .env 中配置。")
        self.driver = None
        self.is_connected = False
        # [V59.3] 延迟加载：不在初始化时物理阻塞，仅在首次使用时建立连接
        # self._init_connection() 

    def _init_connection(self):
        try:
            from neo4j import GraphDatabase
            # [V117.0] 物理协议自愈：针对本地/WSL 环境，bolt:// 比 neo4j:// 更具鲁棒性
            connection_uri = self.uri
            if "localhost" in connection_uri or "127.0.0.1" in connection_uri:
                if connection_uri.startswith("neo4j://"):
                    logger.warning("[NEO4J] 检测到本地环境使用 neo4j:// 协议，可能导致路由失败。正在尝试降级为 bolt://...")
                    connection_uri = connection_uri.replace("neo4j://", "bolt://")

            self.driver = GraphDatabase.driver(
                connection_uri, 
                auth=(self.user, self.password),
                connection_timeout=60.0  # [V117.0] 增加超时容忍度
            )
            self.driver.verify_connectivity()
            self.is_connected = True
            logger.info(f">>> 成功直连至 Neo4j 图数据库 ({connection_uri.split('://')[0]} 模式)。")
        except Exception as e:
            err_msg = str(e)
            if "routing information" in err_msg.lower() and "bolt://" not in self.uri:
                logger.error(f"❌ [NEO4J ROUTING ERROR] 路由发现失败。请检查 .env，建议将 NEO4J_URI 的协议头改为 bolt://")
            else:
                logger.error(f"❌ [NEO4J ERROR] 真实图数据库连接失败: {e}。")
            self.driver = None
            self.is_connected = False

    def get_driver(self):
        if not self.driver:
            self._init_connection()
        if not self.is_connected:
            raise RuntimeError("Neo4j 服务未连接，无法执行图查询。")
        return self.driver

    def get_ontology(self) -> str:
        """获取图数据库的本体结构（标签和关系类型）"""
        if not self.driver:
            self._init_connection()
        if not self.is_connected:
            return "Neo4j 未连接，无法获取本体结构。"
        
        try:
            with self.driver.session() as session:
                # 获取标签
                labels_res = session.run("CALL db.labels()")
                labels = [record["label"] for record in labels_res]
                
                # 获取关系类型
                rel_types_res = session.run("CALL db.relationshipTypes()")
                rel_types = [record["relationshipType"] for record in rel_types_res]
                
                ontology = "**[Neo4j Graph Ontology]**\n"
                ontology += f"- **Labels**: {', '.join(labels) if labels else 'None'}\n"
                ontology += f"- **Relationships**: {', '.join(rel_types) if rel_types else 'None'}\n"
                ontology += "请务必使用上述定义的标签和关系编写 Cypher，严禁臆造。"
                return ontology
        except Exception as e:
            logger.error(f"获取 Neo4j 本体失败: {e}")
            return "获取 Neo4j 本体结构失败。"

    def get_audit_graph_hints(self) -> str:
        """
        [企业级] 返回图谱业务模式提示。
        为 LLM 提供经过验证的 Cypher 查询模板，防止幻觉。
        """
        return """
## 🕸️ HSA 医保审计图谱模式 (权威定义)

### 1. 核心节点与关系
- `(p:Patient {psn_no})`: 参保人
- `(h:Hospital {fixmedins_code, name})`: 医疗机构
- `(t:Phone {tel})`: 手机号
- `(p)-[:VISITED {total_amt, count}]->(h)`: 就医关联
- `(p)-[:HAS_PHONE]->(t)`: 联系方式关联

### 2. 常用审计模式 (Cypher 模板)
- **共享手机号团伙发现**: 
  `MATCH (p1:Patient)-[:HAS_PHONE]->(t:Phone)<-[:HAS_PHONE]-(p2:Patient) WHERE p1.psn_no <> p2.psn_no RETURN p1.psn_no, p2.psn_no, t.tel`
- **聚集性就医模式**: 
  `MATCH (t:Phone {tel: $tel})<-[:HAS_PHONE]-(p:Patient)-[v:VISITED]->(h:Hospital) RETURN p.psn_no, h.name, v.total_amt`
- **高频就医人员提取**: 
  `MATCH (p:Patient)-[v:VISITED]->(h:Hospital) WHERE v.count > 10 RETURN p.psn_no, SUM(v.total_amt) AS total`

### 3. 编写禁忌 (Strictly Prohibited)
- ❌ 严禁使用 SQL 语法 (如 BETWEEN, LIKE)。
- ❌ 严禁使用不存在的标签 (如 shared_contacts, Doctor)。
- ❌ 严禁猜测关系名，必须使用 VISITED 或 HAS_PHONE。
"""


# ──────────────────────────────────────────────────────────────
# 模块级单例
# ──────────────────────────────────────────────────────────────
neo4j_manager = Neo4jManager()
field_kg = FieldKnowledgeGraph()   # [Phase 3-B] 字段知识图谱单例，全局可用
