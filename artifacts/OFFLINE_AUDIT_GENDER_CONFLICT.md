# 离线取证案卷: 性别与诊断冲突排查

**规则ID**: `GENDER_CONFLICT`
**取证SQL**: 
```sql

            SELECT psn_no, psn_name, gend, dise_name, medfee_sumamt, setl_time 
            FROM fqz_gz_jzsj_all_ql 
            WHERE (gend = '1' AND (dise_name LIKE '%妇%' OR dise_name LIKE '%阴道%' OR dise_name LIKE '%子宫%' OR dise_name LIKE '%乳腺%'))
               OR (gend = '2' AND (dise_name LIKE '%男%' OR dise_name LIKE '%前列腺%' OR dise_name LIKE '%睾丸%'))
            LIMIT 50
        
```

经过规则对撞，未发现该项违规行为。