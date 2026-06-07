def _is_probe_query(sql: str) -> bool:
    if not sql: return True
    sql_upper = sql.upper().strip()
    # 1. 明显的表结构/元数据探测 (DESCRIBE, SHOW, etc.)
    if any(sql_upper.startswith(x) for x in ["SHOW ", "DESC ", "DESCRIBE ", "EXPLAIN "]):
        return True
    # 2. 简单的计数/边界/总数探测 (无 GROUP BY 且包含 COUNT/MIN/MAX)
    if "JOIN" not in sql_upper and "GROUP BY" not in sql_upper:
        if any(x in sql_upper for x in ["COUNT(*)", "COUNT (", "MIN(SETL_TIME)", "MAX(SETL_TIME)", "MIN (SETL_TIME)", "MAX (SETL_TIME)"]):
            return True
        if sql_upper.startswith("SELECT COUNT"):
            return True
    # 3. 字典/项目/药品/科室的 DISTINCT 列表探测 (主要用于核查项目名称是否存在)
    if "DISTINCT" in sql_upper and "JOIN" not in sql_upper:
        if any(x in sql_upper for x in ["HILIST_NAME", "HILIST_CODE", "OPRN_OPRT_NAME", "DISE_NAME", "MED_TYPE", "ADM_DEPT_NAME", "DSCG_DEPT_NAME", "CHFPDR_NAME"]):
            return True
    # 4. 任何不含 JOIN，且长度较短，且没有特定业务过滤词的 SQL
    if "JOIN" not in sql_upper and len(sql) < 500:
        if not ("HAVING" in sql_upper or "WINDOW" in sql_upper or "OVER" in sql_upper):
            if "GEND" not in sql_upper:
                return True
    # 5. 明显的表结构/元数据探测
    if "LIMIT " in sql_upper and "JOIN" not in sql_upper and "GROUP BY" not in sql_upper and len(sql) < 500:
        return True
    return False

test_sql = "SELECT count(*) AS dialysis_related, countIf(replace(oprn_oprt_name, '\\t', '') LIKE '%透析%' OR replace(dise_name, '\\t', '') LIKE '%肾衰%' OR replace(dise_name, '\\t', '') LIKE '%透析%') AS dialysis_cnt, countIf(replace(oprn_oprt_name, '\\t', '') LIKE '%固定%' OR replace(dise_name, '\\t', '') LIKE '%骨折%' OR replace(dise_name, '\\t', '') LIKE '%脊柱%') AS spine_cnt FROM fqz_gz_jzsj_all_ql WHERE setl_time >= '2024-01-01'"
print("Is Probe:", _is_probe_query(test_sql))
print("Length:", len(test_sql))
print("sql_upper contains COUNT(*):", "COUNT(*)" in test_sql.upper())
