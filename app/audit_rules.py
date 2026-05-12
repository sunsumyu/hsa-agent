# -*- coding: utf-8 -*-
import re
from typing import List, Dict, Any, Optional
from loguru import logger

class AuditRuleEngine:
    """[V37.7 重构] 审计规则引擎：SQL 模板已外置到 rules/sql_templates.yaml。
    
    本类作为历史兼容层保留, 实际模板从 app.core.rule_registry 加载。
    新增规则只需编辑 YAML 配置, 无需修改 Python 源码。
    """
    
    # [DEPRECATED] 保留 TEMPLATES 字典用于向后兼容, 但内容已移至 rules/sql_templates.yaml
    # 若 YAML 缺失或加载失败, 可作为兜底
    TEMPLATES = {
        # [算子 1] 性别与诊断冲突 [ISS-008 Fix]
        "GENDER_CONFLICT": """
            SELECT
                A.psn_no,
                A.fixmedins_name      AS hospital,
                A.gend                AS gender_code,
                A.hilist_name         AS hilist_name,
                C.nat_hi_druglist_memo AS rule_limit,
                A.medfee_sumamt AS amount,
                A.setl_time           AS setl_time
            FROM fqz_gz_jzsj_all_ql A
            LEFT JOIN fqz_drug_mcs_info_list C ON A.hilist_code = C.med_list_code
            WHERE A.setl_time >= '2024-01-01 00:00:00' AND A.setl_time <= '2024-12-31 23:59:59'
              AND A.gend = '1' -- 男性患者
              -- [V76.3] 工业级健壮逻辑：联合物理限制字段与多维名称关键词校验
              AND (
                  C.nat_hi_druglist_memo LIKE '%限女性%' 
                  OR A.hilist_name LIKE '%妇科%' 
                  OR A.hilist_name LIKE '%产科%' 
                  OR A.hilist_name LIKE '%子宫%'
                  OR A.hilist_name LIKE '%阴道%'
              )
            ORDER BY A.medfee_sumamt DESC
            LIMIT {limit}
        """,

        
        # [算子 2] 高频购药异常（同一参保人在同一药店短时间内多次购药）
        # 适配 fqz_gz_jzsj_all_ql 真实字段: med_type='零售药店购药'
        "HIGH_FREQ_DRUG_PURCHASE": """
            SELECT 
                psn_no, 
                fixmedins_name as drug_store,
                count() as purchase_count,
                min(setl_time) as first_purchase,
                max(setl_time) as last_purchase,
                sum(medfee_sumamt) as sum_medfee_sumamt,
                sum(fund_pay_sumamt) as sum_fund_pay_sumamt
            FROM {table}
            WHERE med_type = '定点药店购药'
              AND toYear(toDateTime(setl_time)) = 2024
            GROUP BY psn_no, fixmedins_code, fixmedins_name
            HAVING purchase_count >= 10
            ORDER BY purchase_count DESC
            LIMIT {limit}
        """,
        
        # [算子 3] 同一参保人跨药店高消费异常
        "CROSS_STORE_HIGH_SPEND": """
            SELECT 
                psn_no,
                count(DISTINCT fixmedins_code) as store_count,
                count() as total_purchases,
                sum(medfee_sumamt) as sum_medfee_sumamt,
                sum(fund_pay_sumamt) as sum_fund_pay_sumamt
            FROM {table}
            WHERE med_type = '定点药店购药'
              AND toYear(toDateTime(setl_time)) = 2024
            GROUP BY psn_no
            HAVING store_count >= 5 AND sum_fund_pay_sumamt > 5000
            ORDER BY sum_fund_pay_sumamt DESC
            LIMIT {limit}
        """,
        
        "DECOMPOSITION_HOSPITALIZATION": """
            SELECT psn_no, fixmedins_name, 
                   prev_end_date as discharge_a, 
                   start_date as admission_b,
                   dateDiff('day', toDate(prev_end_date), toDate(start_date)) as interval_days,
                   prev_fee as fee_a, medfee_sumamt as fee_b
            FROM (
                SELECT psn_no, fixmedins_name, fixmedins_code, start_date, end_date, medfee_sumamt, med_type,
                       lag(end_date) OVER (PARTITION BY psn_no, fixmedins_code ORDER BY start_date) as prev_end_date,
                       lag(medfee_sumamt) OVER (PARTITION BY psn_no, fixmedins_code ORDER BY start_date) as prev_fee
                FROM {table}
                WHERE toYear(toDateTime(start_date)) = 2024
            )
            WHERE prev_end_date IS NOT NULL 
              AND med_type NOT LIKE '%药%'
              AND dateDiff('day', toDate(prev_end_date), toDate(start_date)) BETWEEN 1 AND 15
            ORDER BY interval_days ASC
            LIMIT {limit}
        """,
        
        # [算子 5] 跨机构同日结算（疑似挂名）
        # [算子 3] 跨机构重复住院（同一参保人在不同医院、时间重叠的住院记录）
        "CROSS_HOSPITAL_OVERLAP": """
            SELECT 
                A.psn_no, 
                A.fixmedins_name AS hospital_a, 
                B.fixmedins_name AS hospital_b,
                A.start_date AS start_a, 
                A.end_date AS end_a,
                B.start_date AS start_b, 
                B.end_date AS end_b,
                B.medfee_sumamt AS fee_b
            FROM {table} A
            JOIN {table} B ON A.psn_no = B.psn_no
            WHERE A.fixmedins_code != B.fixmedins_code
              AND A.med_type LIKE '%住院%' AND B.med_type LIKE '%住院%'
              AND A.start_date >= '2024-01-01' AND B.start_date >= '2024-01-01'
              AND A.start_date <= B.end_date 
              AND B.start_date <= A.end_date
              AND A.setl_id < B.setl_id -- 去重对称结果
            ORDER BY fee_b DESC
            LIMIT {limit}
        """,

        "REPEAT_BILLING_DETECTOR": """
            SELECT
                psn_no,
                setl_id,
                toDate(setl_time)       AS setl_time_date,
                fixmedins_name          AS fixmedins_name,
                count()                 AS item_count,
                sum(medfee_sumamt)      AS sum_det_item_fee
            FROM fqz_gz_jzsj_all_ql
            WHERE setl_time >= '2024-01-01 00:00:00' AND setl_time <= '2024-12-31 23:59:59'
            GROUP BY psn_no, setl_id, setl_time_date, fixmedins_code, fixmedins_name
            HAVING item_count > 50  -- 聚焦于单次就诊内的极端明细记录
            ORDER BY item_count DESC, sum_det_item_fee DESC
            LIMIT {limit}
        """,
        
        # [算子 6] 联系方式共用 (患者与职工)
        "CONTACT_SHARING_DETECTOR": """
            SELECT 
                A.psn_no,
                A.psn_name,
                A.fixmedins_name,
                A.tel,
                count(DISTINCT A.setl_id) as visit_count,
                sum(A.medfee_sumamt) as total_amt
            FROM {table} A
            WHERE A.setl_time >= '2024-01-01 00:00:00'
              AND A.tel IN (SELECT tel FROM {table} WHERE med_type LIKE '%职工%' AND setl_time >= '2024-01-01 00:00:00')
              AND A.med_type NOT LIKE '%职工%'
            GROUP BY A.psn_no, A.psn_name, A.fixmedins_name, A.tel
            ORDER BY total_amt DESC
            LIMIT {limit}
        """,

    }

    @staticmethod
    def get_rule_sql(rule_id: str, table_name: Optional[str] = None, limit: int = 50, extra_filters: Optional[Dict[str, str]] = None) -> str:
        """
        [企业级算子引擎 V62.0] 优先从 YAML RuleRegistry 加载, fallback 到内置 TEMPLATES。
        """
        # 1b. 优先走外置 YAML Registry
        sql = ""
        try:
            from app.core.rule_registry import rule_registry
            # 如果 caller 没传 table_name，这里传 None 让 rule_registry 使用模板自带的 default_table
            sql = rule_registry.sql_templates.get_sql(
                rule_id, table=table_name, limit=limit
            )
        except Exception as e:
            logger.debug(f"[RuleEngine] YAML registry load failed, fallback: {e}")

        # 1c. Fallback 到内置模板
        if not sql:
            template = AuditRuleEngine.TEMPLATES.get(rule_id.upper())
            if not template:
                logger.debug(f">>> [RuleEngine] 算子 {rule_id} 不在规则库，尝试回退...")
                return ""
            
            # Legacy fallback: if table_name still None, use main table
            if table_name is None:
                try:
                    from app.core.schema_registry import schema_registry
                    table_name = schema_registry.get_main_table()
                except Exception:
                    table_name = "fqz_gz_jzsj_all_ql"
            
            sql = template.format(table=table_name, limit=limit)
        
        # 2. 清理：移除残留在模板功能区的中文干扰项（保护单引号内业务关键词）
        import re
        def _clean_non_sql_chinese(text):
            literals = re.findall(r"'(?:''|[^'])*'", text)
            placeholder_text = re.sub(r"'(?:''|[^'])*'", "___SQL_LITERAL___", text)
            cleaned_text = re.sub(r'[^\x00-\x7f]+', ' ', placeholder_text)
            for lit in literals:
                cleaned_text = cleaned_text.replace("___SQL_LITERAL___", lit, 1)
            return cleaned_text

        lines = []
        for line in sql.split('\n'):
            if '--' in line:
                parts = line.split('--', 1)
                clean_part = _clean_non_sql_chinese(parts[0])
                lines.append(f"{clean_part} -- {parts[1]}")
            else:
                lines.append(_clean_non_sql_chinese(line))
        sql = '\n'.join(lines)

        # 3. 动态过滤器注入 (SQLBooster V2)
        if extra_filters:
            from app.neo4j_manager import field_kg
            filter_clauses = []
            
            from app.core.schema_registry import schema_registry
            # 获取主表物理字段，用于熔断校验
            main_table = schema_registry.get_main_table()
            physical_cols = schema_registry.get_column_names(main_table)

            for raw_field, cond in extra_filters.items():
                # A. 字段名对齐
                field = field_kg.resolve(raw_field)
                
                # [V118.2] 物理真理熔断：如果 KG 无法对齐，必须通过 SchemaRegistry 校验物理存在
                if not field:
                    if raw_field.lower() in [c.lower() for c in physical_cols]:
                        field = raw_field
                    else:
                        logger.warning(f"⚠️ [RuleEngine] 拦截到幻觉字段注入意图: {raw_field}。物理表 {main_table} 中不存在此列，已跳过。")
                        continue
                
                # B. 算子与值智能补全
                cond_str = str(cond).strip()
                # 检测是否已包含运算符
                has_operator = any(cond_str.upper().startswith(op) for op in ['=', '>', '<', 'LIKE', 'IN', 'BETWEEN', '!='])
                
                # [V65.4] 智能日期/时间陷阱修复
                date_fields = ['setl_time', 'start_date', 'end_date', 'fee_ocur_time', 'setl_date']
                is_date_field = any(df in field.lower() for df in date_fields)
                
                if not has_operator:
                    # C. 算子与类型推断 (工业级)
                    numeric_fields = ['medfee_sumamt', 'fund_pay_sumamt', 'amount', 'fee']
                    is_numeric = any(nf in field.lower() for nf in numeric_fields) or field.lower().endswith('_amt') or 'count' in field.lower()
                    
                    if is_date_field and re.match(r'^\d{4}$', cond_str):
                        # 场景：字段是日期时间，但值只是 4 位年份（如 2024）
                        # 自动转换为 toYear(toDateTime(field)) = 2024
                        safe_predicate = f"toYear(toDateTime({field})) = {cond_str}"
                    elif is_numeric and re.match(r'^-?\d+(\.\d+)?$', cond_str):
                        # 确实是数字字段且值合法
                        safe_predicate = f"{field} = {cond_str}"
                    else:
                        # 字符串字段或非纯数字值，强制包裹单引号
                        if cond_str.startswith("'") and cond_str.endswith("'"):
                            safe_predicate = f"{field} = {cond_str}"
                        else:
                            # 处理转义：防止注入值本身含有单引号
                            escaped_val = cond_str.replace("'", "''")
                            safe_predicate = f"{field} = '{escaped_val}'"
                else:
                    # 已有运算符，直接组合
                    safe_predicate = f"{field} {cond_str}"
                
                filter_clauses.append(f"({safe_predicate})")
            
            if filter_clauses:
                combined_filter = " AND ".join(filter_clauses)
                
                # 寻找关键插入点
                insert_pos = -1
                for marker in [r"\bGROUP\s+BY\b", r"\bHAVING\b", r"\bORDER\s+BY\b", r"\bLIMIT\b"]:
                    match = re.search(marker, sql, re.IGNORECASE)
                    if match:
                        if insert_pos == -1 or match.start() < insert_pos:
                            insert_pos = match.start()
                
                where_match = re.search(r"\bWHERE\b", sql, re.IGNORECASE)
                
                if where_match:
                    patch = f" AND {combined_filter} "
                    if insert_pos != -1:
                        sql = sql[:insert_pos] + patch + sql[insert_pos:]
                    else:
                        sql += patch
                else:
                    patch = f" WHERE {combined_filter} "
                    if insert_pos != -1:
                        sql = sql[:insert_pos] + patch + sql[insert_pos:]
                    else:
                        sql += patch
            
            logger.info(f">>> [RuleEngine] 工业级逻辑注入成功: {extra_filters}")
            
        return sql

    @staticmethod
    def format_violation_report(rule_id: str, results: List[Dict[str, Any]]) -> str:
        """将物理取证结果转化为业务反馈"""
        if not isinstance(results, list):
            return f"数据格式错误：期望列表，实际获得 {type(results)}。详情: {results}"
            
        if not results:
            return "经过规则对撞，未发现该项违规行为。"
        
        count = len(results)
        
        # 尝试汇总金额
        total_amt = 0.0
        for item in results:
            for key in ['medfee_sumamt', 'total_amount', 'total_fund_paid', 'fee_a']:
                if key in item:
                    try:
                        total_amt += float(item[key])
                        break
                    except (ValueError, TypeError):
                        pass
        
        md = f"### 规则对撞详情: {rule_id}\n\n"
        md += f"**审计结论**: 发现疑似违规记录 **{count}** 条，涉及医疗总额 **¥{total_amt:,.2f}**。\n\n"
        md += "**前10条证据明细：**\n\n"
        
        for i, item in enumerate(results[:10]):
            psn = item.get('psn_no', 'N/A')[:8] + '****'  # 脱敏
            md += f"{i+1}. psn:{psn} | "
            # 打印所有键值对
            for k, v in item.items():
                if k != 'psn_no':
                    md += f"{k}={v} | "
            md += "\n"
            
        if count > 10:
            md += f"\n*...其余 {count-10} 条证据已在物理缓冲区固化。*"
        
        return md

rule_engine = AuditRuleEngine()
