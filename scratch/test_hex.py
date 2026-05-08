# -*- coding: utf-8 -*-
from app.tools import _execute_audit_sql_logic
sql = "SELECT hex(med_type), med_type FROM fqz_gz_jzsj_all_ql LIMIT 1"
print("Hex:", _execute_audit_sql_logic(sql))
