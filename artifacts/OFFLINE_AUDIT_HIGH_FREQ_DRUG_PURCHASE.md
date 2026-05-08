# 离线取证案卷: 零售药店高频购药异常

**规则ID**: `HIGH_FREQ_DRUG_PURCHASE`
**取证SQL**: 
```sql

            SELECT 
                psn_no, 
                fixmedins_name as drug_store,
                count() as purchase_count,
                min(setl_time) as first_purchase,
                max(setl_time) as last_purchase,
                sum(medfee_sumamt) as total_amount,
                sum(fund_pay_sumamt) as total_fund_paid
            FROM fqz_gz_jzsj_all_ql
            WHERE med_type = '定点药店购药'
              AND toYear(setl_time) = 2024
            GROUP BY psn_no, fixmedins_code, fixmedins_name
            HAVING purchase_count >= 10
            ORDER BY purchase_count DESC
            LIMIT 50
        
```

### 规则对撞详情: HIGH_FREQ_DRUG_PURCHASE

**审计结论**: 发现疑似违规记录 **50** 条，涉及医疗总额 **¥88,775,225.76**。

**前10条证据明细：**

1. psn:52000001**** | drug_store=dσ-�l��o���9�Ĕ | purchase_count=103936 | first_purchase=2024-03-07 19:59:21+08:00 | last_purchase=2024-05-03 09:52:35+08:00 | total_amount=3734272.0000004848 | total_fund_paid=0.0 | 
2. psn:52000001**** | drug_store=�56�Y�G����w}� | purchase_count=74240 | first_purchase=2024-03-08 15:58:23+08:00 | last_purchase=2024-05-09 16:18:52+08:00 | total_amount=6720204.800000749 | total_fund_paid=0.0 | 
3. psn:52000001**** | drug_store=�F�OGwZ����� | purchase_count=64512 | first_purchase=2024-03-09 15:51:45+08:00 | last_purchase=2024-05-09 15:13:33+08:00 | total_amount=2268672.0 | total_fund_paid=0.0 | 
4. psn:52000001**** | drug_store=�*f�[RM�呈n� | purchase_count=59392 | first_purchase=2024-03-16 20:19:02+08:00 | last_purchase=2024-05-08 12:28:06+08:00 | total_amount=5625907.1999979755 | total_fund_paid=0.0 | 
5. psn:52000001**** | drug_store=WՔ�^|`�DE�h�� | purchase_count=59392 | first_purchase=2024-04-04 19:10:46+08:00 | last_purchase=2024-05-04 10:27:44+08:00 | total_amount=4311562.239999174 | total_fund_paid=0.0 | 
6. psn:52000001**** | drug_store=�oP�L0���V��� | purchase_count=53760 | first_purchase=2024-04-03 17:42:59+08:00 | last_purchase=2024-05-07 17:22:04+08:00 | total_amount=2947123.1999997436 | total_fund_paid=0.0 | 
7. psn:52000001**** | drug_store=_��F2���T��]} | purchase_count=53760 | first_purchase=2024-03-15 13:17:04+08:00 | last_purchase=2024-03-17 09:03:17+08:00 | total_amount=4095436.80000105 | total_fund_paid=0.0 | 
8. psn:52000001**** | drug_store=��PuZ~_^�-�M� | purchase_count=43797 | first_purchase=2024-03-28 13:57:06+08:00 | last_purchase=2024-05-04 10:28:30+08:00 | total_amount=3343171.0 | total_fund_paid=0.0 | 
9. psn:52000001**** | drug_store=�]Ȩ*��a�Ζ5�� | purchase_count=39657 | first_purchase=2024-03-06 14:07:14+08:00 | last_purchase=2024-04-15 09:14:05+08:00 | total_amount=5526863.899999911 | total_fund_paid=0.0 | 
10. psn:52000001**** | drug_store=�':i#����{/�6� | purchase_count=39211 | first_purchase=2024-03-07 15:24:41+08:00 | last_purchase=2024-03-28 17:13:10+08:00 | total_amount=1250854.900000243 | total_fund_paid=0.0 | 

*...其余 40 条证据已在物理缓冲区固化。*