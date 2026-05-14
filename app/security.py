import re
import logging
import sqlglot
from sqlglot import exp
from loguru import logger

from app.core.schema_registry import schema_registry

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
    def validate_sql(sql: str) -> str:
        """
        [V59.3 Phase 3-B] 物理校验并清洗 SQL。
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

        # ── Step 0: 字段知识图谱纠错 ────
        try:
            from app.neo4j_manager import field_kg
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

        # ── Step 1: 表名白名单校验 (从 SchemaRegistry 读取) ────
        forbidden_tables = {t.lower() for t in schema_registry.get_forbidden_table_names()}
        valid_prefixes = tuple(p.lower() for p in schema_registry.get_valid_prefixes())
        for table in expression.find_all(exp.Table):
            table_name = table.name.lower()
            if table_name in forbidden_tables or (
                not any(table_name.startswith(p) for p in valid_prefixes)
                and table_name not in {"dual"}
            ):
                is_cte = False
                parent = table.parent
                while parent:
                    if isinstance(parent, exp.CTE) and parent.alias == table.name:
                        is_cte = True
                        break
                    parent = parent.parent
                
                if not is_cte:
                    logger.error(f"[SECURITY] 发现物理不存在的幻觉表: {table_name}")
                    raise SecurityViolationError(f"物理拦截：表 `{table_name}` 是虚假幻觉表！请务必使用物理主表。")

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
            t_name_lower = table_node.this.this.lower()
            if t_name_lower in all_physical_tables:
                actual_name = all_physical_tables[t_name_lower]
                if table_node.this.this != actual_name:
                    logger.warning(f"🔧 [SQLGuardian] 检测到表名大小写差异，已自动修正: {table_node.this.this} -> {actual_name}")
                    table_node.this.set("this", actual_name)

        return expression.sql(dialect="clickhouse")

    @staticmethod
    def _validate_column_existence(expression):
        """
        [V113.0] 物理真理对撞：基于 AST 执行严格的表级字段与函数校验。
        不再使用模糊的全局白名单，而是精准对撞 SchemaRegistry 中的物理表列。
        """
        from app.core.schema_registry import schema_registry
        from app.neo4j_manager import field_kg
        
        # 1. 提取当前 SQL 涉及的所有物理表
        tables = [t.name.lower() for t in expression.find_all(exp.Table)]
        
        # 2. 构建针对当前表的“物理真理库”
        physical_columns = set()
        for t_name in tables:
            # 路径 A: 从 YAML 静态注册表读取
            entry = schema_registry.get_table(t_name)
            if entry:
                physical_columns.update([c.lower() for c in entry.field_names])
            
            # 路径 B [V128.6 企业级补强]: 从物理同步管理器 (SchemaManager) 读取
            from app.schema_manager import schema_manager
            dynamic_cols = schema_manager._schema_cache.get(t_name.upper(), [])
            if dynamic_cols:
                physical_columns.update([c.lower() for c in dynamic_cols])
        
        # 3. 常见聚合函数与本地别名
        local_aliases = {alias.alias.lower() for alias in expression.find_all(exp.Alias)}
        # ClickHouse 常用内置函数白名单 (部分)
        allowed_functions = {
            "count", "sum", "avg", "min", "max", "toyear", "tomonth", "todatetime", "todate", 
            "datediff", "ifnull", "arraystringconcat", "groupuniqarray", "multisearchany",
            "substring", "countdistinct", "grouparray", "tostring", "toint64", "coalesce",
            "any", "uniq", "round", "length", "format", "if", "multiif", "greatest", "least",
            "and", "or", "not", "anonymous", "anonymousaggfunc"
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
        return expression

    @staticmethod
    def _audit_expression_complexity(expression):
        """
        [V71.0 系统性修复] 基于 AST 的算力审计：从“个人过滤”转向“分区隔离”。
        """
        joins = list(expression.find_all(exp.Join))
        table_names = [t.name.upper() for t in expression.find_all(exp.Table)]
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
                if "PSN_NO" in pred_str:
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
                        join_table = join_node.this.name.upper()
                        if join_table in large_tables or (join_table and join_table not in catalog_tables):
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
