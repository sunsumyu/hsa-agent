import json
from app.skills.audit_rules import rule_engine
from app.tools import _execute_audit_sql_logic

sql = rule_engine.get_rule_sql("HIGH_FREQ_DRUG_PURCHASE")
print("SQL:", sql)
res = _execute_audit_sql_logic(sql, return_raw=True)
print("Res length:", len(res))
if len(res) > 0:
    print("First res:", res[0])
else:
    print("No results!")
