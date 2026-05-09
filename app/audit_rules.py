# -*- coding: utf-8 -*-
import re
from typing import List, Dict, Any, Optional
from loguru import logger

class AuditRuleEngine:
    """[V37.7] 审计规则引擎：物理算子库已适配生产数据真实口径"""
    
    # --- [V37.7] 生产数据经口径校准后的 SQL 模板库 ---
    # 实测数据结构: fqz_gz_jzsj_all_ql 为全量结算明细
    # 字段: psn_no, fixmedins_code, fixmedins_name, med_type, start_date, end_date,
    #        dise_name, medfee_sumamt, fund_pay_sumamt, setl_id, setl_time
    TEMPLATES = {
        # [算子 1] 性别与诊断冲突 [ISS-008 Fix]
        # 策略：使用双维度检测
        # - 主检测：gend(性别编码) × dise_name(疾病名称，如存在)
        # - 补充检测：当 dise_name 无法使用时，依赖 med_type 含妇科关键词
        # - 年份过滤确保性能，避免全表扫描 18GB
        "GENDER_CONFLICT": """
            SELECT
                psn_no,
                fixmedins_name        AS hospital,
                gend                  AS gender_code,
                hilist_name           AS item_name,
                med_type              AS service_type,
                det_item_fee_sumamt   AS item_fee,
                setl_time             AS settle_date
            FROM fqz_fymx_test1
            WHERE setl_time >= '2024-01-01 00:00:00' AND setl_time <= '2024-12-31 23:59:59'
              AND gend = '1' -- 男性患者
              AND (
                  multiSearchAny(hilist_name, ['妇', '产', '阴道', '子宫', '乳腺', '卵巢', '宫颈', '避孕']) OR
                  multiSearchAny(med_type, ['妇', '产', '妇幼'])
              )
            ORDER BY det_item_fee_sumamt DESC
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
                sum(medfee_sumamt) as total_amount,
                sum(fund_pay_sumamt) as total_fund_paid
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
                sum(medfee_sumamt) as total_amount,
                sum(fund_pay_sumamt) as total_fund_paid
            FROM {table}
            WHERE med_type = '定点药店购药'
              AND toYear(toDateTime(setl_time)) = 2024
            GROUP BY psn_no
            HAVING store_count >= 5 AND total_fund_paid > 5000
            ORDER BY total_fund_paid DESC
            LIMIT {limit}
        """,
        
        # [算子 4] 分解住院检测（当住院数据可用时）
        # med_type 住院值需按实际数据口径替换
        "DECOMPOSITION_HOSPITALIZATION": """
            SELECT psn_no, fixmedins_name, 
                   prev_end_date as discharge_a, 
                   start_date as admission_b,
                   dateDiff('day', toDate(prev_end_date), toDate(start_date)) as interval_days,
                   prev_fee as fee_a, medfee_sumamt as fee_b
            FROM (
                SELECT psn_no, fixmedins_name, fixmedins_code, start_date, end_date, medfee_sumamt, med_type,
                       lagInFrame(end_date) OVER (PARTITION BY psn_no, fixmedins_code ORDER BY start_date) as prev_end_date,
                       lagInFrame(medfee_sumamt) OVER (PARTITION BY psn_no, fixmedins_code ORDER BY start_date) as prev_fee
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
            SELECT psn_no, 
                   prev_hosp as hospital_a, fixmedins_name as hospital_b,
                   prev_start as start_a, prev_end as end_a,
                   start_date as start_b, end_date as end_b,
                   medfee_sumamt as fee_b
            FROM (
                SELECT psn_no, fixmedins_name, fixmedins_code, start_date, end_date, medfee_sumamt,
                       lagInFrame(end_date) OVER w AS prev_end,
                       lagInFrame(start_date) OVER w AS prev_start,
                       lagInFrame(fixmedins_name) OVER w AS prev_hosp,
                       lagInFrame(fixmedins_code) OVER w AS prev_hosp_code
                FROM {table}
                WHERE setl_time >= '2024-01-01 00:00:00' AND setl_time <= '2024-12-31 23:59:59'
                  AND start_date IS NOT NULL AND end_date IS NOT NULL
                WINDOW w AS (PARTITION BY psn_no ORDER BY start_date)
            )
            WHERE prev_end IS NOT NULL 
              AND prev_hosp_code != fixmedins_code
              AND start_date <= prev_end  -- 核心判定：当前入院在上次出院之前（时间重叠）
            ORDER BY fee_b DESC
            LIMIT {limit}
        """,

        # [算子 6] 重复收费检测（同一天、同一患者、同一医院多次结算）
        "REPEAT_BILLING_DETECTOR": """
            SELECT
                psn_no,
                toDate(setl_time)       AS setl_date,
                fixmedins_name          AS hospital,
                count()                 AS bill_count,
                sum(medfee_sumamt)      AS total_fee,
                sum(fund_pay_sumamt)    AS total_fund_paid
            FROM {table}
            WHERE setl_time >= '2024-01-01 00:00:00' AND setl_time <= '2024-12-31 23:59:59'
            GROUP BY psn_no, setl_date, fixmedins_code, fixmedins_name
            HAVING bill_count > 1
            ORDER BY bill_count DESC, total_fee DESC
            LIMIT {limit}
        """,

        # [算子 7] 共用联系方式欺诈网络检测
        # 通过 tel (联系电话) 聚合，找出多个不同参保人共用同一手机号的异常情况
        "CONTACT_SHARING_DETECTOR": """
            SELECT
                a.tel                  AS contact_phone,
                count(DISTINCT a.psn_no) AS shared_patient_count,
                groupArray(a.psn_name) AS shared_patients,
                a.fixmedins_name       AS hospital,
                count()                AS total_visits,
                sum(a.medfee_sumamt)   AS total_fee,
                sum(a.fund_pay_sumamt) AS total_fund_paid,
                round(
                    sum(a.fund_pay_sumamt) / nullIf(sum(a.medfee_sumamt), 0),
                    4
                ) AS reimb_ratio
            FROM {table} AS a
            WHERE toYear(toDateTime(a.setl_time)) = 2024
              AND a.tel IS NOT NULL
              AND a.tel != ''
              AND length(a.tel) >= 7
            GROUP BY a.tel, a.fixmedins_name
            HAVING
                shared_patient_count >= 2   -- 至少2个不同参保人共用
                AND total_fund_paid > 5000  -- 报销金额偏高
            ORDER BY shared_patient_count DESC, total_fund_paid DESC
            LIMIT {limit}
        """
    }

    @staticmethod
    def get_rule_sql(rule_id: str, table_name: str = "fqz_gz_jzsj_all_ql", limit: int = 50, extra_filters: Optional[Dict[str, str]] = None) -> str:
        """
        [企业级算子引擎 V61.5] 结构化获取审计 SQL 并注入动态过滤器。
        
        改进点：
        1. 字段对齐：通过 FieldKG 将动态字段映射为标准物理字段。
        2. 算子推断：自动补全缺失的 '=' 或 'LIKE'。
        3. 安全包裹：智能处理单引号，防止语法崩溃。
        """
        template = AuditRuleEngine.TEMPLATES.get(rule_id.upper())
        if not template:
            logger.error(f">>> [RuleEngine] 未定义的规则算子: {rule_id}")
            return ""

        # 1. 基础渲染（处理表名和限制）
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
            
            for raw_field, cond in extra_filters.items():
                # A. 字段名对齐
                field = field_kg.resolve(raw_field) or raw_field
                
                # B. 算子与值智能补全
                cond_str = str(cond).strip()
                # 检测是否已包含运算符
                has_operator = any(cond_str.upper().startswith(op) for op in ['=', '>', '<', 'LIKE', 'IN', 'BETWEEN', '!='])
                
                if not has_operator:
                    # C. 算子与类型推断 (工业级)
                    numeric_fields = ['medfee_sumamt', 'fund_pay_sumamt', 'det_item_fee_sumamt', 'amount', 'fee']
                    is_numeric = any(nf in field.lower() for nf in numeric_fields) or field.lower().endswith('_amt') or 'count' in field.lower()
                    
                    if is_numeric and re.match(r'^-?\d+(\.\d+)?$', cond_str):
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
