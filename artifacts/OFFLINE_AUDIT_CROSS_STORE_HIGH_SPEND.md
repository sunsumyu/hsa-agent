# 离线取证案卷: 跨药店流窜套高额消费

**规则ID**: `CROSS_STORE_HIGH_SPEND`
**取证SQL**: 
```sql

            SELECT 
                psn_no,
                count(DISTINCT fixmedins_code) as store_count,
                count() as total_purchases,
                sum(medfee_sumamt) as total_amount,
                sum(fund_pay_sumamt) as total_fund_paid
            FROM fqz_gz_jzsj_all_ql
            WHERE med_type = '定点药店购药'
              AND toYear(setl_time) = 2024
            GROUP BY psn_no
            HAVING store_count >= 5 AND total_fund_paid > 5000
            ORDER BY total_fund_paid DESC
            LIMIT 50
        
```

经过规则对撞，未发现该项违规行为。