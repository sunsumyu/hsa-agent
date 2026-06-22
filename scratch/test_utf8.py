# -*- coding: utf-8 -*-
from app.tools import _execute_audit_sql_logic
sql = "SELECT count() FROM fqz_gz_jzsj_all_ql WHERE med_type = '零售药店购药'"
print("Result of count:", _execute_audit_sql_logic(sql))
