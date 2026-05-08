1. 调用 `audit_medical_rule` 工具，参数设置为 `rule='DECOMPOSITION_HOSPITALIZATION'`, `year=2024`, `days_between=(1, 15)`, `top_n=5`。
2. 对于排名第一的嫌疑人，调用 `execute_audit_sql` 工具，SQL 内容为：
   ```sql
   SELECT psn_no, dise_name, amount
   FROM fqz_gz_jzsj_all_ql
   WHERE psn_no = '排名第一的嫌疑人编号'
     AND YEAR(jz_date) = 2024
     AND jz_type = '住院'
   ORDER BY jz_date;
   ```
3. 生成专项审计简报，包含上述证据链。