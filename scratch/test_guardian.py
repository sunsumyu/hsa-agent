from app.skills.security import SQLGuardian
sql = """
    SELECT 
        psn_no, 
        count() as purchase_count
    FROM fqz_gz_jzsj_all_ql
    WHERE med_type = '零售药店购药'
    GROUP BY psn_no
    ORDER BY purchase_count DESC
    LIMIT 5
"""
safe = SQLGuardian.validate_sql(sql)
lim = SQLGuardian.ensure_limit(safe)
print("Validated:", safe)
print("With limit:", lim)
