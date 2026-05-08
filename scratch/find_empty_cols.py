from app.tools import _execute_audit_sql_logic
sql = """
    SELECT 
        count(), 
        countIf(psn_no != ''), 
        countIf(fixmedins_code != '')
    FROM fqz_gz_jzsj_all_ql
"""
print(_execute_audit_sql_logic(sql))

sql2 = """
    SELECT med_type, count() 
    FROM fqz_gz_jzsj_all_ql 
    GROUP BY med_type
"""
print(_execute_audit_sql_logic(sql2))
