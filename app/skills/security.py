import re
import logging
import sqlglot
from sqlglot import exp
from loguru import logger

from app.core.registry.schema_registry import schema_registry

class SecurityViolationError(Exception):
    """物理安全或算力限制违规异常"""
    pass

class SQLComplexityError(SecurityViolationError):
    """查询代价过高导致的拦截异常"""
    pass

class SQLGuardian:
    """[V71.0] 生产级 SQL 安全哨兵：执行语义级别的物理拦截。"""
    
    # 危险关键词黑名单 (DDL & DML)
    FORBIDDEN_KEYWORDS = [
        "DROP", "TRUNCATE", "DELETE", "UPDATE", "ALTER", 
        "GRANT", "REVOKE", "REPLACE", "INSERT", "CREATE", 
        "RENAME", "SYSTEM", "KILL"
    ]
    
    @staticmethod
    def validate_sql(sql: str, tenant_id: str = None, expected_table: str = None) -> str:
        """
        [V173.0] 物理校验并执行行政区划隔离 + 场景-表映射强制验证。

        Args:
            sql: 待校验的 SQL
            tenant_id: 租户 ID（用于行政区划隔离）
            expected_table: 预期的目标表名（由 SceneTableSelector 提供）
        """
        if not sql:
            raise SecurityViolationError("SQL 内容不能为空")

        clean_sql = sql.strip()
        logger.info(f"🕵️ [SQLGuardian] 正在校验原始 SQL: {clean_sql[:300]}...")
        clean_sql = sql.replace('\\n', '\n').strip().rstrip(';； \n\r\t')

        # [V90.6] Mongo / NoSQL 语法物理拦截：LLM 偶尔写出 {'$gte': ...} 当作 SQL 字面量
        _mongo_ops = ["$gte", "$lte", "$gt", "$lt", "$eq", "$ne", "$in", "$nin", "$or", "$and", "$regex"]
        for _op in _mongo_ops:
            if _op in clean_sql:
                logger.error(f"[SECURITY] 检测到 MongoDB 操作符 {_op} 混入 SQL")
                raise SecurityViolationError(
                    f"物理拦截：SQL 中混入了 MongoDB/NoSQL 操作符 `{_op}`。"
                    f"ClickHouse SQL 不支持 `{{'$gte': '2024-01-01'}}` 这种语法，"
                    f"请改写为 `setl_time >= '2024-01-01'` 这种标准 SQL 比较语法。"
                )

        # ── Step 0: 确定性架构接缝修复 (Deterministic Schema Seam via SchemaGrounder) ────
        from app.core.tool_engine.grounder import SchemaGrounder
        clean_sql, _, _ = SchemaGrounder.ground_sql(clean_sql)

        # ── Step 0.1: 字段知识图谱纠错 ────
        try:
            from app.infra.neo4j_manager import field_kg
            clean_sql, kg_warnings = field_kg.sanitize_sql(clean_sql)
            if kg_warnings:
                logger.warning(f"[SQLGuardian+FieldKG] 字段自动纠错 ({len(kg_warnings)} 处): "
                               f"{'; '.join(kg_warnings)}")
        except Exception as kg_err:
            logger.debug(f"[SQLGuardian] FieldKG 不可用，跳过字段纠错: {kg_err}")

        # 1. 物理检查堆叠查询 [V143.0 优化]：使用正则移除字符串字面量后再检查分号，防止误报。
        # 移除单引号和双引号包裹的内容
        temp_sql = re.sub(r"'(?:''|[^'])*'", "", clean_sql)
        temp_sql = re.sub(r'"(?:""|[^"])*"', "", temp_sql)
        if ";" in temp_sql or "；" in temp_sql:
            logger.error(f"[SECURITY] 检测到非法堆叠查询攻击! [Raw]: {repr(sql)} | [Cleaned]: {repr(clean_sql)}")
            raise SecurityViolationError("物理拦截：检测到堆叠查询意图，系统已拒绝执行。")

        # 2. 框架级语法解析与 AST 生成
        try:
            expression = sqlglot.parse_one(clean_sql, read="clickhouse")
        except Exception as pe:
            logger.error(f"[SECURITY] SQL 框架解析失败: {pe}")
            raise SecurityViolationError(f"物理语法解析失败：{str(pe)}。请检查 SQL 结构是否完整。")

        # ── Step 0.5: 静态 AST 恒假互斥语义拦截 ────
        from app.core.guardrails.contradiction_detector import ContradictionDetector
        contra_violation = ContradictionDetector.detect(clean_sql)
        if contra_violation:
            logger.error(f"[SECURITY] 发现逻辑恒假矛盾条件: {contra_violation.message}")
            raise SecurityViolationError(f"物理拦截：{contra_violation.message}")

        # ── Step 1: 表名白名单校验 (从 SchemaRegistry 读取) ────
        forbidden_tables = {t.lower() for t in schema_registry.get_forbidden_table_names()}
        valid_prefixes = tuple(p.lower() for p in schema_registry.get_valid_prefixes())
        
        # 收集所有的 CTE 别名，避免将它们误判为物理幻觉表
        cte_names = set()
        for cte in expression.find_all(exp.CTE):
            if cte.alias:
                cte_names.add(cte.alias.lower())
                
        for table in expression.find_all(exp.Table):
            table_name = table.name.lower()
            is_system_db = bool(table.db and table.db.lower() in {"system", "information_schema"})
            if is_system_db or table_name in cte_names or table_name in {"dual"}:
                continue
            if table_name in forbidden_tables or not any(table_name.startswith(p) for p in valid_prefixes):
                logger.error(f"[SECURITY] 发现物理不存在的幻觉表: {table_name}")
                raise SecurityViolationError(f"物理拦截：表 `{table_name}` 是虚假幻觉表！{SchemaGrounder.get_registered_tables_hint()}。")

        # ── [V173.0 NEW] 场景-表映射强制验证 ────
        if expected_table:
            used_tables = SQLGuardian._extract_tables_from_ast(expression)
            expected_lower = expected_table.lower()
            if expected_lower not in used_tables and len(used_tables) > 0:
                # 检测到使用了错误的表
                wrong_tables = [t for t in used_tables if t != expected_lower]
                logger.error(f"[SECURITY] 场景-表映射违规! 预期: {expected_table}, 实际: {wrong_tables}")
                raise SecurityViolationError(
                    f"【表选择强制拦截】检测到场景-表映射违规！\n"
                    f"预期表: `{expected_table}`\n"
                    f"实际使用的表: `{wrong_tables}`\n"
                    f"根据场景关键词分析，当前查询**必须使用 `{expected_table}`**。\n"
                    f"请修改 SQL 中的 FROM/JOIN 子句，将 `{wrong_tables[0]}` 替换为 `{expected_table}`。"
                )

        # 3. 结构化指令审计
        allowed_keys = ("select", "with", "show", "describe", "explain")
        if expression.key not in allowed_keys:
            logger.warning(f"[SECURITY] 拦截到非查询意图节点 key: {expression.key}")
            raise SecurityViolationError(f"物理拦截：检测到非法 DDL/DML 意图 [{expression.key}]。")

        forbidden_nodes = (exp.Drop, exp.Update, exp.Delete, exp.Alter, exp.Create, exp.Insert)
        for node in expression.walk():
            if isinstance(node, forbidden_nodes):
                logger.error(f"[SECURITY] 在 AST 深层探测到非法节点: {type(node)}")
                raise SecurityViolationError(f"物理拦截：在 SQL 内部发现非法操作节点 {type(node).__name__}。")

        # 4. 物理陷阱自动修复
        expression = SQLGuardian._refine_sql_traps(expression)

        # 5. 严格字段白名单审计
        SQLGuardian._validate_column_existence(expression)

        # 6. 代价审计 (Systemic Fix V71.0)
        SQLGuardian._audit_expression_complexity(expression)
        
        # ── [V132.0] 企业级自愈：自动对齐 ClickHouse 的大小写敏感表名 ────
        all_physical_tables = {t.lower(): t for t in schema_registry.get_all_table_names()}
        for table_node in expression.find_all(exp.Table):
            t_name = table_node.name
            if not t_name: continue
            
            # 物理存在性校验 (通过 schema_registry 统一深接缝)
            dynamic_cols = schema_registry.get_table_columns(t_name)
            t_name_lower = t_name.lower()
            if t_name_lower in all_physical_tables:
                actual_name = all_physical_tables[t_name_lower]
                if table_node.this.this != actual_name:
                    logger.warning(f"🔧 [SQLGuardian] 检测到表名大小写差异，已自动修正: {table_node.this.this} -> {actual_name}")
                    table_node.this.set("this", actual_name)
 
        # ── Step 7: 行政区划隔离注入 (Administrative Isolation) [V172.0] ────
        if tenant_id:
            expression = SQLGuardian._inject_tenant_isolation(expression, tenant_id)
 
        return expression.sql(dialect="clickhouse")

    @staticmethod
    def _inject_tenant_isolation(expression: exp.Expression, tenant_id: str) -> exp.Expression:
        """
        物理逻辑隔离：通过 AST 改写，强制在 WHERE 子句中注入统筹区过滤。
        """
        # 1. 查找 WHERE 子句
        where_clause = expression.find(exp.Where)
        where_str = str(where_clause).upper() if where_clause else ""

        # 2. 如果已经存在 AAA027 或 ADMIN_DIVISION 过滤，则跳过注入 (避免冗余)
        if "AAA027" in where_str or "ADMIN_DIVISION" in where_str:
            return expression

        # 3. 构造隔离条件 (aaa027 是医保结算表标准分区字段)
        # 针对所有的 SELECT 查询注入隔离条件
        if isinstance(expression, exp.Select):
             # 自动追加 AND 逻辑
             return expression.where(f"aaa027 = '{tenant_id}'", append=True)

        return expression

    @staticmethod
    def _extract_tables_from_ast(expression: exp.Expression) -> list:
        """
        [V173.0] 从 AST 中提取所有 fqz_ 开头的物理表名

        Returns:
            list: 表名列表（小写）
        """
        tables = []
        for table_node in expression.find_all(exp.Table):
            table_name = table_node.name.lower()
            if table_name.startswith('fqz_'):
                tables.append(table_name)
        return tables

    @staticmethod
    def _validate_column_existence(expression):
        """
        [V113.0] 物理真理对撞：基于 AST 执行严格的表级字段与函数校验。
        不再使用模糊的全局白名单，而是精准对撞 SchemaRegistry 中的物理表列。
        """
        from app.core.registry.schema_registry import schema_registry
        from app.infra.neo4j_manager import field_kg
        
        # 1. 提取当前 SQL 涉及的所有物理业务表 (排除 CTE 临时表以及系统元数据库表)
        cte_names = set()
        for cte in expression.find_all(exp.CTE):
            if cte.alias:
                cte_names.add(cte.alias.lower())

        tables = []
        for t in expression.find_all(exp.Table):
            t_name = t.name.lower()
            is_sys = bool(t.db and t.db.lower() in {"system", "information_schema"})
            if not is_sys and t_name not in cte_names:
                tables.append(t_name)

        # 若纯为系统元数据表探查（如 system.columns 或 information_schema.columns），跳过业务字段对撞
        if not tables:
            return

        # 2. 构建针对当前表的“物理真理库” (通过 SchemaRegistry 统一深接缝)
        physical_columns = set()
        for t_name in tables:
            physical_columns.update(schema_registry.get_table_columns(t_name))
        
        # 3. 常见聚合函数与本地别名
        local_aliases = {alias.alias.lower() for alias in expression.find_all(exp.Alias)}
        # ClickHouse 常用内置函数白名单 (部分)
        allowed_functions = {
            "count", "sum", "avg", "min", "max", "toyear", "tomonth", "todatetime", "todate", 
            "datediff", "ifnull", "arraystringconcat", "groupuniqarray", "multisearchany",
            "substring", "countdistinct", "grouparray", "tostring", "toint64", "coalesce",
            "any", "uniq", "round", "length", "format", "if", "multiif", "greatest", "least",
            "and", "or", "not", "anonymous", "anonymousaggfunc",
            "row_number", "laginframe", "lead", "lag", "rank", "dense_rank"
        }

        for node in expression.walk():
            # 校验字段 (exp.Column)
            if isinstance(node, exp.Column):
                col_name = node.name.lower()
                # 排除别名和标准计算列
                if col_name in local_aliases or col_name in {"*", "1"}:
                    continue
                
                # 核心拦截：如果不在当前表的物理列中，且 FieldKG 无法映射
                if col_name not in physical_columns:
                    resolved = field_kg.resolve(col_name)
                    if not resolved:
                        suggestion = SQLGuardian._suggest_field(col_name)
                        # [V128.1] 治理层解耦：判定层记 WARNING，避免 ERROR 堆叠
                        logger.warning(f"🛡️ [SQLGuardian] 物理字段拦截: {tables} -> `{col_name}`")
                        raise SecurityViolationError(
                            f"【物理拦截】字段 `{col_name}` 在当前表 {tables} 中不存在！"
                            f"{suggestion} "
                            f"请通过 `lookup_medical_schema` 工具获取正确物理字段。"
                        )
            
            # 校验函数 (exp.Func) [V113.0 新增]
            elif isinstance(node, exp.Func):
                func_name = node.key.lower()
                if func_name not in allowed_functions:
                    # 针对 year/month 这种典型幻觉做专门引导
                    if func_name in {"year", "month", "day"}:
                        raise SecurityViolationError(
                            f"【物理拦截】检测到非法函数 `{func_name}()`。ClickHouse 不支持此语法。"
                            f"请改用 `toYear()`, `toMonth()` 或直接使用日期字段范围过滤。"
                        )
                    logger.warning(f"⚠️ [SECURITY] 使用了非标准函数: {func_name}")

    @staticmethod
    def _suggest_field(hallucinated: str) -> str:
        """[V90.2] 对幻觉字段做模糊匹配，返回可能的正确字段建议"""
        _COMMON_HALLUCINATIONS = {
            "fee_amt": "medfee_sumamt",
            "total_fee": "medfee_sumamt",
            "amount": "medfee_sumamt",
            "pay_amount": "fund_pay_sumamt",
            "fund_amt": "fund_pay_sumamt",
            "hosp_code": "fixmedins_code",
            "hospital_id": "fixmedins_code",
            "hosp_name": "fixmedins_name",
            "hospital_name": "fixmedins_name",
            "patient_id": "psn_no",
            "patient_name": "psn_name",
            "item_name": "hilist_name",
            "drug_name": "hilist_name",
            "det_item_name": "hilist_name",
            "medical_category": "med_type",
            "type_name": "med_type",
            "settlement_time": "setl_time",
            "settle_time": "setl_time",
            "gender": "gend",
            "sex": "gend",
            # ── 虚拟计算指标：非物理字段，需通过 SQL 公式计算 ──
            "vix": "非物理字段。变异指数需计算: stddevPop(medfee_sumamt)/avg(medfee_sumamt) AS vix",
            "variation_index": "非物理字段。变异指数需计算: stddevPop(medfee_sumamt)/avg(medfee_sumamt) AS variation_index",
            "overlap_hours": "非物理字段。需计算: dateDiff('hour', greatest(a.start_date, b.start_date), least(a.end_date, b.end_date)) AS overlap_hours",
            "department_id": "非物理字段。科室信息在 dise_name 或 fixmedins_name 中",
            "dept_id": "非物理字段。科室信息在 dise_name 或 fixmedins_name 中",
            "visit_count": "非物理字段。需计算: COUNT(*) AS visit_count",
            "admission_count": "非物理字段。需计算: COUNT(*) AS admission_count",
            "age": "非物理字段。需计算: dateDiff('year', toDate(brdy), today()) AS age (brdy=出生日期字段)",
            "los": "非物理字段。住院天数需计算: dateDiff('day', start_date, end_date) AS los",
            "length_of_stay": "非物理字段。住院天数需计算: dateDiff('day', start_date, end_date) AS length_of_stay",
        }
        h = hallucinated.lower().strip()
        if h in _COMMON_HALLUCINATIONS:
            correct = _COMMON_HALLUCINATIONS[h]
            return f"建议替换: `{hallucinated}` → `{correct}`。"
        # 子串匹配
        for wrong, correct in _COMMON_HALLUCINATIONS.items():
            if wrong in h or h in wrong:
                return f"建议替换: `{hallucinated}` → `{correct}`。"
        return "无法自动推测正确字段。"

    @staticmethod
    def _refine_sql_traps(expression):
        date_fields = {'setl_time', 'start_date', 'end_date', 'fee_ocur_time', 'setl_date'}
        for eq in expression.find_all(exp.EQ):
            left, right = eq.left, eq.right
            if isinstance(left, exp.Column) and left.name.lower() in date_fields:
                if isinstance(right, exp.Literal) and right.is_string and re.match(r'^\d{4}$', right.this):
                    new_eq = sqlglot.parse_one(f"toYear(toDateTime({left.sql()})) = {right.this}", read="clickhouse")
                    eq.replace(new_eq)

        # ──【企业级 v1.2】SQL AST 级方言自愈重写 ──
        # 对语法树中的非法/非标/方言函数节点进行深度探测与平滑重写
        for node in expression.walk():
            # 1. 拦截与重写 Anonymous 节点 (sqlglot 无法解析为标准内置的自定义/外来函数)
            if isinstance(node, exp.Anonymous):
                func_name = node.name.upper()
                
                # 修复 MySQL DATEDIFF(A, B) -> ClickHouse dateDiff('day', B, A)
                if func_name == "DATEDIFF" and len(node.expressions) == 2:
                    arg1, arg2 = node.expressions[0].sql(), node.expressions[1].sql()
                    new_node = sqlglot.parse_one(f"dateDiff('day', {arg2}, {arg1})", read="clickhouse")
                    node.replace(new_node)
                    logger.success(f"🔧 [AST自愈] 自动重写 MySQL DATEDIFF 为 ClickHouse dateDiff: {node.sql()} -> {new_node.sql()}")
                
                # 修复 MySQL IFNULL(A, B) -> ClickHouse ifNull(A, B)
                elif func_name == "IFNULL" and len(node.expressions) == 2:
                    arg1, arg2 = node.expressions[0].sql(), node.expressions[1].sql()
                    new_node = sqlglot.parse_one(f"ifNull({arg1}, {arg2})", read="clickhouse")
                    node.replace(new_node)
                    logger.success(f"🔧 [AST自愈] 自动重写 IFNULL 为 ClickHouse ifNull")

                # 修复 MySQL YEAR(A) -> ClickHouse toYear(A)
                elif func_name == "YEAR" and len(node.expressions) == 1:
                    arg = node.expressions[0].sql()
                    new_node = sqlglot.parse_one(f"toYear({arg})", read="clickhouse")
                    node.replace(new_node)
                    logger.success(f"🔧 [AST自愈] 自动重写 YEAR 为 ClickHouse toYear")

                # 修复 MySQL MONTH(A) -> ClickHouse toMonth(A)
                elif func_name == "MONTH" and len(node.expressions) == 1:
                    arg = node.expressions[0].sql()
                    new_node = sqlglot.parse_one(f"toMonth({arg})", read="clickhouse")
                    node.replace(new_node)
                    logger.success(f"🔧 [AST自愈] 自动重写 MONTH 为 ClickHouse toMonth")

                # 修复 MySQL DATE_FORMAT(A, fmt) -> ClickHouse formatDateTime(A, fmt)
                elif func_name == "DATE_FORMAT" and len(node.expressions) == 2:
                    arg1, arg2 = node.expressions[0].sql(), node.expressions[1].sql()
                    new_node = sqlglot.parse_one(f"formatDateTime({arg1}, {arg2})", read="clickhouse")
                    node.replace(new_node)
                    logger.success(f"🔧 [AST自愈] 自动重写 DATE_FORMAT 为 ClickHouse formatDateTime")

                # 修复 MySQL CURDATE() -> ClickHouse today()
                elif func_name == "CURDATE":
                    new_node = sqlglot.parse_one("today()", read="clickhouse")
                    node.replace(new_node)
                    logger.success(f"🔧 [AST自愈] 自动重写 CURDATE 为 ClickHouse today()")

                # 修复 MySQL GROUP_CONCAT(col) / GROUP_CONCAT(col, sep) -> ClickHouse arrayStringConcat(groupUniqArray(col), sep)
                elif func_name == "GROUP_CONCAT" and len(node.expressions) >= 1:
                    col = node.expressions[0].sql()
                    sep = node.expressions[1].sql() if len(node.expressions) > 1 else "','"
                    new_node = sqlglot.parse_one(f"arrayStringConcat(groupUniqArray({col}), {sep})", read="clickhouse")
                    node.replace(new_node)
                    logger.success(f"🔧 [AST自愈] 自动重写 GROUP_CONCAT 为 ClickHouse arrayStringConcat")

            # 2. 拦截与重写已被部分解析的标准 AST Func 节点 (以防 sqlglot 将其解析为 DateDiff 等特定类)
            elif isinstance(node, exp.Func):
                func_name = node.key.upper()
                
                # 修复标准 DateDiff / DATEDIFF AST 节点为 ClickHouse 三参数版本
                if func_name == "DATEDIFF" and len(node.expressions) == 2:
                    arg1, arg2 = node.expressions[0].sql(), node.expressions[1].sql()
                    new_node = sqlglot.parse_one(f"dateDiff('day', {arg2}, {arg1})", read="clickhouse")
                    node.replace(new_node)
                    logger.success(f"🔧 [AST自愈] 自动重写 DATEDIFF 节点为 ClickHouse dateDiff")

        return expression

    @staticmethod
    def _audit_expression_complexity(expression):
        """
        [V71.0 系统性修复] 基于 AST 的算力审计：从“个人过滤”转向“分区隔离”。
        """
        joins = list(expression.find_all(exp.Join))
        table_names = [(t.name or "").upper() for t in expression.find_all(exp.Table)]
        # 大表列表从 SchemaRegistry 读取
        main_table = schema_registry.get_main_table().upper()
        large_tables = [main_table, f"{main_table}_FIXED"]
        
        involves_large_table = any(t in large_tables for t in table_names)
        
        if involves_large_table:
            has_index_filter = False
            has_time_filter = False
            
            # [V90.3] 扩展谓词扫描：覆盖 >=, <= 以及函数包裹的时间条件 (如 toYear(toDateTime(setl_time)))
            full_sql_upper = str(expression).upper()
            for predicate in expression.find_all((exp.EQ, exp.In, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Between)):
                pred_str = str(predicate).upper()
                if "PSN_NO" in pred_str or "SETL_ID" in pred_str:
                    has_index_filter = True
                if any(tf in pred_str for tf in ["SETL_TIME", "START_DATE", "END_DATE"]):
                    has_time_filter = True
            # Fallback: 函数包裹的时间条件（如 toYear(toDateTime(setl_time)) = 2024）
            if not has_time_filter:
                if any(tf in full_sql_upper for tf in ["SETL_TIME", "START_DATE", "END_DATE"]):
                    # 存在时间字段引用，检查是否在 WHERE 子句中
                    where_clause = expression.find(exp.Where)
                    if where_clause and any(tf in str(where_clause).upper() for tf in ["SETL_TIME", "START_DATE", "END_DATE"]):
                        has_time_filter = True
            
            is_heavy_join = False
            if joins:
                catalog_tables = {"FQZ_DRUG_MCS_INFO_LIST", "FQZ_ALL_YY_YD_1"}
                for join_node in joins:
                    if hasattr(join_node.this, 'name'):
                        join_table = (join_node.this.name or "").upper()
                        if join_table and (join_table in large_tables or join_table not in catalog_tables):
                            is_heavy_join = True
                            break
            
            if is_heavy_join and not has_index_filter:
                raise SQLComplexityError(
                    "物理算力拦截：检测到大表间关联操作。为防止 OOM，必须显式提供 psn_no 过滤条件（Investigation 模式）。"
                )
            
            if not has_index_filter and not has_time_filter:
                raise SQLComplexityError(
                    "物理算力拦截：在扫描 18GB 流水表执行 Discovery 任务时，必须显式提供 setl_time 或 start_date 时间区间（推荐 '2024-01-01' 起）以利用 ClickHouse 分区裁剪性能。"
                )

    @staticmethod
    def inject_settings(sql: str) -> str:
        sql = sql.strip().rstrip(";")
        max_time = schema_registry.get_max_execution_time()
        max_mem = schema_registry.get_max_memory_usage()
        quota_settings = (
            f"SETTINGS max_execution_time={max_time}, "
            f"max_memory_usage={max_mem}, readonly=1"
        )
        if "SETTINGS" not in sql.upper():
            return f"{sql}\n{quota_settings}"
        return sql

    @staticmethod
    def ensure_limit(sql: str, default_limit: int = 500) -> str:
        if "LIMIT" in sql.upper(): return sql
        settings_match = re.search(r'\bSETTINGS\b', sql, re.IGNORECASE)
        if settings_match:
            idx = settings_match.start()
            return f"{sql[:idx].rstrip()} LIMIT {default_limit} {sql[idx:]}"
        return f"{sql.strip().rstrip(';')} LIMIT {default_limit}"

    @staticmethod
    def check_result_reasonableness(sql: str, results: list, tasks: list) -> bool:
        sql_u = sql.upper()
        if "JOIN" in sql_u and not any(k in sql_u for k in [" ON ", " USING ", " CROSS "]):
            raise SQLComplexityError("🚨 物理防御拦截：SQL 包含 JOIN 但未发现关联条件，疑似存在笛卡尔积风险。")
        return True

    @staticmethod
    def validate_business_logic(rows: list) -> bool:
        if not rows: return True
        for row in rows:
            if isinstance(row, dict):
                medfee = float(row.get("medfee_sumamt", row.get("amount", 0)) or 0)
                fund = float(row.get("fund_pay_sumamt", row.get("fund_pay", 0)) or 0)
                if medfee > 0 and fund > medfee * 1.01: return False
                if medfee < -0.01: return False
        return True
