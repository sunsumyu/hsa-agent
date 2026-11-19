"""
app/core/context/funnel_baseline_builder.py
============================================
[Matt Pocock Deep Module] 语义漏斗第四层：双阶段动态基线参数封装器
专职负责：
1. 提取意图重写中的统计策略与金融度量字段
2. 构造 ICD-10 疾病编码过滤子句与横杠解包自愈
3. 拼装 ClickHouse 内存临时表 Join 片段
4. 生成 Phase 1 基线分位数探测 SQL 模板
"""

from typing import Dict, Any, List, Optional
from loguru import logger


def build_statistical_baseline(
    rewritten: Dict[str, Any],
    aligned_codes: List[str],
    temp_table: Optional[str]
) -> Dict[str, Any]:
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
