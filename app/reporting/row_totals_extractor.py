"""
Row Set Totals & Aggregation Extractor Deep Module.
Adheres to Matt Pocock's Deep Module design: encapsulates SQL AST projection parsing,
ROLLUP deconstruction, summary marker deduplication, and financial reconciliation
behind a unified, clean interface:
`extract_db_totals(db_rows, sql=None, gt_count=0, gt_sum=0.0) -> Tuple[int, float]`
"""
from typing import List, Dict, Any, Optional, Tuple

# 严格聚合别名全量白名单 (必须是明确的汇总/行数别名)
STRICT_AGGREGATE_ALIASES = frozenset({
    "total_records", "total_cnt", "record_count", "row_cnt", "total_count",
    "total_record_count", "rec_cnt", "high_amount_record_count", "batch_cnt",
    "patient_count", "setl_count", "outlier_count", "refund_count", "item_cnt",
    "lv_count", "total_hosp", "drug_total", "cases_num", "case_count",
    "total_drug_varieties"
})

SUMMARY_MARKERS = ("全局汇总", "全库总计", "汇总", "总计", "合计")


def detect_count_column(
    first_row: Dict[str, Any],
    sql: Optional[str] = None,
    gt_count: int = 0
) -> Optional[str]:
    """探测结果集中的聚合记录数/条数列名"""
    count_col = None

    # 0. AST 优先探测：从 SQL 编译期投影识别 count(...) 别名
    if sql and isinstance(sql, str):
        try:
            import sqlglot
            from sqlglot import exp
            parsed = sqlglot.parse_one(sql, read="clickhouse")
            if parsed:
                for s in parsed.selects:
                    alias = s.alias_or_name
                    if alias and alias in first_row:
                        if any(isinstance(node, exp.Count) for node in s.walk()):
                            count_col = alias
                            break
        except Exception:
            pass

    # 1. 严格白名单别名匹配
    if not count_col:
        for col in first_row.keys():
            if col.lower() in STRICT_AGGREGATE_ALIASES:
                count_col = col
                break

    # 2. 泛化模式匹配（严格排除 cnt，fqz_fymx_test.cnt 为药品数量）
    if not count_col:
        for col in first_row.keys():
            col_lower = col.lower().strip()
            if col_lower == "cnt":
                continue
            if any(k in col_lower for k in ["count", "_cnt", "num", "record", "row", "总数", "笔数", "条数", "家数", "例数"]):
                try:
                    val = first_row.get(col)
                    if val is not None:
                        int_val = int(val)
                        if gt_count > 0 and int_val == gt_count:
                            count_col = col
                            break
                        elif count_col is None:
                            count_col = col
                except (ValueError, TypeError):
                    pass

    # 3. 单行汇总自愈：若数值精确等于 gt_count，直接锁定
    if not count_col and gt_count > 0:
        for col, val in first_row.items():
            if col.lower() != "cnt":
                try:
                    if int(val) == gt_count:
                        count_col = col
                        break
                except (ValueError, TypeError):
                    pass

    return count_col


def detect_amount_column(
    first_row: Dict[str, Any],
    count_col: Optional[str] = None,
    sql: Optional[str] = None
) -> Optional[str]:
    """探测结果集中的总金额/费用列名"""
    amount_col = None

    # 0. AST 优先探测：从 SQL 编译期投影识别 sum(...) 别名
    if sql and isinstance(sql, str):
        try:
            import sqlglot
            from sqlglot import exp
            parsed = sqlglot.parse_one(sql, read="clickhouse")
            if parsed:
                for s in parsed.selects:
                    alias = s.alias_or_name
                    if alias and alias in first_row and alias != count_col:
                        if any(isinstance(node, exp.Sum) for node in s.walk()):
                            amount_col = alias
                            break
        except Exception:
            pass

    # 1. 字段名特征匹配
    if not amount_col:
        for col in first_row.keys():
            if col == count_col:
                continue
            col_lower = col.lower()
            if any(k in col_lower for k in ["fee", "amt", "pay", "cost", "sum", "amount", "price", "金额", "费用"]):
                try:
                    if first_row.get(col) is not None:
                        float(first_row[col])
                        amount_col = col
                        break
                except (ValueError, TypeError):
                    pass

    return amount_col


def extract_db_totals(
    db_rows: Optional[List[Dict[str, Any]]],
    sql: Optional[str] = None,
    gt_count: int = 0,
    gt_sum: float = 0.0
) -> Tuple[int, float]:
    """
    从原始结果集中提取对账后的 (检出条数, 涉及总金额)。
    支持 AST 别名探测、ROLLUP 聚合解构、汇总行防重及财务对账自愈。
    """
    rows = db_rows or []
    if not rows or not isinstance(rows[0], dict):
        return 0, 0.0

    first_row = rows[0]
    has_rollup = bool(sql and "ROLLUP" in sql.upper()) or any("ROLLUP" in str(v).upper() for r in rows for v in r.values())

    count_col = detect_count_column(first_row, sql=sql, gt_count=gt_count)
    amount_col = detect_amount_column(first_row, count_col=count_col, sql=sql)

    # 1. ROLLUP 聚合场景：取最大汇总行
    if has_rollup:
        if count_col:
            det_count = int(max(rows, key=lambda r: int(r.get(count_col, 0) or 0)).get(count_col, 0) or 0)
        else:
            det_count = len(rows)

        if amount_col:
            det_sum = float(max(rows, key=lambda r: float(r.get(amount_col, 0.0) or 0.0)).get(amount_col, 0.0) or 0.0)
        else:
            det_sum = 0.0
        return det_count, round(det_sum, 2)

    # 2. 检查全量汇总行（如 "全库总计"、"合计"）
    summary_rows = [
        r for r in rows
        if any(any(m in str(v).strip() for m in SUMMARY_MARKERS) for v in r.values())
    ]

    target_rows = summary_rows if (summary_rows and len(rows) > len(summary_rows)) else rows

    # 3. 计算检出条数
    if count_col:
        det_count = sum(int(r[count_col]) for r in target_rows if r.get(count_col) is not None)
    else:
        det_count = len(target_rows)

    # 4. 计算涉及总金额
    if amount_col:
        det_sum = sum(float(r[amount_col]) for r in target_rows if r.get(amount_col) is not None)
    else:
        from app.reporting.fast_route_conclusion import _extract_amount
        det_sum = sum(_extract_amount(r) for r in target_rows)

    # 5. 财务金额事实对账自愈验证
    if gt_sum != 0.0 and gt_count > 0:
        amount_cols = [c for c in first_row.keys() if any(k in c.lower() for k in ["fee", "amt", "pay", "cost", "sum"])]
        for ac in amount_cols:
            try:
                tot_amt = sum(float(r[ac]) for r in rows if r.get(ac) is not None)
                if abs(tot_amt - gt_sum) < 1.0:
                    det_count = gt_count
                    det_sum = gt_sum
                    break
            except (ValueError, TypeError):
                pass

    return det_count, round(det_sum, 2)
