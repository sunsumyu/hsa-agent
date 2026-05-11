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

        # ── Step 0: 字段知识图谱纠错 ────
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
        
        return expression.sql(dialect="clickhouse")

    @staticmethod
    def _validate_column_existence(expression):
        """
        [V80.0] 遍历 AST，确保所有字段名在物理真相中心（SchemaManager）中存在。
        """
        from app.schema_manager import schema_manager
        from app.neo4j_manager import field_kg
        
        # 1. 获取动态物理白名单
        whitelist = schema_manager.get_all_columns()
        
        local_aliases = {alias.alias.lower() for alias in expression.find_all(exp.Alias)}
        common_ignore = {"count", "sum", "avg", "min", "max", "arraystringconcat", "groupuniqarray", "any"}

        for node in expression.walk():
            if isinstance(node, exp.Column):
                raw_name = node.name
                if not isinstance(raw_name, str) or not raw_name.strip():
                    continue
                col_name = raw_name.lower()
                
                if col_name in whitelist or col_name in local_aliases or col_name in common_ignore:
                    continue
                
                # 尝试用 FieldKG 再次解析（处理物理别名映射）
                resolved = field_kg.resolve(col_name)
                if not resolved:
                    logger.error(f"[SECURITY] 发现物理不存在的幻觉字段: {col_name}")
                    raise SecurityViolationError(
                        f"物理拦截：字段 `{col_name}` 既不是物理列也不是合法别名。严禁猜测字段名，请仅使用 Physical Blueprint 中提供的字段。"
                    )

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
            
            for predicate in expression.find_all((exp.EQ, exp.In, exp.GT, exp.LT, exp.Between)):
                pred_str = str(predicate).upper()
                if "PSN_NO" in pred_str:
                    has_index_filter = True
                if any(tf in pred_str for tf in ["SETL_TIME", "START_DATE", "END_DATE"]):
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
