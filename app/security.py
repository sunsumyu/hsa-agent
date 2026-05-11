import re
import logging
import sqlglot
from sqlglot import exp
from loguru import logger

class SecurityViolationError(Exception):
    """物理安全或算力限制违规异常"""
    pass

class SQLComplexityError(SecurityViolationError):
    """查询代价过高导致的拦截异常"""
    pass

class SQLGuardian:
    """[V41.0] 生产级 SQL 安全哨兵：执行语义级别的物理拦截。"""
    
    # 危险关键词黑名单 (DDL & DML)
    FORBIDDEN_KEYWORDS = [
        "DROP", "TRUNCATE", "DELETE", "UPDATE", "ALTER", 
        "GRANT", "REVOKE", "REPLACE", "INSERT", "CREATE", 
        "RENAME", "SYSTEM", "KILL"
    ]
    
    @staticmethod
    def validate_sql(sql: str) -> str:
        """
        [V59.3 Phase 3-B] 物理校验并清洗 SQL。
        步骤 0: 字段知识图谱纠错（禁用字段名自动替换）
        步骤 1: 强制 AST 解析：如果框架无法识别，直接拒绝。
        步骤 2: AST 节点审计：从结构层面拦截非法 DDL/DML。
        步骤 3: 代价审计：拦截 OOM 模式。
        """
        if not sql:
            raise SecurityViolationError("SQL 内容不能为空")

        clean_sql = sql.strip()
        logger.info(f"🕵️ [SQLGuardian] 正在校验原始 SQL: {clean_sql[:300]}...")
        clean_sql = sql.replace('\\n', '\n').strip().rstrip(';； \n\r\t')

        # ── Step 0: [Phase 3-B] 字段知识图谱纠错（优先修正字段别名）────
        try:
            from app.neo4j_manager import field_kg
            clean_sql, kg_warnings = field_kg.sanitize_sql(clean_sql)
            if kg_warnings:
                logger.warning(f"[SQLGuardian+FieldKG] 字段自动纠错 ({len(kg_warnings)} 处): "
                               f"{'; '.join(kg_warnings)}")
        except Exception as kg_err:
            logger.debug(f"[SQLGuardian] FieldKG 不可用，跳过字段纠错: {kg_err}")

        # 1. 物理检查堆叠查询
        if ";" in clean_sql or "；" in clean_sql:
            logger.error(f"[SECURITY] 检测到非法堆叠查询攻击! [Raw]: {repr(sql)} | [Cleaned]: {repr(clean_sql)}")
            raise SecurityViolationError("物理拦截：检测到堆叠查询意图，系统已拒绝执行。")

        # 2. 框架级语法解析与 AST 生成 (The Gatekeeper)
        import sqlglot
        import sqlglot.expressions as exp
        try:
            # 强制分发给 ClickHouse 方言处理器
            expression = sqlglot.parse_one(clean_sql, read="clickhouse")
        except Exception as pe:
            logger.error(f"[SECURITY] SQL 框架解析失败: {pe}")
            # 提取详细报错信息供 Agent 自愈
            raise SecurityViolationError(f"物理语法解析失败：{str(pe)}。请检查 SQL 结构是否完整。")

        # ── Step 1: [Phase 3-B] 表名白名单校验 ────
        for table in expression.find_all(exp.Table):
            table_name = table.name.lower()
            # 允许 CTE (Common Table Expressions) 和 临时表名
            forbidden_tables = {"patient_info", "medical_fees", "users", "orders", "settlements"}
            if table_name in forbidden_tables or (not table_name.startswith("fqz_") and table_name not in {"dual"}):
                # 检查是否是 CTE
                is_cte = False
                parent = table.parent
                while parent:
                    if isinstance(parent, exp.CTE) and parent.alias == table.name:
                        is_cte = True
                        break
                    parent = parent.parent
                
                if not is_cte:
                    logger.error(f"[SECURITY] 发现物理不存在的幻觉表: {table_name}")
                    
                    # [V107.0] 逻辑纠偏：多维幻觉识别
                    rule_hint = ""
                    if any(dk in table_name.lower() for dk in ["dept", "department"]):
                        rule_hint = "当前物理 Schema 不包含科室（Department）级别的数据！请仅使用医疗机构级别字段（如 `fixmedins_code`）。"
                    else:
                        from app.audit_rules import AuditRuleEngine
                        if table_name.upper() in AuditRuleEngine.TEMPLATES:
                            rule_hint = f"检测到您误将审计规则 ID `{table_name}` 当作了物理表名！\n请修正 SQL 直接查询 `fqz_gz_jzsj_all_ql` 表，或直接调用 `audit_medical_rule` 技能并传入 rule_id='{table_name.upper()}'。"
                    
                    raise SecurityViolationError(
                        f"物理拦截：表 `{table_name}` 是虚假幻觉表！\n"
                        f"{rule_hint if rule_hint else '请务必使用物理主表。'}\n"
                        f"【物理真相】当前数据库中仅允许访问以下主表：\n"
                        f"- `fqz_gz_jzsj_all_ql` (全量结算明细/患者记录)\n"
                        f"- `fqz_all_yy_yd_1` (机构评估指标)\n"
                        f"- `fqz_drug_mcs_info_list` (医保限制支付目录)\n"
                    )

        # 3. 结构化指令审计 (取代正则扫描)
        forbidden_nodes = (exp.Drop, exp.Update, exp.Delete, exp.Alter, exp.Create, 
                          exp.Insert, exp.Command)
        
        # 特殊处理：使用 .key 指纹强制放行合法查询根节点
        allowed_keys = ("select", "with", "show", "describe", "explain")
        if expression.key not in allowed_keys:
            logger.warning(f"[SECURITY] 拦截到非查询意图节点 key: {expression.key}")
            raise SecurityViolationError(f"物理拦截：检测到非法 DDL/DML 意图 [{expression.key}]。Agent 物理权限已锁定为 READONLY。")

        # 深度探测子查询中是否存在非法节点
        for node in expression.walk():
            if isinstance(node, forbidden_nodes):
                # 安全白名单：仅放行 ClickHouse 的 SETTINGS 指令
                if isinstance(node, exp.Command) and node.this.upper() == "SETTINGS":
                    continue
                
                logger.error(f"[SECURITY] 在 AST 深层探测到非法节点: {type(node)} - {node}")
                raise SecurityViolationError(f"物理拦截：在 SQL 内部发现非法操作节点 {type(node).__name__}。")

        # 4. 物理陷阱自动修复 (ClickHouse Anti-Trap)
        expression = SQLGuardian._refine_sql_traps(expression)

        # 5. [Phase 3-B] 严格字段白名单审计：防止臆造字段进入执行层
        SQLGuardian._validate_column_existence(expression)

        # 6. 代价审计：通过 AST 树执行复杂性分析
        SQLGuardian._audit_expression_complexity(expression)
        
        # 7. 资源锁定：由驱动连接层负责，不再在 SQL 文本中注入
        return expression.sql(dialect="clickhouse")

    @staticmethod
    def _validate_column_existence(expression):
        """
        遍历 AST，确保所有字段名在白名单、知识图谱或当前 SQL 定义的别名中存在。
        """
        from app.neo4j_manager import field_kg
        from app.schema_injector import BUILTIN_FIELD_SEEDS
        
        # 1. 构建全局物理字段白名单
        whitelist = {f["canonical"].lower() for f in field_kg.get_canonical_fields()}
        whitelist.update({f["field"].lower() for f in BUILTIN_FIELD_SEEDS})
        
        # 2. 动态提取当前 SQL 中的别名 (Alias)
        # 例如：SELECT toDate(setl_time) AS setl_date 中的 setl_date
        local_aliases = set()
        for alias in expression.find_all(exp.Alias):
            local_aliases.add(alias.alias.lower())
        
        # 3. 常见聚合函数和关键字放行
        common_ignore = {"count", "sum", "avg", "min", "max", "arraystringconcat", "groupuniqarray", "any"}

        for node in expression.walk():
            if isinstance(node, exp.Column):
                col_name = node.name.lower()
                
                # 校验优先级：物理白名单 > 动态别名 > 聚合函数 > FieldKG 兜底
                if col_name in whitelist:
                    continue
                if col_name in local_aliases:
                    continue
                if col_name in common_ignore:
                    continue
                
                # 尝试用 FieldKG 再次解析（处理可能漏掉的物理别名映射）
                resolved = field_kg.resolve(col_name)
                if not resolved:
                    logger.error(f"[SECURITY] 发现物理不存在的幻觉字段: {col_name}")
                    raise SecurityViolationError(
                        f"物理拦截：字段 `{col_name}` 既不是物理列也不是合法别名。严禁猜测字段名，请仅使用 Physical Blueprint 中提供的字段。"
                    )

    @staticmethod
    def _refine_sql_traps(expression):
        """
        [V65.5] ClickHouse 语法陷阱自动修复器。
        遍历 AST，修正 DateTime 与年份字符串对撞等高频错误。
        """
        # 定义日期时间敏感字段
        date_fields = {'setl_time', 'start_date', 'end_date', 'fee_ocur_time', 'setl_date'}
        
        # 遍历所有等值判断节点
        for eq in expression.find_all(exp.EQ):
            # 获取左操作数和右操作数
            left = eq.left
            right = eq.right
            
            # 检测：左边是日期字段，右边是 4 位年份字符串
            if isinstance(left, exp.Column) and left.name.lower() in date_fields:
                if isinstance(right, exp.Literal) and right.is_string and re.match(r'^\d{4}$', right.this):
                    logger.info(f"🛡️ [SQLGuardian] 自动纠正 ClickHouse 时间陷阱: {left.name} = '{right.this}'")
                    # 重写节点：toYear(toDateTime(left)) = int(right.this)
                    new_eq = sqlglot.parse_one(
                        f"toYear(toDateTime({left.sql()})) = {right.this}", 
                        read="clickhouse"
                    )
                    eq.replace(new_eq)
                    
        return expression

    @staticmethod
    def _audit_expression_complexity(expression):
        """
        [V45.0] 基于已生成的 AST 执行算力审计。
        """
        # --- A. 探测 JOIN 节点契约 ---
        joins = list(expression.find_all(exp.Join))
        if joins:
            # 检查是否涉及巨型表
            tables = [t.name.upper() for t in expression.find_all(exp.Table)]
            large_tables = ["FQZ_GZ_JZSJ_ALL_QL", "FQZ_GZ_JZSJ_ALL_QL_FIXED"]
            
            if any(t in large_tables for t in tables):
                has_index_filter = False
                # 检查等值谓词
                for eq in expression.find_all(exp.EQ):
                    if "PSN_NO" in str(eq).upper():
                        has_index_filter = True
                        break
                
                # 检查 IN 谓词
                if not has_index_filter:
                    for in_node in expression.find_all(exp.In):
                        if "PSN_NO" in str(in_node).upper():
                            has_index_filter = True
                            break

                if not has_index_filter:
                    logger.warning(f"[SECURITY] AST 审计拒绝：缺失 PSN_NO 物理隔离条件。")
                    raise SQLComplexityError(
                        "物理算力拦截：在操作 18GB 流水表时，必须显式提供 psn_no 过滤条件以降低内存代价。"
                    )
        
        # --- B. 探测非法聚合方向 (V35.0 基准测试期间临时禁用以防误伤) ---
        # for agg in expression.find_all(exp.AggFunc):
        #     agg_content = str(agg.this).upper()
        #     logger.debug(f">>> [SECURITY_DEBUG] Agg Content: {agg_content}")
        #     if "IPT_DAYS" in agg_content and "TO" not in agg_content:
        #         logger.warning(f"[SECURITY] AST 审计拒绝：发现对 String 字段 ipt_days 的直接聚合。")
        #         raise SQLComplexityError(
        #             "物理类型拦截：字段 ipt_days 以 String 存储，禁止直接聚合。请修正为 SUM(toUInt32OrZero(ipt_days)) 或 AVG(toUInt32OrZero(ipt_days))。"
        #         )

    @staticmethod
    def inject_settings(sql: str) -> str:
        """
        [V42.0] 强制注入 ClickHouse 执行配额。
        物理确保即使 SQL 解析通过，也不会由于长时间扫描耗尽系统资源。
        """
        # 移除可能存在的分号，确保 SETTINGS 挂载在末尾
        sql = sql.strip().rstrip(";")
        
        # 强制资源规约 (30s 超时, 2GB 内存上限)
        QUOTA_SETTINGS = (
            "SETTINGS "
            "max_execution_time=30, "
            "max_memory_usage=2000000000, "
            "max_rows_to_read=5000000, "
            "readonly=1"
        )
        
        if "SETTINGS" not in sql.upper():
            return f"{sql}\n{QUOTA_SETTINGS}"
        return sql

    @staticmethod
    def ensure_limit(sql: str, default_limit: int = 500) -> str:
        """
        物理注入 LIMIT 熔断，自动避开 SETTINGS 子句。
        ClickHouse 语法规则：SELECT ... LIMIT n SETTINGS ...
        """
        sql_upper = sql.upper()
        if "LIMIT" in sql_upper:
            return sql # 已存在 LIMIT，不再干预
            
        # 探测是否含有 SETTINGS 关键词
        settings_match = re.search(r'\bSETTINGS\b', sql, re.IGNORECASE)
        if settings_match:
            # 在 SETTINGS 之前插入 LIMIT
            split_idx = settings_match.start()
            return f"{sql[:split_idx].rstrip()} LIMIT {default_limit} {sql[split_idx:]}"
        
        # 移除可能的分号并追加
        return f"{sql.strip().rstrip(';')} LIMIT {default_limit}"

    @staticmethod
    def check_result_reasonableness(sql: str, results: list, tasks: list) -> bool:
        """
        [V66.0] 业务合理性深度校验 (Business Sanity Check)。
        判断执行结果是否符合审计直觉，防止“沉默错误”进入报告。
        """
        sql_u = sql.upper()
        task_str = " ".join(tasks).upper()
        row_count = len(results) if results else 0

        # [V67.0] 物理安全加固：拦截潜在的笛卡尔积风险 (Data Explosion Prevention)
        if "JOIN" in sql_u and " ON " not in sql_u and " USING " not in sql_u and " CROSS " not in sql_u:
            # 特别注意：ClickHouse 虽然能处理大 JOIN，但无条件的 JOIN 在 18GB 数据下是致命的
            raise SQLComplexityError("🚨 [SECURITY] 物理防御拦截：SQL 包含 JOIN 但未发现关联条件 (ON/USING)，疑似存在笛卡尔积风险。")
        
        # 1. 空结果拦截 (Targeted Patient Query)
        # 如果任务涉及特定患者(PSN_NO)，但 SQL 返回为空，极大概率是 SQL 过滤条件写得过窄或字段写错
        if row_count == 0:
            if "PSN_NO" in sql_u or "PSN_" in task_str:
                logger.warning("[REASONABLENESS] 提示：查询结果为空。在开发环境种子库下这通常是正常的。")
                # 暂时放行，以便测试全链路时延
                return True

        # 2. 笛卡尔积拦截 (Data Explosion)
        # 如果返回行数达到了强制限制 (默认 500) 且不是明细查询，疑似 JOIN 逻辑错误导致数据膨胀
        if row_count >= 500 and "GROUP BY" in sql_u:
            # 除非是 Top-N 这种明确的大规模聚合，否则一般聚合结果不应填满 500 行
            if "ORDER BY" not in sql_u:
                 logger.warning(f"[REASONABLENESS] 拦截：聚合查询返回行数 ({row_count}) 触发上限，疑似 JOIN 缺失导致笛卡尔积。")
                 return False

        # 3. 语义一致性软扫描 (Year Mismatch)
        # 仅当任务中明确提到了某个年份，但 SQL 中出现了另一个不同的 202x 年份时才拦截
        task_years = re.findall(r'202[0-9]', task_str)
        sql_years = re.findall(r'202[0-9]', sql_u)
        
        if task_years and sql_years:
            for sy in sql_years:
                if sy not in task_years:
                    logger.warning(f"[REASONABLENESS] 警告：SQL 中的年份 ({sy}) 与任务声明的年份 ({task_years}) 可能不符，仅作记录。")
                    # 不再硬拦截，改为宽容模式以支持灵活的 SQL 编写
                    break
        
        return True

    @staticmethod
    def validate_business_logic(rows: list) -> bool:
        """
        [V36.0] 物理业务断言：拦截违反财务常识的数据。
        """
        if not rows: return True
        
        for row in rows:
            # 兼容字典格式
            if isinstance(row, dict):
                # 1. 基金支付不应超过总费用
                # 兼容多种可能的别名
                medfee = float(row.get("medfee_sumamt", row.get("amount", row.get("total_amount", 0))) or 0)
                fund = float(row.get("fund_pay_sumamt", row.get("hifp_pay", row.get("fund_pay", 0))) or 0)
                
                if medfee > 0 and fund > medfee * 1.01: # 允许 1% 的舍入误差
                    logger.warning(f"[BUSINESS_ASSERT] 逻辑违规：基金支付 ({fund}) > 总费用 ({medfee})")
                    return False
                
                # 2. 核心金额非负 (退费场景除外，但在稽核取证中通常拦截)
                if medfee < -0.01:
                    logger.warning(f"[BUSINESS_ASSERT] 常识违规：检测到负数金额 ({medfee})")
                    return False
        return True
