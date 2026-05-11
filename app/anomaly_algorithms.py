import re
from typing import List, Dict, Any, Optional
from loguru import logger

class AnomalyDetector:
    """[V70.0] 异常识别算法库：封装针对海量流水的统计学探测算子"""
    
    # --- 算法逻辑模板 ---
    ALGORITHMS = {
        "VIX_ANOMALY_SCAN": """
            SELECT fixmedins_name, vix, sum_medfee_sumamt, totlcnt_psn_no, setl_time 
            FROM {table} 
            WHERE vix >= {threshold} 
            ORDER BY vix DESC 
            LIMIT {limit}
        """,
        "STAY_SPLIT_DETECTOR": """
            SELECT a.psn_no, a.psn_name, a.fixmedins_name, a.end_date as discharge_a, b.start_date as admit_b,
                   dateDiff('day', toDate(a.end_date), toDate(b.start_date)) as interval_days
            FROM {table} AS a
            INNER JOIN {table} AS b ON a.psn_no = b.psn_no
            WHERE a.fixmedins_code = b.fixmedins_code
              AND a.mdtrt_id != b.mdtrt_id
              AND interval_days >= 0 AND interval_days <= 3
              AND a.med_type = '住院' AND b.med_type = '住院'
            LIMIT {limit}
        """,
        "CLUSTER_ENCOUNTER_DETECTOR": """
            SELECT fixmedins_name, setl_time, count(DISTINCT psn_no) as unique_patients, sum(medfee_sumamt) as total_amt
            FROM {table}
            GROUP BY fixmedins_name, setl_time
            HAVING unique_patients > {threshold}
            ORDER BY total_amt DESC
            LIMIT {limit}
        """,
        "STATISTICAL_OUTLIER_DETECTOR": """
            WITH 
                (SELECT avg(medfee_sumamt) FROM {table} WHERE medfee_sumamt > 0) AS avg_amt,
                (SELECT stddevPop(medfee_sumamt) FROM {table} WHERE medfee_sumamt > 0) AS std_amt
            SELECT 
                psn_no,
                count() as visit_count,
                sum(medfee_sumamt) as total_amt,
                sum(fund_pay_sumamt) as total_fund_paid,
                (sum(medfee_sumamt) - avg_amt) / std_amt as z_score
            FROM {table}
            WHERE medfee_sumamt > 0
            GROUP BY psn_no
            HAVING z_score > {threshold}
            ORDER BY z_score DESC
            LIMIT {limit}
        """,
        "ROBUST_MAD_DETECTOR": """
            WITH 
                (SELECT quantile(0.5)(medfee_sumamt) FROM {table} WHERE medfee_sumamt > 0) AS med_amt,
                (SELECT quantile(0.5)(abs(medfee_sumamt - med_amt)) FROM {table} WHERE medfee_sumamt > 0) AS mad_amt
            SELECT 
                psn_no,
                count() as visit_count,
                sum(medfee_sumamt) as total_amt,
                abs(sum(medfee_sumamt) - med_amt) / (mad_amt * 1.4826) as modified_z_score
            FROM {table}
            WHERE medfee_sumamt > 0
            GROUP BY psn_no
            HAVING modified_z_score > {threshold}
            ORDER BY modified_z_score DESC
            LIMIT {limit}
        """
    }

    @staticmethod
    def get_algorithm_sql(algo_id: str, params: Dict[str, Any] = {}, extra_filters: Optional[Dict[str, str]] = None) -> str:
        """根据算法 ID 与参数动态生成取证 SQL"""
        template = AnomalyDetector.ALGORITHMS.get(algo_id.upper())
        if not template:
            logger.debug(f">>> [AnomalyDetector] 算子 {algo_id} 不在算法库")
            return ""
        
        # 参数处理
        table_name = params.get("table_name", "fqz_gz_jzsj_all_ql")
        # 默认 VIX 使用统计表
        if algo_id.upper() == "VIX_ANOMALY_SCAN" and table_name == "fqz_gz_jzsj_all_ql":
            table_name = "fqz_cgzhan_hosp"
            
        threshold = params.get("threshold", 1.5 if "VIX" in algo_id else 20)
        limit = params.get("limit", 50)
        
        sql = template.format(table=table_name, threshold=threshold, limit=limit)

        # [V66.2] 动态过滤器注入：防止算法扫描全库导致 429 或 爆炸
        if extra_filters:
            from app.audit_rules import rule_engine
            # 借用 RuleEngine 的注入逻辑（如果它是静态的或可访问的）
            # 由于逻辑较复杂，这里做一个简单的 WHERE 注入
            filter_clauses = []
            for k, v in extra_filters.items():
                val = str(v).replace("'", "''")
                if not any(val.upper().startswith(op) for op in ['=', '>', '<', 'LIKE']):
                    filter_clauses.append(f"{k} = '{val}'")
                else:
                    filter_clauses.append(f"{k} {v}")
            
            if filter_clauses:
                where_patch = " AND ".join(filter_clauses)
                if "WHERE" in sql.upper():
                    sql = re.sub(r"(WHERE\s+)", rf"\1 ({where_patch}) AND ", sql, flags=re.IGNORECASE)
                else:
                    # 寻找第一个 GROUP BY 或 ORDER BY 之前插入
                    insert_pos = -1
                    for marker in [r"\bGROUP\s+BY\b", r"\bORDER\s+BY\b", r"\bLIMIT\b"]:
                        m = re.search(marker, sql, re.IGNORECASE)
                        if m and (insert_pos == -1 or m.start() < insert_pos):
                            insert_pos = m.start()
                    
                    if insert_pos != -1:
                        sql = sql[:insert_pos] + f" WHERE {where_patch} " + sql[insert_pos:]
                    else:
                        sql += f" WHERE {where_patch}"
        
        return sql

    @staticmethod
    def format_anomaly_report(algo_id: str, results: List[Dict[str, Any]]) -> str:
        """解析算法产出，生成针对管理层的风险简报"""
        if not isinstance(results, list):
            return f"数据格式错误：期望列表，实际获得 {type(results)}。详情: {results}"
            
        if not results:
            return "✅ 在设定的灵敏度阈值下，未发现异常聚集模式。"
            
        count = len(results)
        md = f"### 📊 审计算法产出: {algo_id}\n\n"
        md += f"**识别结果**: 检测到 **{count}** 个高风险实体/模式。\n\n"
        
        if algo_id.upper() == "VIX_ANOMALY_SCAN":
            md += "| 医院名称 | 变异指数 (VIX) | 结算总额 | 患者数 |\n"
            md += "| :--- | :--- | :--- | :--- |\n"
            for it in results[:10]:
                md += f"| {it.get('fixmedins_name')} | **{it.get('vix')}** | ¥{float(it.get('sum_medfee_sumamt', 0)):,.2f} | {it.get('totlcnt_psn_no')} |\n"
        
        elif algo_id.upper() == "STAY_SPLIT_DETECTOR":
            md += "| 患者姓名 | 医院名称 | 第一次出院 | 第二次入院 | 间隔天数 |\n"
            md += "| :--- | :--- | :--- | :--- | :--- |\n"
            for it in results[:10]:
                md += f"| {it.get('psn_name')} | {it.get('fixmedins_name')} | {it.get('discharge_a')} | {it.get('admit_b')} | {it.get('interval_days')} 天 |\n"
        
        elif algo_id.upper() == "STATISTICAL_OUTLIER_DETECTOR":
            md += "| 参保人ID | 就诊次数 | 累计金额 | Z-Score (离群度) |\n"
            md += "| :--- | :--- | :--- | :--- |\n"
            for it in results[:10]:
                psn = it.get('psn_no', 'N/A')[:8] + '****'
                md += f"| {psn} | {it.get('visit_count')} | ¥{float(it.get('total_amt', 0)):,.2f} | **{float(it.get('z_score', 0)):.2f}** |\n"
        
        elif algo_id.upper() == "ROBUST_MAD_DETECTOR":
            md += "| 参保人ID | 就诊次数 | 累计金额 | Modified Z-Score (抗干扰离群度) |\n"
            md += "| :--- | :--- | :--- | :--- |\n"
            for it in results[:10]:
                psn = it.get('psn_no', 'N/A')[:8] + '****'
                md += f"| {psn} | {it.get('visit_count')} | ¥{float(it.get('total_amt', 0)):,.2f} | **{float(it.get('modified_z_score', 0)):.2f}** |\n"
        
        else:
            md += "| 目标主体 | 统计时间 | 聚集规模 (人数) | 涉及金额 |\n"
            md += "| :--- | :--- | :--- | :--- |\n"
            for it in results[:10]:
                target = it.get('fixmedins_name') or it.get('psn_no')
                md += f"| {target} | {it.get('setl_time')} | {it.get('unique_patients')} | ¥{float(it.get('total_amt', 0)):,.2f} |\n"

        return md

anomaly_detector = AnomalyDetector()
