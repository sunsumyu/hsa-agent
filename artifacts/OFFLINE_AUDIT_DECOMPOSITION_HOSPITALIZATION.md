# 离线取证案卷: 分解住院/挂床行为检测

**规则ID**: `DECOMPOSITION_HOSPITALIZATION`
**取证SQL**: 
```sql

            SELECT a.psn_no, a.fixmedins_name, a.end_date as discharge_a, b.start_date as admission_b, 
                   dateDiff('day', toDate(a.end_date), toDate(b.start_date)) as interval_days,
                   a.medfee_sumamt as fee_a, b.medfee_sumamt as fee_b,
                   a.dise_name as disease_a, b.dise_name as disease_b
            FROM fqz_gz_jzsj_all_ql AS a
            INNER JOIN fqz_gz_jzsj_all_ql AS b ON a.psn_no = b.psn_no AND a.fixmedins_code = b.fixmedins_code
            WHERE a.setl_id != b.setl_id
              AND b.start_date > a.end_date
              AND dateDiff('day', toDate(a.end_date), toDate(b.start_date)) BETWEEN 1 AND 15
              AND a.med_type NOT LIKE '%药%'
              AND b.med_type NOT LIKE '%药%'
              AND toYear(a.start_date) = 2024
            ORDER BY interval_days ASC
            LIMIT 50
        
```

经过规则对撞，未发现该项违规行为。