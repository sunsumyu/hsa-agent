# ClickHouse 数据库结构详表

生成时间: 2026-04-11 01:04:15

## 表: `fqz_admdvs`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| admdvs | String | 行政区划编码 |
| admdvs_name | String | 行政区划名称 |
| prnt_admdvs | String | 父级区划编码 |
| admdvs_lv | String | 区划层级 |

### 数据样例 (前3条)

```json
[
  {
    "admdvs": "810000",
    "admdvs_name": "香港特别行政区",
    "prnt_admdvs": "100000",
    "admdvs_lv": "1"
  },
  {
    "admdvs": "820000",
    "admdvs_name": "澳门特别行政区",
    "prnt_admdvs": "100000",
    "admdvs_lv": "1"
  },
  {
    "admdvs": "910000",
    "admdvs_name": "中国人民解放军部队",
    "prnt_admdvs": "100000",
    "admdvs_lv": "1"
  }
]
```

---

## 表: `fqz_all_yy_yd_1`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| fixmedins_code | String | 医疗机构编码 |
| fixmedins_name | String | 医疗机构名称 |
| admdvs | String | 行政区划 |
| medfee_sumamt | Decimal(18, 2) | 医疗费总金额 |
| fund_pay_sumamt | Decimal(18, 2) | 统筹基金支付金额 |
| setl_time | DateTime | 结算时间 (核心审计维) |

### 数据样例 (前3条)

```json
[
  {
    "fixmedins_code": "H001",
    "fixmedins_name": "广州市第一人民医院",
    "admdvs": "440100",
    "medfee_sumamt": "1513.53",
    "fund_pay_sumamt": "1297.73",
    "setl_time": "2026-04-03 10:02:00+08:00"
  },
  {
    "fixmedins_code": "H001",
    "fixmedins_name": "广州市第一人民医院",
    "admdvs": "440100",
    "medfee_sumamt": "1752.03",
    "fund_pay_sumamt": "1276.49",
    "setl_time": "2026-04-10 13:24:00+08:00"
  },
  {
    "fixmedins_code": "H001",
    "fixmedins_name": "广州市第一人民医院",
    "admdvs": "440100",
    "medfee_sumamt": "4752.71",
    "fund_pay_sumamt": "4111.09",
    "setl_time": "2026-04-14 18:29:00+08:00"
  }
]
```

---

## 表: `fqz_cgzhan_hosp`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| timetype | String |  |
| setl_time | String |  |
| fixmedins_code | String |  |
| fixmedins_name | String |  |
| medinslv | String |  |
| hosp_natu_code | String |  |
| fix_blng_admdvs | String |  |
| fix_blng_admdvs_city | String |  |
| totlcnt_psn_no | String |  |
| totlnum_mdtrt_id | String |  |
| sum_medfee_sumamt | Float64 |  |
| sum_hifp_pay | Float64 |  |
| sum_fund_pay_sumamt | Float64 |  |
| sum_acct_pay | Float64 |  |
| sum_cash_payamt | Float64 |  |
| sum_balc | Float64 |  |
| sum_inscp_amt | Float64 |  |
| sum_hi_agre_sumfee | Float64 |  |
| sum_acct_mulaid_pay | Float64 |  |
| sum_bydise_setl_payamt | Float64 |  |
| sum_cvlserv_pay | Float64 |  |
| sum_maf_pay | Float64 |  |
| sum_ipt_days | Float64 |  |
| avg_medfee_sumamt | Float64 |  |
| avgnum_medfee_sumamt | Float64 |  |
| avg_fund_pay_sumamt | Float64 |  |
| avgnum_fund_pay_sumamt | Float64 |  |
| avg_ipt_days | Float64 |  |
| avgnum_ipt_days | Float64 |  |
| prop_totlcnt_num | Float64 |  |
| vix | Float64 |  |
| etl_create_time | DateTime |  |

### 数据样例 (前3条)

```json
[
  {
    "timetype": "halfyearly",
    "setl_time": "2021-01",
    "fixmedins_code": "43010105278",
    "fixmedins_name": "长沙养和医院有限责任公司",
    "medinslv": "2",
    "hosp_natu_code": "99",
    "fix_blng_admdvs": "null",
    "fix_blng_admdvs_city": "430100",
    "totlcnt_psn_no": "5772.94",
    "totlnum_mdtrt_id": "3745.01",
    "sum_medfee_sumamt": "3389.55",
    "sum_hifp_pay": "6707.3",
    "sum_fund_pay_sumamt": "7270.37",
    "sum_acct_pay": "6689.83",
    "sum_cash_payamt": "8982.62",
    "sum_balc": "7095.32",
    "sum_inscp_amt": "9218.33",
    "sum_hi_agre_sumfee": "1946.07",
    "sum_acct_mulaid_pay": "2552.56",
    "sum_bydise_setl_payamt": "4937.47",
    "sum_cvlserv_pay": "1307.57",
    "sum_maf_pay": "2422.08",
    "sum_ipt_days": "7795.15",
    "avg_medfee_sumamt": "1210.03",
    "avgnum_medfee_sumamt": "5505.92",
    "avg_fund_pay_sumamt": "995.29",
    "avgnum_fund_pay_sumamt": "1971.5",
    "avg_ipt_days": "9889.34",
    "avgnum_ipt_days": "2325.87",
    "prop_totlcnt_num": "632.39",
    "vix": "6434.26",
    "etl_create_time": "2024-02-02 15:13:58+08:00"
  },
  {
    "timetype": "halfyearly",
    "setl_time": "2021-01",
    "fixmedins_code": "43010105280",
    "fixmedins_name": "长沙康地医院有限公司",
    "medinslv": "2",
    "hosp_natu_code": "99",
    "fix_blng_admdvs": "null",
    "fix_blng_admdvs_city": "430100",
    "totlcnt_psn_no": "1419.88",
    "totlnum_mdtrt_id": "15.93",
    "sum_medfee_sumamt": "4928.56",
    "sum_hifp_pay": "2665.92",
    "sum_fund_pay_sumamt": "9133.47",
    "sum_acct_pay": "2049.99",
    "sum_cash_payamt": "5282.6",
    "sum_balc": "2783.23",
    "sum_inscp_amt": "9337.65",
    "sum_hi_agre_sumfee": "2479.41",
    "sum_acct_mulaid_pay": "9919.07",
    "sum_bydise_setl_payamt": "2907.01",
    "sum_cvlserv_pay": "6109.4",
    "sum_maf_pay": "5767.25",
    "sum_ipt_days": "4289.92",
    "avg_medfee_sumamt": "4947.66",
    "avgnum_medfee_sumamt": "2618.47",
    "avg_fund_pay_sumamt": "7583.49",
    "avgnum_fund_pay_sumamt": "1980.8",
    "avg_ipt_days": "7395.58",
    "avgnum_ipt_days": "1783.56",
    "prop_totlcnt_num": "5692.66",
    "vix": "213.24",
    "etl_create_time": "2024-02-02 15:13:58+08:00"
  },
  {
    "timetype": "halfyearly",
    "setl_time": "2021-01",
    "fixmedins_code": "43010110005",
    "fixmedins_name": "湖南有色冶金职工医院",
    "medinslv": "2",
    "hosp_natu_code": "99",
    "fix_blng_admdvs": "null",
    "fix_blng_admdvs_city": "430100",
    "totlcnt_psn_no": "8513.01",
    "totlnum_mdtrt_id": "420.68",
    "sum_medfee_sumamt": "5554.66",
    "sum_hifp_pay": "4242.84",
    "sum_fund_pay_sumamt": "5965.1",
    "sum_acct_pay": "2686.95",
    "sum_cash_payamt": "3548.3",
    "sum_balc": "538.91",
    "sum_inscp_amt": "5371.97",
    "sum_hi_agre_sumfee": "593.98",
    "sum_acct_mulaid_pay": "1823.77",
    "sum_bydise_setl_payamt": "9475.09",
    "sum_cvlserv_pay": "6528.05",
    "sum_maf_pay": "1627.09",
    "sum_ipt_days": "2716.82",
    "avg_medfee_sumamt": "4476.12",
    "avgnum_medfee_sumamt": "100.47",
    "avg_fund_pay_sumamt": "6112.17",
    "avgnum_fund_pay_sumamt": "7378.19",
    "avg_ipt_days": "6008.51",
    "avgnum_ipt_days": "9503.27",
    "prop_totlcnt_num": "9855.32",
    "vix": "2817.06",
    "etl_create_time": "2024-02-02 15:13:58+08:00"
  }
]
```

---

## 表: `fqz_cgzhan_hosp_fee`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| timetype | String |  |
| fixmedins_code | String |  |
| fixmedins_name | String |  |
| med_chrgitm_type | String |  |
| setl_time | String |  |
| medinslv | String |  |
| hosp_natu_code | String |  |
| fix_blng_admdvs | String |  |
| fix_blng_admdvs_city | String |  |
| sum_medfee_sumamt | Float64 |  |
| sum_hifp_pay | Float64 |  |
| sum_fund_pay_sumamt | Float64 |  |
| sum_acct_pay | Float64 |  |
| sum_cash_payamt | Float64 |  |
| sum_item_sumamt | Float64 |  |
| sum_item_claa_amt | Float64 |  |
| sum_item_clab_amt | Float64 |  |
| sum_item_ownpay_amt | Float64 |  |
| sum_item_oth_amt | Float64 |  |
| pct_item_sumamt | Float64 |  |
| uyear | String |  |
| uhalfyear | String |  |
| uquarter | String |  |
| umonth | String |  |
| uweek | String |  |
| etl_create_time | Date |  |

### 数据样例 (前3条)

```json
[
  {
    "timetype": "halfyearly",
    "fixmedins_code": "43010105278",
    "fixmedins_name": "长沙养和医院有限责任公司",
    "med_chrgitm_type": "12",
    "setl_time": "2022-01",
    "medinslv": "1",
    "hosp_natu_code": "2",
    "fix_blng_admdvs": "",
    "fix_blng_admdvs_city": "",
    "sum_medfee_sumamt": "94219.65",
    "sum_hifp_pay": "91756.51",
    "sum_fund_pay_sumamt": "50256.73",
    "sum_acct_pay": "86120.68",
    "sum_cash_payamt": "98500.05",
    "sum_item_sumamt": "71213.05",
    "sum_item_claa_amt": "25082.19",
    "sum_item_clab_amt": "82216.07",
    "sum_item_ownpay_amt": "4384.52",
    "sum_item_oth_amt": "12723.64",
    "pct_item_sumamt": "529.62",
    "uyear": "",
    "uhalfyear": "",
    "uquarter": "",
    "umonth": "",
    "uweek": "",
    "etl_create_time": "2022-12-01"
  },
  {
    "timetype": "halfyearly",
    "fixmedins_code": "43010105278",
    "fixmedins_name": "长沙养和医院有限责任公司",
    "med_chrgitm_type": "12",
    "setl_time": "2022-01",
    "medinslv": "3",
    "hosp_natu_code": "2",
    "fix_blng_admdvs": "",
    "fix_blng_admdvs_city": "",
    "sum_medfee_sumamt": "24438.0",
    "sum_hifp_pay": "34423.92",
    "sum_fund_pay_sumamt": "20479.07",
    "sum_acct_pay": "24777.02",
    "sum_cash_payamt": "88164.53",
    "sum_item_sumamt": "65599.79",
    "sum_item_claa_amt": "29669.75",
    "sum_item_clab_amt": "50393.49",
    "sum_item_ownpay_amt": "46225.94",
    "sum_item_oth_amt": "72418.37",
    "pct_item_sumamt": "45825.68",
    "uyear": "",
    "uhalfyear": "",
    "uquarter": "",
    "umonth": "",
    "uweek": "",
    "etl_create_time": "2022-12-01"
  },
  {
    "timetype": "halfyearly",
    "fixmedins_code": "43010105278",
    "fixmedins_name": "长沙养和医院有限责任公司",
    "med_chrgitm_type": "12",
    "setl_time": "2022-01",
    "medinslv": "2",
    "hosp_natu_code": "2",
    "fix_blng_admdvs": "",
    "fix_blng_admdvs_city": "",
    "sum_medfee_sumamt": "19216.66",
    "sum_hifp_pay": "60953.83",
    "sum_fund_pay_sumamt": "81419.47",
    "sum_acct_pay": "4635.82",
    "sum_cash_payamt": "24558.32",
    "sum_item_sumamt": "55896.77",
    "sum_item_claa_amt": "37213.0",
    "sum_item_clab_amt": "53165.23",
    "sum_item_ownpay_amt": "98751.52",
    "sum_item_oth_amt": "22662.24",
    "pct_item_sumamt": "79863.28",
    "uyear": "",
    "uhalfyear": "",
    "uquarter": "",
    "umonth": "",
    "uweek": "",
    "etl_create_time": "2022-12-01"
  }
]
```

---

## 表: `fqz_cgzhan_hosp_tmp`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| timetype | String |  |
| setl_time | String |  |
| fixmedins_code | String |  |
| fixmedins_name | String |  |
| medinslv | String |  |
| hosp_natu_code | String |  |
| fix_blng_admdvs | String |  |
| fix_blng_admdvs_city | String |  |
| totlcnt_psn_no | String |  |
| totlnum_mdtrt_id | String |  |
| sum_medfee_sumamt | Float64 |  |
| sum_hifp_pay | Float64 |  |
| sum_fund_pay_sumamt | Float64 |  |
| sum_acct_pay | Float64 |  |
| sum_cash_payamt | Float64 |  |
| sum_balc | Float64 |  |
| sum_inscp_amt | Float64 |  |
| sum_hi_agre_sumfee | Float64 |  |
| sum_acct_mulaid_pay | Float64 |  |
| sum_bydise_setl_payamt | Float64 |  |
| sum_cvlserv_pay | Float64 |  |
| sum_maf_pay | Float64 |  |
| sum_ipt_days | Float64 |  |
| avg_medfee_sumamt | Float64 |  |
| avgnum_medfee_sumamt | Float64 |  |
| avg_fund_pay_sumamt | Float64 |  |
| avgnum_fund_pay_sumamt | Float64 |  |
| avg_ipt_days | Float64 |  |
| avgnum_ipt_days | Float64 |  |
| prop_totlcnt_num | Float64 |  |
| vix | Float64 |  |
| etl_create_time | DateTime |  |

### 数据样例 (前3条)

```json
[
  {
    "timetype": "halfyearly",
    "setl_time": "2021-01",
    "fixmedins_code": "43010105278",
    "fixmedins_name": "长沙养和医院有限责任公司",
    "medinslv": "2",
    "hosp_natu_code": "99",
    "fix_blng_admdvs": "null",
    "fix_blng_admdvs_city": "430100",
    "totlcnt_psn_no": "5772.94",
    "totlnum_mdtrt_id": "3745.01",
    "sum_medfee_sumamt": "3389.55",
    "sum_hifp_pay": "6707.3",
    "sum_fund_pay_sumamt": "7270.37",
    "sum_acct_pay": "6689.83",
    "sum_cash_payamt": "8982.62",
    "sum_balc": "7095.32",
    "sum_inscp_amt": "9218.33",
    "sum_hi_agre_sumfee": "1946.07",
    "sum_acct_mulaid_pay": "2552.56",
    "sum_bydise_setl_payamt": "4937.47",
    "sum_cvlserv_pay": "1307.57",
    "sum_maf_pay": "2422.08",
    "sum_ipt_days": "7795.15",
    "avg_medfee_sumamt": "1210.03",
    "avgnum_medfee_sumamt": "5505.92",
    "avg_fund_pay_sumamt": "995.29",
    "avgnum_fund_pay_sumamt": "1971.5",
    "avg_ipt_days": "9889.34",
    "avgnum_ipt_days": "2325.87",
    "prop_totlcnt_num": "632.39",
    "vix": "6434.26",
    "etl_create_time": "2024-02-02 15:13:58+08:00"
  },
  {
    "timetype": "halfyearly",
    "setl_time": "2021-01",
    "fixmedins_code": "43010105280",
    "fixmedins_name": "长沙康地医院有限公司",
    "medinslv": "2",
    "hosp_natu_code": "99",
    "fix_blng_admdvs": "null",
    "fix_blng_admdvs_city": "430100",
    "totlcnt_psn_no": "1419.88",
    "totlnum_mdtrt_id": "15.93",
    "sum_medfee_sumamt": "4928.56",
    "sum_hifp_pay": "2665.92",
    "sum_fund_pay_sumamt": "9133.47",
    "sum_acct_pay": "2049.99",
    "sum_cash_payamt": "5282.6",
    "sum_balc": "2783.23",
    "sum_inscp_amt": "9337.65",
    "sum_hi_agre_sumfee": "2479.41",
    "sum_acct_mulaid_pay": "9919.07",
    "sum_bydise_setl_payamt": "2907.01",
    "sum_cvlserv_pay": "6109.4",
    "sum_maf_pay": "5767.25",
    "sum_ipt_days": "4289.92",
    "avg_medfee_sumamt": "4947.66",
    "avgnum_medfee_sumamt": "2618.47",
    "avg_fund_pay_sumamt": "7583.49",
    "avgnum_fund_pay_sumamt": "1980.8",
    "avg_ipt_days": "7395.58",
    "avgnum_ipt_days": "1783.56",
    "prop_totlcnt_num": "5692.66",
    "vix": "213.24",
    "etl_create_time": "2024-02-02 15:13:58+08:00"
  },
  {
    "timetype": "halfyearly",
    "setl_time": "2021-01",
    "fixmedins_code": "43010110005",
    "fixmedins_name": "湖南有色冶金职工医院",
    "medinslv": "2",
    "hosp_natu_code": "99",
    "fix_blng_admdvs": "null",
    "fix_blng_admdvs_city": "430100",
    "totlcnt_psn_no": "8513.01",
    "totlnum_mdtrt_id": "420.68",
    "sum_medfee_sumamt": "5554.66",
    "sum_hifp_pay": "4242.84",
    "sum_fund_pay_sumamt": "5965.1",
    "sum_acct_pay": "2686.95",
    "sum_cash_payamt": "3548.3",
    "sum_balc": "538.91",
    "sum_inscp_amt": "5371.97",
    "sum_hi_agre_sumfee": "593.98",
    "sum_acct_mulaid_pay": "1823.77",
    "sum_bydise_setl_payamt": "9475.09",
    "sum_cvlserv_pay": "6528.05",
    "sum_maf_pay": "1627.09",
    "sum_ipt_days": "2716.82",
    "avg_medfee_sumamt": "4476.12",
    "avgnum_medfee_sumamt": "100.47",
    "avg_fund_pay_sumamt": "6112.17",
    "avgnum_fund_pay_sumamt": "7378.19",
    "avg_ipt_days": "6008.51",
    "avgnum_ipt_days": "9503.27",
    "prop_totlcnt_num": "9855.32",
    "vix": "2817.06",
    "etl_create_time": "2024-02-02 15:13:58+08:00"
  }
]
```

---

## 表: `fqz_cgzhan_tcq`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| timetype | String |  |
| setl_time | String |  |
| admdvs_code | String |  |
| admdvs_name | String |  |
| totalcnt_fixmedins_code | String |  |
| totalcnt_psn_no | String |  |
| totalnum_mdtrt_id | String |  |
| sum_medfee_sumamt | Float64 |  |
| sum_hifp_pay | Float64 |  |
| sum_fund_pay_sumamt | Float64 |  |
| sum_acct_pay | Float64 |  |
| sum_cash_payamt | Float64 |  |
| sum_balc | Float64 |  |
| sum_inscp_amt | Float64 |  |
| sum_hi_agre_sumfee | Float64 |  |
| sum_acct_mulaid_pay | Float64 |  |
| sum_bydise_setl_payamt | Float64 |  |
| sum_cvlserv_pay | Float64 |  |
| sum_maf_pay | Float64 |  |
| sum_ipt_days | Float64 |  |
| avg_medfee_sumamt | Float64 |  |
| avgnum_medfee_sumamt | Float64 |  |
| avg_fund_pay_sumamt | Float64 |  |
| avgnum_fund_pay_sumamt | Float64 |  |
| avg_ipt_days | Float64 |  |
| avgnum_ipt_days | Float64 |  |
| prop_totlcnt_num | Float64 |  |
| vix | Float64 |  |
| etl_create_time | DateTime |  |

### 数据样例 (前3条)

```json
[
  {
    "timetype": "quarterly",
    "setl_time": "2021-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "totalcnt_fixmedins_code": "13425656.66",
    "totalcnt_psn_no": "74320502.60",
    "totalnum_mdtrt_id": "74061568.04",
    "sum_medfee_sumamt": "11333554.08",
    "sum_hifp_pay": "16987778.58",
    "sum_fund_pay_sumamt": "99423888.18",
    "sum_acct_pay": "93492541.98",
    "sum_cash_payamt": "97308614.89",
    "sum_balc": "32101131.69",
    "sum_inscp_amt": "33009929.52",
    "sum_hi_agre_sumfee": "81796643.79",
    "sum_acct_mulaid_pay": "50381671.41",
    "sum_bydise_setl_payamt": "29320617.59",
    "sum_cvlserv_pay": "37744469.18",
    "sum_maf_pay": "70221186.71",
    "sum_ipt_days": "3016419.82",
    "avg_medfee_sumamt": "74907372.64",
    "avgnum_medfee_sumamt": "99628411.03",
    "avg_fund_pay_sumamt": "30104304.55",
    "avgnum_fund_pay_sumamt": "5282675.68",
    "avg_ipt_days": "91945591.49",
    "avgnum_ipt_days": "73066613.1",
    "prop_totlcnt_num": "208465.2",
    "vix": "37450019.89",
    "etl_create_time": "2024-01-19 10:50:32+08:00"
  },
  {
    "timetype": "quarterly",
    "setl_time": "2021-01",
    "admdvs_code": "110000",
    "admdvs_name": "北京市",
    "totalcnt_fixmedins_code": "212339.15",
    "totalcnt_psn_no": "825785.03",
    "totalnum_mdtrt_id": "1382534.73",
    "sum_medfee_sumamt": "385594.13",
    "sum_hifp_pay": "1965923.56",
    "sum_fund_pay_sumamt": "194344.77",
    "sum_acct_pay": "809965.72",
    "sum_cash_payamt": "1918572.2",
    "sum_balc": "741775.8",
    "sum_inscp_amt": "1240690.01",
    "sum_hi_agre_sumfee": "1047102.8",
    "sum_acct_mulaid_pay": "841936.18",
    "sum_bydise_setl_payamt": "769506.87",
    "sum_cvlserv_pay": "412174.32",
    "sum_maf_pay": "1235806.23",
    "sum_ipt_days": "856076.75",
    "avg_medfee_sumamt": "1644414.47",
    "avgnum_medfee_sumamt": "279986.07",
    "avg_fund_pay_sumamt": "839318.78",
    "avgnum_fund_pay_sumamt": "908009.92",
    "avg_ipt_days": "1192392.85",
    "avgnum_ipt_days": "1901067.28",
    "prop_totlcnt_num": "519925.7",
    "vix": "1531164.28",
    "etl_create_time": "2024-01-19 10:50:32+08:00"
  },
  {
    "timetype": "quarterly",
    "setl_time": "2021-01",
    "admdvs_code": "119900",
    "admdvs_name": "北京市市本级",
    "totalcnt_fixmedins_code": "7037.13",
    "totalcnt_psn_no": "7735.17",
    "totalnum_mdtrt_id": "6782.00",
    "sum_medfee_sumamt": "6698.32",
    "sum_hifp_pay": "2313.41",
    "sum_fund_pay_sumamt": "5748.75",
    "sum_acct_pay": "2903.29",
    "sum_cash_payamt": "4084.05",
    "sum_balc": "4336.17",
    "sum_inscp_amt": "7380.55",
    "sum_hi_agre_sumfee": "6034.46",
    "sum_acct_mulaid_pay": "8759.05",
    "sum_bydise_setl_payamt": "3321.29",
    "sum_cvlserv_pay": "624.89",
    "sum_maf_pay": "1486.97",
    "sum_ipt_days": "172.19",
    "avg_medfee_sumamt": "6766.74",
    "avgnum_medfee_sumamt": "2748.57",
    "avg_fund_pay_sumamt": "10.44",
    "avgnum_fund_pay_sumamt": "6120.46",
    "avg_ipt_days": "7531.18",
    "avgnum_ipt_days": "8092.23",
    "prop_totlcnt_num": "6358.53",
    "vix": "9295.03",
    "etl_create_time": "2024-01-19 10:50:32+08:00"
  }
]
```

---

## 表: `fqz_cgzhan_tcq_jzdlb`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| timetype | String |  |
| setl_time | String |  |
| admdvs_code | String |  |
| admdvs_name | String |  |
| mdtrt_type | String |  |
| totalcnt_fixmedins_code | String |  |
| totalcnt_psn_no | String |  |
| totalnum_mdtrt_id | String |  |
| sum_medfee_sumamt | Float64 |  |
| sum_hifp_pay | Float64 |  |
| sum_fund_pay_sumamt | Float64 |  |
| sum_acct_pay | Float64 |  |
| sum_cash_payamt | Float64 |  |
| sum_balc | Float64 |  |
| sum_inscp_amt | Float64 |  |
| sum_hi_agre_sumfee | Float64 |  |
| sum_acct_mulaid_pay | Float64 |  |
| sum_bydise_setl_payamt | Float64 |  |
| sum_cvlserv_pay | Float64 |  |
| sum_maf_pay | Float64 |  |
| sum_ipt_days | Float64 |  |
| avg_medfee_sumamt | Float64 |  |
| avgnum_medfee_sumamt | Float64 |  |
| avg_fund_pay_sumamt | Float64 |  |
| avgnum_fund_pay_sumamt | Float64 |  |
| avg_ipt_days | Float64 |  |
| avgnum_ipt_days | Float64 |  |
| prop_totlcnt_num | Float64 |  |
| vix | Float64 |  |
| etl_create_time | DateTime |  |

### 数据样例 (前3条)

```json
[
  {
    "timetype": "quarterly",
    "setl_time": "2021-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "mdtrt_type": "1",
    "totalcnt_fixmedins_code": "78370143.46",
    "totalcnt_psn_no": "94527722.09",
    "totalnum_mdtrt_id": "53986952.08",
    "sum_medfee_sumamt": "16982122.52",
    "sum_hifp_pay": "8975668.66",
    "sum_fund_pay_sumamt": "21419552.54",
    "sum_acct_pay": "79792501.11",
    "sum_cash_payamt": "57729569.2",
    "sum_balc": "82845098.43",
    "sum_inscp_amt": "20051540.56",
    "sum_hi_agre_sumfee": "89322934.32",
    "sum_acct_mulaid_pay": "89113457.17",
    "sum_bydise_setl_payamt": "88415852.46",
    "sum_cvlserv_pay": "88324299.35",
    "sum_maf_pay": "38109738.3",
    "sum_ipt_days": "42356120.3",
    "avg_medfee_sumamt": "35469704.31",
    "avgnum_medfee_sumamt": "29293113.98",
    "avg_fund_pay_sumamt": "77298564.6",
    "avgnum_fund_pay_sumamt": "92281865.5",
    "avg_ipt_days": "75827052.53",
    "avgnum_ipt_days": "70181212.67",
    "prop_totlcnt_num": "42749874.94",
    "vix": "79235564.04",
    "etl_create_time": "2024-01-24 14:35:43+08:00"
  },
  {
    "timetype": "quarterly",
    "setl_time": "2021-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "mdtrt_type": "2",
    "totalcnt_fixmedins_code": "34462530.63",
    "totalcnt_psn_no": "67219966.90",
    "totalnum_mdtrt_id": "95657844.35",
    "sum_medfee_sumamt": "5897281.87",
    "sum_hifp_pay": "14129839.17",
    "sum_fund_pay_sumamt": "83573560.65",
    "sum_acct_pay": "33232493.37",
    "sum_cash_payamt": "90228367.65",
    "sum_balc": "98788698.62",
    "sum_inscp_amt": "64449934.48",
    "sum_hi_agre_sumfee": "35569910.43",
    "sum_acct_mulaid_pay": "56085026.26",
    "sum_bydise_setl_payamt": "64483104.85",
    "sum_cvlserv_pay": "33164338.28",
    "sum_maf_pay": "48371670.03",
    "sum_ipt_days": "54380455.15",
    "avg_medfee_sumamt": "19821933.21",
    "avgnum_medfee_sumamt": "45922107.0",
    "avg_fund_pay_sumamt": "52826817.54",
    "avgnum_fund_pay_sumamt": "66979621.75",
    "avg_ipt_days": "27628052.65",
    "avgnum_ipt_days": "55423837.71",
    "prop_totlcnt_num": "92135822.55",
    "vix": "61777851.12",
    "etl_create_time": "2024-01-24 14:35:43+08:00"
  },
  {
    "timetype": "quarterly",
    "setl_time": "2021-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "mdtrt_type": "3",
    "totalcnt_fixmedins_code": "6398751.25",
    "totalcnt_psn_no": "81851374.79",
    "totalnum_mdtrt_id": "6704147.35",
    "sum_medfee_sumamt": "73548051.25",
    "sum_hifp_pay": "16573780.69",
    "sum_fund_pay_sumamt": "56234240.7",
    "sum_acct_pay": "27807576.28",
    "sum_cash_payamt": "23333101.07",
    "sum_balc": "90466754.77",
    "sum_inscp_amt": "98941557.94",
    "sum_hi_agre_sumfee": "44861740.96",
    "sum_acct_mulaid_pay": "54886997.89",
    "sum_bydise_setl_payamt": "57918999.7",
    "sum_cvlserv_pay": "57098040.43",
    "sum_maf_pay": "15941802.7",
    "sum_ipt_days": "11122978.42",
    "avg_medfee_sumamt": "30278522.33",
    "avgnum_medfee_sumamt": "65591652.33",
    "avg_fund_pay_sumamt": "96604351.98",
    "avgnum_fund_pay_sumamt": "4832051.76",
    "avg_ipt_days": "35943379.71",
    "avgnum_ipt_days": "38913275.58",
    "prop_totlcnt_num": "11305407.36",
    "vix": "16345464.7",
    "etl_create_time": "2024-01-24 14:35:43+08:00"
  }
]
```

---

## 表: `fqz_cgzhan_tcq_xzlb`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| timetype | String |  |
| setl_time | String |  |
| admdvs_code | String |  |
| admdvs_name | String |  |
| insutype | String |  |
| totalcnt_fixmedins_code | String |  |
| totalcnt_psn_no | String |  |
| totalnum_mdtrt_id | String |  |
| sum_medfee_sumamt | Float64 |  |
| sum_hifp_pay | Float64 |  |
| sum_fund_pay_sumamt | Float64 |  |
| sum_acct_pay | Float64 |  |
| sum_cash_payamt | Float64 |  |
| sum_balc | Float64 |  |
| sum_inscp_amt | Float64 |  |
| sum_hi_agre_sumfee | Float64 |  |
| sum_acct_mulaid_pay | Float64 |  |
| sum_bydise_setl_payamt | Float64 |  |
| sum_cvlserv_pay | Float64 |  |
| sum_maf_pay | Float64 |  |
| sum_ipt_days | Float64 |  |
| avg_medfee_sumamt | Float64 |  |
| avgnum_medfee_sumamt | Float64 |  |
| avg_fund_pay_sumamt | Float64 |  |
| avgnum_fund_pay_sumamt | Float64 |  |
| avg_ipt_days | Float64 |  |
| avgnum_ipt_days | Float64 |  |
| prop_totlcnt_num | Float64 |  |
| vix | Float64 |  |
| etl_create_time | String |  |

### 数据样例 (前3条)

```json
[
  {
    "timetype": "halfyearly",
    "setl_time": "2022-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "insutype": "2",
    "totalcnt_fixmedins_code": "74869",
    "totalcnt_psn_no": "771546",
    "totalnum_mdtrt_id": "75152",
    "sum_medfee_sumamt": "919177460.15",
    "sum_hifp_pay": "773231581.76",
    "sum_fund_pay_sumamt": "751120433.17",
    "sum_acct_pay": "691877858.94",
    "sum_cash_payamt": "617777884.28",
    "sum_balc": "809951137.34",
    "sum_inscp_amt": "841664325.19",
    "sum_hi_agre_sumfee": "648513225.67",
    "sum_acct_mulaid_pay": "681654055.3",
    "sum_bydise_setl_payamt": "960815248.07",
    "sum_cvlserv_pay": "587967632.63",
    "sum_maf_pay": "855669317.13",
    "sum_ipt_days": "947058397.29",
    "avg_medfee_sumamt": "854428473.47",
    "avgnum_medfee_sumamt": "742537744.33",
    "avg_fund_pay_sumamt": "641176095.97",
    "avgnum_fund_pay_sumamt": "669367896.38",
    "avg_ipt_days": "520810270.67",
    "avgnum_ipt_days": "938019909.34",
    "prop_totlcnt_num": "584577889.35",
    "vix": "882205162.97",
    "etl_create_time": ""
  },
  {
    "timetype": "halfyearly",
    "setl_time": "2022-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "insutype": "1",
    "totalcnt_fixmedins_code": "98424",
    "totalcnt_psn_no": "803463",
    "totalnum_mdtrt_id": "72604",
    "sum_medfee_sumamt": "917974343.22",
    "sum_hifp_pay": "709899479.12",
    "sum_fund_pay_sumamt": "749243654.98",
    "sum_acct_pay": "614357152.65",
    "sum_cash_payamt": "858004098.04",
    "sum_balc": "692963218.86",
    "sum_inscp_amt": "871243636.49",
    "sum_hi_agre_sumfee": "1011901761.02",
    "sum_acct_mulaid_pay": "959638260.68",
    "sum_bydise_setl_payamt": "674422465.03",
    "sum_cvlserv_pay": "855527767.73",
    "sum_maf_pay": "910523393.65",
    "sum_ipt_days": "816812606.25",
    "avg_medfee_sumamt": "896521838.47",
    "avgnum_medfee_sumamt": "692842252.29",
    "avg_fund_pay_sumamt": "831936966.43",
    "avgnum_fund_pay_sumamt": "875861756.88",
    "avg_ipt_days": "678848000.8",
    "avgnum_ipt_days": "699958312.57",
    "prop_totlcnt_num": "638917551.46",
    "vix": "1067766436.97",
    "etl_create_time": ""
  },
  {
    "timetype": "halfyearly",
    "setl_time": "2022-01",
    "admdvs_code": "110000",
    "admdvs_name": "北京市",
    "insutype": "2",
    "totalcnt_fixmedins_code": "81520",
    "totalcnt_psn_no": "629639",
    "totalnum_mdtrt_id": "70668",
    "sum_medfee_sumamt": "80588619.78",
    "sum_hifp_pay": "72265390.79",
    "sum_fund_pay_sumamt": "77195573.42",
    "sum_acct_pay": "77030443.85",
    "sum_cash_payamt": "73494021.52",
    "sum_balc": "76738064.85",
    "sum_inscp_amt": "90456617.06",
    "sum_hi_agre_sumfee": "67682528.1",
    "sum_acct_mulaid_pay": "64924801.17",
    "sum_bydise_setl_payamt": "74819554.22",
    "sum_cvlserv_pay": "102181925.33",
    "sum_maf_pay": "87567417.18",
    "sum_ipt_days": "61830945.28",
    "avg_medfee_sumamt": "67311765.85",
    "avgnum_medfee_sumamt": "59092524.86",
    "avg_fund_pay_sumamt": "75279373.63",
    "avgnum_fund_pay_sumamt": "84279616.55",
    "avg_ipt_days": "75735681.6",
    "avgnum_ipt_days": "55182754.33",
    "prop_totlcnt_num": "91229189.69",
    "vix": "89322578.63",
    "etl_create_time": ""
  }
]
```

---

## 表: `fqz_cgzhan_tcq_xzlb_jzdlb`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| timetype | String |  |
| setl_time | String |  |
| admdvs_code | String |  |
| admdvs_name | String |  |
| insutype | String |  |
| mdtrt_type | String |  |
| totalcnt_fixmedins_code | String |  |
| totalcnt_psn_no | String |  |
| totalnum_mdtrt_id | String |  |
| sum_medfee_sumamt | Float64 |  |
| sum_hifp_pay | Float64 |  |
| sum_fund_pay_sumamt | Float64 |  |
| sum_acct_pay | Float64 |  |
| sum_cash_payamt | Float64 |  |
| sum_balc | Float64 |  |
| sum_inscp_amt | Float64 |  |
| sum_hi_agre_sumfee | Float64 |  |
| sum_acct_mulaid_pay | Float64 |  |
| sum_bydise_setl_payamt | Float64 |  |
| sum_cvlserv_pay | Float64 |  |
| sum_maf_pay | Float64 |  |
| sum_ipt_days | Float64 |  |
| avg_medfee_sumamt | Float64 |  |
| avgnum_medfee_sumamt | Float64 |  |
| avg_fund_pay_sumamt | Float64 |  |
| avgnum_fund_pay_sumamt | Float64 |  |
| avg_ipt_days | Float64 |  |
| avgnum_ipt_days | Float64 |  |
| prop_totlcnt_num | Float64 |  |
| vix | Float64 |  |
| etl_create_time | String |  |

### 数据样例 (前3条)

```json
[
  {
    "timetype": "halfyearly",
    "setl_time": "2022-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "insutype": "2",
    "mdtrt_type": "310",
    "totalcnt_fixmedins_code": "74869",
    "totalcnt_psn_no": "771546",
    "totalnum_mdtrt_id": "75152",
    "sum_medfee_sumamt": "919177460.15",
    "sum_hifp_pay": "773231581.76",
    "sum_fund_pay_sumamt": "751120433.17",
    "sum_acct_pay": "691877858.94",
    "sum_cash_payamt": "617777884.28",
    "sum_balc": "809951137.34",
    "sum_inscp_amt": "841664325.19",
    "sum_hi_agre_sumfee": "648513225.67",
    "sum_acct_mulaid_pay": "681654055.3",
    "sum_bydise_setl_payamt": "960815248.07",
    "sum_cvlserv_pay": "587967632.63",
    "sum_maf_pay": "855669317.13",
    "sum_ipt_days": "947058397.29",
    "avg_medfee_sumamt": "854428473.47",
    "avgnum_medfee_sumamt": "742537744.33",
    "avg_fund_pay_sumamt": "641176095.97",
    "avgnum_fund_pay_sumamt": "669367896.38",
    "avg_ipt_days": "520810270.67",
    "avgnum_ipt_days": "938019909.34",
    "prop_totlcnt_num": "584577889.35",
    "vix": "882205162.97",
    "etl_create_time": ""
  },
  {
    "timetype": "halfyearly",
    "setl_time": "2022-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "insutype": "1",
    "mdtrt_type": "310",
    "totalcnt_fixmedins_code": "98424",
    "totalcnt_psn_no": "803463",
    "totalnum_mdtrt_id": "72604",
    "sum_medfee_sumamt": "917974343.22",
    "sum_hifp_pay": "709899479.12",
    "sum_fund_pay_sumamt": "749243654.98",
    "sum_acct_pay": "614357152.65",
    "sum_cash_payamt": "858004098.04",
    "sum_balc": "692963218.86",
    "sum_inscp_amt": "871243636.49",
    "sum_hi_agre_sumfee": "1011901761.02",
    "sum_acct_mulaid_pay": "959638260.68",
    "sum_bydise_setl_payamt": "674422465.03",
    "sum_cvlserv_pay": "855527767.73",
    "sum_maf_pay": "910523393.65",
    "sum_ipt_days": "816812606.25",
    "avg_medfee_sumamt": "896521838.47",
    "avgnum_medfee_sumamt": "692842252.29",
    "avg_fund_pay_sumamt": "831936966.43",
    "avgnum_fund_pay_sumamt": "875861756.88",
    "avg_ipt_days": "678848000.8",
    "avgnum_ipt_days": "699958312.57",
    "prop_totlcnt_num": "638917551.46",
    "vix": "1067766436.97",
    "etl_create_time": ""
  },
  {
    "timetype": "halfyearly",
    "setl_time": "2022-01",
    "admdvs_code": "110000",
    "admdvs_name": "北京市",
    "insutype": "2",
    "mdtrt_type": "310",
    "totalcnt_fixmedins_code": "81520",
    "totalcnt_psn_no": "629639",
    "totalnum_mdtrt_id": "70668",
    "sum_medfee_sumamt": "80588619.78",
    "sum_hifp_pay": "72265390.79",
    "sum_fund_pay_sumamt": "77195573.42",
    "sum_acct_pay": "77030443.85",
    "sum_cash_payamt": "73494021.52",
    "sum_balc": "76738064.85",
    "sum_inscp_amt": "90456617.06",
    "sum_hi_agre_sumfee": "67682528.1",
    "sum_acct_mulaid_pay": "64924801.17",
    "sum_bydise_setl_payamt": "74819554.22",
    "sum_cvlserv_pay": "102181925.33",
    "sum_maf_pay": "87567417.18",
    "sum_ipt_days": "61830945.28",
    "avg_medfee_sumamt": "67311765.85",
    "avgnum_medfee_sumamt": "59092524.86",
    "avg_fund_pay_sumamt": "75279373.63",
    "avgnum_fund_pay_sumamt": "84279616.55",
    "avg_ipt_days": "75735681.6",
    "avgnum_ipt_days": "55182754.33",
    "prop_totlcnt_num": "91229189.69",
    "vix": "89322578.63",
    "etl_create_time": ""
  }
]
```

---

## 表: `fqz_cgzhan_tcq_yydj`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| timetype | String |  |
| setl_time | String |  |
| admdvs_code | String |  |
| admdvs_name | String |  |
| medinslv | String |  |
| totalcnt_fixmedins_code | String |  |
| totalcnt_psn_no | String |  |
| totalnum_mdtrt_id | String |  |
| sum_medfee_sumamt | Float64 |  |
| sum_hifp_pay | Float64 |  |
| sum_fund_pay_sumamt | Float64 |  |
| sum_acct_pay | Float64 |  |
| sum_cash_payamt | Float64 |  |
| sum_balc | Float64 |  |
| sum_inscp_amt | Float64 |  |
| sum_hi_agre_sumfee | Float64 |  |
| sum_acct_mulaid_pay | Float64 |  |
| sum_bydise_setl_payamt | Float64 |  |
| sum_cvlserv_pay | Float64 |  |
| sum_maf_pay | Float64 |  |
| sum_ipt_days | Float64 |  |
| avg_medfee_sumamt | Float64 |  |
| avgnum_medfee_sumamt | Float64 |  |
| avg_fund_pay_sumamt | Float64 |  |
| avgnum_fund_pay_sumamt | Float64 |  |
| avg_ipt_days | Float64 |  |
| avgnum_ipt_days | Float64 |  |
| prop_totlcnt_num | Float64 |  |
| vix | Float64 |  |
| etl_create_time | DateTime |  |

### 数据样例 (前3条)

```json
[
  {
    "timetype": "quarterly",
    "setl_time": "2021-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "medinslv": "1",
    "totalcnt_fixmedins_code": "95695805.42",
    "totalcnt_psn_no": "54258818.36",
    "totalnum_mdtrt_id": "41279017.95",
    "sum_medfee_sumamt": "37837302.37",
    "sum_hifp_pay": "35584435.88",
    "sum_fund_pay_sumamt": "81705972.47",
    "sum_acct_pay": "27971845.64",
    "sum_cash_payamt": "47156053.62",
    "sum_balc": "53513603.37",
    "sum_inscp_amt": "88629142.38",
    "sum_hi_agre_sumfee": "50382092.95",
    "sum_acct_mulaid_pay": "88791525.63",
    "sum_bydise_setl_payamt": "66294506.33",
    "sum_cvlserv_pay": "40698546.02",
    "sum_maf_pay": "44361095.24",
    "sum_ipt_days": "99590711.31",
    "avg_medfee_sumamt": "11813327.7",
    "avgnum_medfee_sumamt": "19017434.86",
    "avg_fund_pay_sumamt": "86330216.27",
    "avgnum_fund_pay_sumamt": "45478807.16",
    "avg_ipt_days": "67257174.96",
    "avgnum_ipt_days": "60989143.96",
    "prop_totlcnt_num": "22707157.26",
    "vix": "11339823.33",
    "etl_create_time": "2024-01-19 15:37:31+08:00"
  },
  {
    "timetype": "quarterly",
    "setl_time": "2021-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "medinslv": "2",
    "totalcnt_fixmedins_code": "50675210.63",
    "totalcnt_psn_no": "65960519.58",
    "totalnum_mdtrt_id": "82515227.42",
    "sum_medfee_sumamt": "36333652.85",
    "sum_hifp_pay": "63107886.24",
    "sum_fund_pay_sumamt": "74261197.97",
    "sum_acct_pay": "81899054.75",
    "sum_cash_payamt": "76473547.08",
    "sum_balc": "22547285.81",
    "sum_inscp_amt": "35481279.93",
    "sum_hi_agre_sumfee": "9763663.53",
    "sum_acct_mulaid_pay": "12114639.36",
    "sum_bydise_setl_payamt": "82289846.31",
    "sum_cvlserv_pay": "25708880.5",
    "sum_maf_pay": "26502993.9",
    "sum_ipt_days": "24325848.93",
    "avg_medfee_sumamt": "90933787.53",
    "avgnum_medfee_sumamt": "47741251.2",
    "avg_fund_pay_sumamt": "55756102.64",
    "avgnum_fund_pay_sumamt": "99250859.54",
    "avg_ipt_days": "89089246.27",
    "avgnum_ipt_days": "32348640.42",
    "prop_totlcnt_num": "71343715.8",
    "vix": "82759478.35",
    "etl_create_time": "2024-01-24 14:24:27+08:00"
  },
  {
    "timetype": "quarterly",
    "setl_time": "2021-01",
    "admdvs_code": "110000",
    "admdvs_name": "北京市",
    "medinslv": "1",
    "totalcnt_fixmedins_code": "670807.08",
    "totalcnt_psn_no": "700824.10",
    "totalnum_mdtrt_id": "1578081.56",
    "sum_medfee_sumamt": "703306.95",
    "sum_hifp_pay": "1197455.55",
    "sum_fund_pay_sumamt": "399633.09",
    "sum_acct_pay": "674961.44",
    "sum_cash_payamt": "696554.77",
    "sum_balc": "773175.92",
    "sum_inscp_amt": "802217.63",
    "sum_hi_agre_sumfee": "1566468.03",
    "sum_acct_mulaid_pay": "1261879.84",
    "sum_bydise_setl_payamt": "553821.74",
    "sum_cvlserv_pay": "13192.42",
    "sum_maf_pay": "1581811.61",
    "sum_ipt_days": "703338.38",
    "avg_medfee_sumamt": "323859.33",
    "avgnum_medfee_sumamt": "1649824.79",
    "avg_fund_pay_sumamt": "757295.19",
    "avgnum_fund_pay_sumamt": "1180151.98",
    "avg_ipt_days": "56621.4",
    "avgnum_ipt_days": "295640.06",
    "prop_totlcnt_num": "50204.27",
    "vix": "95110.17",
    "etl_create_time": "2024-01-19 15:37:31+08:00"
  }
]
```

---

## 表: `fqz_cgzhan_tcq_yydj_jzdlb`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| timetype | String |  |
| setl_time | String |  |
| admdvs_code | String |  |
| admdvs_name | String |  |
| medinslv | String |  |
| mdtrt_type | String |  |
| totalcnt_fixmedins_code | String |  |
| totalcnt_psn_no | String |  |
| totalnum_mdtrt_id | String |  |
| sum_medfee_sumamt | Float64 |  |
| sum_hifp_pay | Float64 |  |
| sum_fund_pay_sumamt | Float64 |  |
| sum_acct_pay | Float64 |  |
| sum_cash_payamt | Float64 |  |
| sum_balc | Float64 |  |
| sum_inscp_amt | Float64 |  |
| sum_hi_agre_sumfee | Float64 |  |
| sum_acct_mulaid_pay | Float64 |  |
| sum_bydise_setl_payamt | Float64 |  |
| sum_cvlserv_pay | Float64 |  |
| sum_maf_pay | Float64 |  |
| sum_ipt_days | Float64 |  |
| avg_medfee_sumamt | Float64 |  |
| avgnum_medfee_sumamt | Float64 |  |
| avg_fund_pay_sumamt | Float64 |  |
| avgnum_fund_pay_sumamt | Float64 |  |
| avg_ipt_days | Float64 |  |
| avgnum_ipt_days | Float64 |  |
| prop_totlcnt_num | Float64 |  |
| vix | Float64 |  |
| etl_create_time | DateTime |  |

### 数据样例 (前3条)

```json
[
  {
    "timetype": "quarterly",
    "setl_time": "2021-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "medinslv": "1",
    "mdtrt_type": "1",
    "totalcnt_fixmedins_code": "79533442.76",
    "totalcnt_psn_no": "57129260.98",
    "totalnum_mdtrt_id": "20287501.08",
    "sum_medfee_sumamt": "63858399.34",
    "sum_hifp_pay": "58664621.86",
    "sum_fund_pay_sumamt": "70584207.65",
    "sum_acct_pay": "20842235.45",
    "sum_cash_payamt": "68054660.68",
    "sum_balc": "91282474.9",
    "sum_inscp_amt": "37115708.65",
    "sum_hi_agre_sumfee": "2618654.04",
    "sum_acct_mulaid_pay": "68623333.89",
    "sum_bydise_setl_payamt": "9663003.62",
    "sum_cvlserv_pay": "75932308.12",
    "sum_maf_pay": "64715989.44",
    "sum_ipt_days": "35396972.13",
    "avg_medfee_sumamt": "79302147.26",
    "avgnum_medfee_sumamt": "62991257.66",
    "avg_fund_pay_sumamt": "28045021.57",
    "avgnum_fund_pay_sumamt": "50948375.13",
    "avg_ipt_days": "39346707.97",
    "avgnum_ipt_days": "48114101.07",
    "prop_totlcnt_num": "67141253.67",
    "vix": "61442651.24",
    "etl_create_time": "2024-01-25 14:17:11+08:00"
  },
  {
    "timetype": "quarterly",
    "setl_time": "2021-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "medinslv": "2",
    "mdtrt_type": "1",
    "totalcnt_fixmedins_code": "98391432.06",
    "totalcnt_psn_no": "3338869.68",
    "totalnum_mdtrt_id": "91767293.20",
    "sum_medfee_sumamt": "71283075.79",
    "sum_hifp_pay": "15436331.39",
    "sum_fund_pay_sumamt": "91092251.9",
    "sum_acct_pay": "26814870.86",
    "sum_cash_payamt": "11132170.12",
    "sum_balc": "37285076.65",
    "sum_inscp_amt": "30390899.57",
    "sum_hi_agre_sumfee": "86541087.77",
    "sum_acct_mulaid_pay": "28423044.32",
    "sum_bydise_setl_payamt": "77316636.85",
    "sum_cvlserv_pay": "21264311.58",
    "sum_maf_pay": "5542433.36",
    "sum_ipt_days": "97083722.22",
    "avg_medfee_sumamt": "25596291.4",
    "avgnum_medfee_sumamt": "83354315.53",
    "avg_fund_pay_sumamt": "96785159.39",
    "avgnum_fund_pay_sumamt": "56427088.49",
    "avg_ipt_days": "68758670.06",
    "avgnum_ipt_days": "12965580.14",
    "prop_totlcnt_num": "9983626.24",
    "vix": "58181777.76",
    "etl_create_time": "2024-01-25 14:17:11+08:00"
  },
  {
    "timetype": "quarterly",
    "setl_time": "2021-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "medinslv": "3",
    "mdtrt_type": "1",
    "totalcnt_fixmedins_code": "33795872.08",
    "totalcnt_psn_no": "84328775.49",
    "totalnum_mdtrt_id": "17180859.10",
    "sum_medfee_sumamt": "39129674.23",
    "sum_hifp_pay": "20983125.93",
    "sum_fund_pay_sumamt": "89891889.2",
    "sum_acct_pay": "85241397.68",
    "sum_cash_payamt": "17129928.09",
    "sum_balc": "10716291.78",
    "sum_inscp_amt": "27178640.66",
    "sum_hi_agre_sumfee": "12058003.5",
    "sum_acct_mulaid_pay": "66572983.56",
    "sum_bydise_setl_payamt": "98265083.2",
    "sum_cvlserv_pay": "76480296.81",
    "sum_maf_pay": "77491234.92",
    "sum_ipt_days": "94049875.1",
    "avg_medfee_sumamt": "30791708.89",
    "avgnum_medfee_sumamt": "87150069.64",
    "avg_fund_pay_sumamt": "48015731.47",
    "avgnum_fund_pay_sumamt": "67627481.21",
    "avg_ipt_days": "59469233.55",
    "avgnum_ipt_days": "41824892.63",
    "prop_totlcnt_num": "46478178.42",
    "vix": "90575792.11",
    "etl_create_time": "2024-01-25 14:17:11+08:00"
  }
]
```

---

## 表: `fqz_cgzhan_tcq_yydj_xzlb`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| timetype | String |  |
| setl_time | String |  |
| admdvs_code | String |  |
| admdvs_name | String |  |
| insutype | String |  |
| medinslv | String |  |
| totalcnt_fixmedins_code | String |  |
| totalcnt_psn_no | String |  |
| totalnum_mdtrt_id | String |  |
| sum_medfee_sumamt | Float64 |  |
| sum_hifp_pay | Float64 |  |
| sum_fund_pay_sumamt | Float64 |  |
| sum_acct_pay | Float64 |  |
| sum_cash_payamt | Float64 |  |
| sum_balc | Float64 |  |
| sum_inscp_amt | Float64 |  |
| sum_hi_agre_sumfee | Float64 |  |
| sum_acct_mulaid_pay | Float64 |  |
| sum_bydise_setl_payamt | Float64 |  |
| sum_cvlserv_pay | Float64 |  |
| sum_maf_pay | Float64 |  |
| sum_ipt_days | Float64 |  |
| avg_medfee_sumamt | Float64 |  |
| avgnum_medfee_sumamt | Float64 |  |
| avg_fund_pay_sumamt | Float64 |  |
| avgnum_fund_pay_sumamt | Float64 |  |
| avg_ipt_days | Float64 |  |
| avgnum_ipt_days | Float64 |  |
| prop_totlcnt_num | Float64 |  |
| vix | Float64 |  |
| etl_create_time | String |  |

### 数据样例 (前3条)

```json
[
  {
    "timetype": "halfyearly",
    "setl_time": "2022-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "insutype": "2",
    "medinslv": "3",
    "totalcnt_fixmedins_code": "20113",
    "totalcnt_psn_no": "241262",
    "totalnum_mdtrt_id": "21343",
    "sum_medfee_sumamt": "177103813.57",
    "sum_hifp_pay": "219739509.01",
    "sum_fund_pay_sumamt": "247344649.86",
    "sum_acct_pay": "189998103.65",
    "sum_cash_payamt": "98411807.1",
    "sum_balc": "235258350.6",
    "sum_inscp_amt": "134707162.0",
    "sum_hi_agre_sumfee": "167400472.56",
    "sum_acct_mulaid_pay": "199145517.14",
    "sum_bydise_setl_payamt": "254708890.21",
    "sum_cvlserv_pay": "172452577.74",
    "sum_maf_pay": "175219162.82",
    "sum_ipt_days": "185767857.54",
    "avg_medfee_sumamt": "215205855.66",
    "avgnum_medfee_sumamt": "221289039.68",
    "avg_fund_pay_sumamt": "185583268.05",
    "avgnum_fund_pay_sumamt": "138153039.47",
    "avg_ipt_days": "81696302.73",
    "avgnum_ipt_days": "220595625.94",
    "prop_totlcnt_num": "102892228.7",
    "vix": "229618658.73",
    "etl_create_time": ""
  },
  {
    "timetype": "halfyearly",
    "setl_time": "2022-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "insutype": "1",
    "medinslv": "9",
    "totalcnt_fixmedins_code": "21352",
    "totalcnt_psn_no": "240877",
    "totalnum_mdtrt_id": "18115",
    "sum_medfee_sumamt": "197067969.64",
    "sum_hifp_pay": "169010963.97",
    "sum_fund_pay_sumamt": "237790109.01",
    "sum_acct_pay": "208330769.1",
    "sum_cash_payamt": "156280256.25",
    "sum_balc": "174137226.0",
    "sum_inscp_amt": "236752722.18",
    "sum_hi_agre_sumfee": "255901578.74",
    "sum_acct_mulaid_pay": "213650529.08",
    "sum_bydise_setl_payamt": "124465737.65",
    "sum_cvlserv_pay": "240995093.75",
    "sum_maf_pay": "210605876.21",
    "sum_ipt_days": "244816283.86",
    "avg_medfee_sumamt": "280407083.62",
    "avgnum_medfee_sumamt": "164626534.4",
    "avg_fund_pay_sumamt": "200474073.49",
    "avgnum_fund_pay_sumamt": "195354556.19",
    "avg_ipt_days": "215490388.94",
    "avgnum_ipt_days": "125634519.58",
    "prop_totlcnt_num": "200599921.4",
    "vix": "265058291.79",
    "etl_create_time": ""
  },
  {
    "timetype": "halfyearly",
    "setl_time": "2022-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "insutype": "2",
    "medinslv": "2",
    "totalcnt_fixmedins_code": "19054",
    "totalcnt_psn_no": "187932",
    "totalnum_mdtrt_id": "18572",
    "sum_medfee_sumamt": "307463485.08",
    "sum_hifp_pay": "206125372.04",
    "sum_fund_pay_sumamt": "217365663.27",
    "sum_acct_pay": "212212371.43",
    "sum_cash_payamt": "98120706.9",
    "sum_balc": "228735599.46",
    "sum_inscp_amt": "196342280.58",
    "sum_hi_agre_sumfee": "103349356.77",
    "sum_acct_mulaid_pay": "175445408.1",
    "sum_bydise_setl_payamt": "247155760.51",
    "sum_cvlserv_pay": "85654592.0",
    "sum_maf_pay": "224349873.51",
    "sum_ipt_days": "254981610.34",
    "avg_medfee_sumamt": "113506285.27",
    "avgnum_medfee_sumamt": "192234096.99",
    "avg_fund_pay_sumamt": "118379377.63",
    "avgnum_fund_pay_sumamt": "131417078.95",
    "avg_ipt_days": "178484758.19",
    "avgnum_ipt_days": "280430024.61",
    "prop_totlcnt_num": "214746714.57",
    "vix": "108319730.57",
    "etl_create_time": ""
  }
]
```

---

## 表: `fqz_cgzhan_tcq_yydj_yyxz`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| timetype | String |  |
| setl_time | String |  |
| admdvs_code | String |  |
| admdvs_name | String |  |
| medinslv | String |  |
| hosp_natu_code | String |  |
| totalcnt_fixmedins_code | String |  |
| totalcnt_psn_no | String |  |
| totalnum_mdtrt_id | String |  |
| sum_medfee_sumamt | Float64 |  |
| sum_hifp_pay | Float64 |  |
| sum_fund_pay_sumamt | Float64 |  |
| sum_acct_pay | Float64 |  |
| sum_cash_payamt | Float64 |  |
| sum_balc | Float64 |  |
| sum_inscp_amt | Float64 |  |
| sum_hi_agre_sumfee | Float64 |  |
| sum_acct_mulaid_pay | Float64 |  |
| sum_bydise_setl_payamt | Float64 |  |
| sum_cvlserv_pay | Float64 |  |
| sum_maf_pay | Float64 |  |
| sum_ipt_days | Float64 |  |
| avg_medfee_sumamt | Float64 |  |
| avgnum_medfee_sumamt | Float64 |  |
| avg_fund_pay_sumamt | Float64 |  |
| avgnum_fund_pay_sumamt | Float64 |  |
| avg_ipt_days | Float64 |  |
| avgnum_ipt_days | Float64 |  |
| prop_totlcnt_num | Float64 |  |
| vix | Float64 |  |
| etl_create_time | DateTime |  |

### 数据样例 (前3条)

```json
[
  {
    "timetype": "quarterly",
    "setl_time": "2021-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "medinslv": "1",
    "hosp_natu_code": "2",
    "totalcnt_fixmedins_code": "9567117.58",
    "totalcnt_psn_no": "91318189.74",
    "totalnum_mdtrt_id": "67374184.37",
    "sum_medfee_sumamt": "39174106.52",
    "sum_hifp_pay": "86451296.83",
    "sum_fund_pay_sumamt": "36918241.93",
    "sum_acct_pay": "77123218.96",
    "sum_cash_payamt": "81283331.24",
    "sum_balc": "4414943.22",
    "sum_inscp_amt": "6658172.63",
    "sum_hi_agre_sumfee": "44317457.69",
    "sum_acct_mulaid_pay": "58962508.63",
    "sum_bydise_setl_payamt": "46865645.47",
    "sum_cvlserv_pay": "83199301.8",
    "sum_maf_pay": "83851197.09",
    "sum_ipt_days": "72712417.57",
    "avg_medfee_sumamt": "25833436.88",
    "avgnum_medfee_sumamt": "56727321.47",
    "avg_fund_pay_sumamt": "77730431.04",
    "avgnum_fund_pay_sumamt": "13778751.77",
    "avg_ipt_days": "87582051.44",
    "avgnum_ipt_days": "47698921.14",
    "prop_totlcnt_num": "13548140.62",
    "vix": "69581587.08",
    "etl_create_time": "2024-01-25 11:34:20+08:00"
  },
  {
    "timetype": "quarterly",
    "setl_time": "2021-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "medinslv": "2",
    "hosp_natu_code": "2",
    "totalcnt_fixmedins_code": "34669006.78",
    "totalcnt_psn_no": "30106832.21",
    "totalnum_mdtrt_id": "91427375.88",
    "sum_medfee_sumamt": "28375346.24",
    "sum_hifp_pay": "5787347.9",
    "sum_fund_pay_sumamt": "75118570.98",
    "sum_acct_pay": "50947267.22",
    "sum_cash_payamt": "79547225.27",
    "sum_balc": "7180920.9",
    "sum_inscp_amt": "13803243.3",
    "sum_hi_agre_sumfee": "81821147.46",
    "sum_acct_mulaid_pay": "19852080.88",
    "sum_bydise_setl_payamt": "88795847.62",
    "sum_cvlserv_pay": "82919376.61",
    "sum_maf_pay": "3182738.83",
    "sum_ipt_days": "39247854.25",
    "avg_medfee_sumamt": "63665332.25",
    "avgnum_medfee_sumamt": "99998075.94",
    "avg_fund_pay_sumamt": "32687077.17",
    "avgnum_fund_pay_sumamt": "50109780.12",
    "avg_ipt_days": "10923475.04",
    "avgnum_ipt_days": "63945670.95",
    "prop_totlcnt_num": "11395978.42",
    "vix": "75685582.08",
    "etl_create_time": "2024-01-25 11:34:21+08:00"
  },
  {
    "timetype": "quarterly",
    "setl_time": "2021-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "medinslv": "3",
    "hosp_natu_code": "2",
    "totalcnt_fixmedins_code": "65478222.75",
    "totalcnt_psn_no": "65895273.76",
    "totalnum_mdtrt_id": "449909.33",
    "sum_medfee_sumamt": "99556002.41",
    "sum_hifp_pay": "85215564.88",
    "sum_fund_pay_sumamt": "39178897.81",
    "sum_acct_pay": "64642858.74",
    "sum_cash_payamt": "84610897.19",
    "sum_balc": "63468001.39",
    "sum_inscp_amt": "37558211.51",
    "sum_hi_agre_sumfee": "34549491.73",
    "sum_acct_mulaid_pay": "73394552.11",
    "sum_bydise_setl_payamt": "64360843.83",
    "sum_cvlserv_pay": "14241008.31",
    "sum_maf_pay": "1722690.48",
    "sum_ipt_days": "44357006.04",
    "avg_medfee_sumamt": "30016978.32",
    "avgnum_medfee_sumamt": "64677561.52",
    "avg_fund_pay_sumamt": "98585327.8",
    "avgnum_fund_pay_sumamt": "82541921.87",
    "avg_ipt_days": "23600219.53",
    "avgnum_ipt_days": "5849452.13",
    "prop_totlcnt_num": "21884045.78",
    "vix": "52678868.36",
    "etl_create_time": "2024-01-25 11:34:21+08:00"
  }
]
```

---

## 表: `fqz_cgzhan_tcq_yydj_yyxz_jzdlb`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| timetype | String |  |
| setl_time | String |  |
| admdvs_code | String |  |
| admdvs_name | String |  |
| medinslv | String |  |
| hosp_natu_code | String |  |
| mdtrt_type | String |  |
| totalcnt_fixmedins_code | String |  |
| totalcnt_psn_no | String |  |
| totalnum_mdtrt_id | String |  |
| sum_medfee_sumamt | Float64 |  |
| sum_hifp_pay | Float64 |  |
| sum_fund_pay_sumamt | Float64 |  |
| sum_acct_pay | Float64 |  |
| sum_cash_payamt | Float64 |  |
| sum_balc | Float64 |  |
| sum_inscp_amt | Float64 |  |
| sum_hi_agre_sumfee | Float64 |  |
| sum_acct_mulaid_pay | Float64 |  |
| sum_bydise_setl_payamt | Float64 |  |
| sum_cvlserv_pay | Float64 |  |
| sum_maf_pay | Float64 |  |
| sum_ipt_days | Float64 |  |
| avg_medfee_sumamt | Float64 |  |
| avgnum_medfee_sumamt | Float64 |  |
| avg_fund_pay_sumamt | Float64 |  |
| avgnum_fund_pay_sumamt | Float64 |  |
| avg_ipt_days | Float64 |  |
| avgnum_ipt_days | Float64 |  |
| prop_totlcnt_num | Float64 |  |
| vix | Float64 |  |
| etl_create_time | String |  |

### 数据样例 (前3条)

```json
[
  {
    "timetype": "halfyearly",
    "setl_time": "2022-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "medinslv": "3",
    "hosp_natu_code": "2",
    "mdtrt_type": "310",
    "totalcnt_fixmedins_code": "11795",
    "totalcnt_psn_no": "104657",
    "totalnum_mdtrt_id": "12117",
    "sum_medfee_sumamt": "89435906.1",
    "sum_hifp_pay": "65444667.95",
    "sum_fund_pay_sumamt": "43355064.92",
    "sum_acct_pay": "127353239.75",
    "sum_cash_payamt": "63944643.58",
    "sum_balc": "107126338.36",
    "sum_inscp_amt": "95980691.76",
    "sum_hi_agre_sumfee": "142185893.16",
    "sum_acct_mulaid_pay": "123916500.77",
    "sum_bydise_setl_payamt": "151990851.29",
    "sum_cvlserv_pay": "125453135.25",
    "sum_maf_pay": "84289506.78",
    "sum_ipt_days": "124266536.97",
    "avg_medfee_sumamt": "107548842.59",
    "avgnum_medfee_sumamt": "148181227.33",
    "avg_fund_pay_sumamt": "112174396.41",
    "avgnum_fund_pay_sumamt": "57861103.86",
    "avg_ipt_days": "33620204.64",
    "avgnum_ipt_days": "56257795.6",
    "prop_totlcnt_num": "88086115.33",
    "vix": "187217493.8",
    "etl_create_time": ""
  },
  {
    "timetype": "halfyearly",
    "setl_time": "2022-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "medinslv": "2",
    "hosp_natu_code": "4",
    "mdtrt_type": "310",
    "totalcnt_fixmedins_code": "9627",
    "totalcnt_psn_no": "41414",
    "totalnum_mdtrt_id": "8118",
    "sum_medfee_sumamt": "131958743.02",
    "sum_hifp_pay": "117189607.76",
    "sum_fund_pay_sumamt": "88794776.28",
    "sum_acct_pay": "59580645.92",
    "sum_cash_payamt": "88062196.75",
    "sum_balc": "133541698.48",
    "sum_inscp_amt": "109144655.97",
    "sum_hi_agre_sumfee": "37732088.96",
    "sum_acct_mulaid_pay": "34760057.07",
    "sum_bydise_setl_payamt": "25893671.0",
    "sum_cvlserv_pay": "57768363.52",
    "sum_maf_pay": "114905488.2",
    "sum_ipt_days": "96449074.42",
    "avg_medfee_sumamt": "108253718.44",
    "avgnum_medfee_sumamt": "85308331.69",
    "avg_fund_pay_sumamt": "49673212.05",
    "avgnum_fund_pay_sumamt": "66822887.43",
    "avg_ipt_days": "117326077.73",
    "avgnum_ipt_days": "108268611.03",
    "prop_totlcnt_num": "12014159.81",
    "vix": "112578705.21",
    "etl_create_time": ""
  },
  {
    "timetype": "halfyearly",
    "setl_time": "2022-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "medinslv": "1",
    "hosp_natu_code": "4",
    "mdtrt_type": "310",
    "totalcnt_fixmedins_code": "13739",
    "totalcnt_psn_no": "106319",
    "totalnum_mdtrt_id": "16141",
    "sum_medfee_sumamt": "192647055.01",
    "sum_hifp_pay": "46274183.6",
    "sum_fund_pay_sumamt": "39535138.1",
    "sum_acct_pay": "101341640.56",
    "sum_cash_payamt": "100834140.67",
    "sum_balc": "16174083.74",
    "sum_inscp_amt": "98458613.38",
    "sum_hi_agre_sumfee": "66604257.35",
    "sum_acct_mulaid_pay": "191391570.23",
    "sum_bydise_setl_payamt": "121587953.44",
    "sum_cvlserv_pay": "41205134.35",
    "sum_maf_pay": "102156010.32",
    "sum_ipt_days": "99980516.51",
    "avg_medfee_sumamt": "178434363.64",
    "avgnum_medfee_sumamt": "43387253.53",
    "avg_fund_pay_sumamt": "59776992.25",
    "avgnum_fund_pay_sumamt": "143297906.23",
    "avg_ipt_days": "90665291.54",
    "avgnum_ipt_days": "101753565.56",
    "prop_totlcnt_num": "90275448.08",
    "vix": "153896450.73",
    "etl_create_time": ""
  }
]
```

---

## 表: `fqz_cgzhan_tcq_yydj_yyxz_xzlb`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| timetype | String |  |
| setl_time | String |  |
| admdvs_code | String |  |
| admdvs_name | String |  |
| medinslv | String |  |
| hosp_natu_code | String |  |
| insutype | String |  |
| totalcnt_fixmedins_code | String |  |
| totalcnt_psn_no | String |  |
| totalnum_mdtrt_id | String |  |
| sum_medfee_sumamt | Float64 |  |
| sum_hifp_pay | Float64 |  |
| sum_fund_pay_sumamt | Float64 |  |
| sum_acct_pay | Float64 |  |
| sum_cash_payamt | Float64 |  |
| sum_balc | Float64 |  |
| sum_inscp_amt | Float64 |  |
| sum_hi_agre_sumfee | Float64 |  |
| sum_acct_mulaid_pay | Float64 |  |
| sum_bydise_setl_payamt | Float64 |  |
| sum_cvlserv_pay | Float64 |  |
| sum_maf_pay | Float64 |  |
| sum_ipt_days | Float64 |  |
| avg_medfee_sumamt | Float64 |  |
| avgnum_medfee_sumamt | Float64 |  |
| avg_fund_pay_sumamt | Float64 |  |
| avgnum_fund_pay_sumamt | Float64 |  |
| avg_ipt_days | Float64 |  |
| avgnum_ipt_days | Float64 |  |
| prop_totlcnt_num | Float64 |  |
| vix | Float64 |  |
| etl_create_time | String |  |

### 数据样例 (前3条)

```json
[
  {
    "timetype": "halfyearly",
    "setl_time": "2022-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "medinslv": "2",
    "hosp_natu_code": "2",
    "insutype": "2",
    "totalcnt_fixmedins_code": "7167",
    "totalcnt_psn_no": "16392",
    "totalnum_mdtrt_id": "1149",
    "sum_medfee_sumamt": "64813323.05",
    "sum_hifp_pay": "8552356.15",
    "sum_fund_pay_sumamt": "67923088.09",
    "sum_acct_pay": "57563228.99",
    "sum_cash_payamt": "78113341.3",
    "sum_balc": "3112564.63",
    "sum_inscp_amt": "15893903.45",
    "sum_hi_agre_sumfee": "29538174.93",
    "sum_acct_mulaid_pay": "37483438.9",
    "sum_bydise_setl_payamt": "57008524.26",
    "sum_cvlserv_pay": "41881018.28",
    "sum_maf_pay": "63602207.11",
    "sum_ipt_days": "31207625.05",
    "avg_medfee_sumamt": "43689880.98",
    "avgnum_medfee_sumamt": "64028187.01",
    "avg_fund_pay_sumamt": "81222569.19",
    "avgnum_fund_pay_sumamt": "30950880.8",
    "avg_ipt_days": "63907548.82",
    "avgnum_ipt_days": "42559917.39",
    "prop_totlcnt_num": "87930550.97",
    "vix": "20127419.45",
    "etl_create_time": ""
  },
  {
    "timetype": "halfyearly",
    "setl_time": "2022-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "medinslv": "1",
    "hosp_natu_code": "2",
    "insutype": "1",
    "totalcnt_fixmedins_code": "3344",
    "totalcnt_psn_no": "84302",
    "totalnum_mdtrt_id": "7974",
    "sum_medfee_sumamt": "26911298.09",
    "sum_hifp_pay": "25036073.29",
    "sum_fund_pay_sumamt": "25444354.88",
    "sum_acct_pay": "27573205.29",
    "sum_cash_payamt": "45554734.01",
    "sum_balc": "19884864.94",
    "sum_inscp_amt": "58877814.45",
    "sum_hi_agre_sumfee": "28555739.26",
    "sum_acct_mulaid_pay": "92906203.73",
    "sum_bydise_setl_payamt": "78057290.16",
    "sum_cvlserv_pay": "90647749.4",
    "sum_maf_pay": "71332688.54",
    "sum_ipt_days": "28648578.93",
    "avg_medfee_sumamt": "35063257.84",
    "avgnum_medfee_sumamt": "8124895.61",
    "avg_fund_pay_sumamt": "71665970.65",
    "avgnum_fund_pay_sumamt": "31193466.42",
    "avg_ipt_days": "21114649.1",
    "avgnum_ipt_days": "54230999.91",
    "prop_totlcnt_num": "43235699.22",
    "vix": "52621835.27",
    "etl_create_time": ""
  },
  {
    "timetype": "halfyearly",
    "setl_time": "2022-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "medinslv": "2",
    "hosp_natu_code": "1",
    "insutype": "2",
    "totalcnt_fixmedins_code": "6971",
    "totalcnt_psn_no": "69979",
    "totalnum_mdtrt_id": "9598",
    "sum_medfee_sumamt": "83068857.33",
    "sum_hifp_pay": "53215893.87",
    "sum_fund_pay_sumamt": "52332446.95",
    "sum_acct_pay": "13218837.97",
    "sum_cash_payamt": "1934222.85",
    "sum_balc": "64612468.75",
    "sum_inscp_amt": "88399610.08",
    "sum_hi_agre_sumfee": "69832036.26",
    "sum_acct_mulaid_pay": "93535224.79",
    "sum_bydise_setl_payamt": "75326294.5",
    "sum_cvlserv_pay": "27743310.91",
    "sum_maf_pay": "27188186.92",
    "sum_ipt_days": "60602655.5",
    "avg_medfee_sumamt": "23750385.48",
    "avgnum_medfee_sumamt": "9658016.71",
    "avg_fund_pay_sumamt": "15795289.07",
    "avgnum_fund_pay_sumamt": "18627589.8",
    "avg_ipt_days": "77677499.89",
    "avgnum_ipt_days": "64201916.12",
    "prop_totlcnt_num": "96566111.99",
    "vix": "49100224.63",
    "etl_create_time": ""
  }
]
```

---

## 表: `fqz_cgzhan_tcq_yydj_yyxz_xzlb_jzdlb`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| timetype | String |  |
| setl_time | String |  |
| admdvs_code | String |  |
| admdvs_name | String |  |
| medinslv | String |  |
| insutype | String |  |
| hosp_natu_code | String |  |
| mdtrt_type | String |  |
| totalcnt_fixmedins_code | String |  |
| totalcnt_psn_no | String |  |
| totalnum_mdtrt_id | String |  |
| sum_medfee_sumamt | Float64 |  |
| sum_hifp_pay | Float64 |  |
| sum_fund_pay_sumamt | Float64 |  |
| sum_acct_pay | Float64 |  |
| sum_cash_payamt | Float64 |  |
| sum_balc | Float64 |  |
| sum_inscp_amt | Float64 |  |
| sum_hi_agre_sumfee | Float64 |  |
| sum_acct_mulaid_pay | Float64 |  |
| sum_bydise_setl_payamt | Float64 |  |
| sum_cvlserv_pay | Float64 |  |
| sum_maf_pay | Float64 |  |
| sum_ipt_days | Float64 |  |
| avg_medfee_sumamt | Float64 |  |
| avgnum_medfee_sumamt | Float64 |  |
| avg_fund_pay_sumamt | Float64 |  |
| avgnum_fund_pay_sumamt | Float64 |  |
| avg_ipt_days | Float64 |  |
| avgnum_ipt_days | Float64 |  |
| prop_totlcnt_num | Float64 |  |
| vix | Float64 |  |
| etl_create_time | Date |  |

### 数据样例 (前3条)

```json
[
  {
    "timetype": "halfyearly",
    "setl_time": "2022-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "medinslv": "1",
    "insutype": "2",
    "hosp_natu_code": "2",
    "mdtrt_type": "310",
    "totalcnt_fixmedins_code": "3000",
    "totalcnt_psn_no": "2460",
    "totalnum_mdtrt_id": "305",
    "sum_medfee_sumamt": "97258442.07",
    "sum_hifp_pay": "46064909.34",
    "sum_fund_pay_sumamt": "19664988.77",
    "sum_acct_pay": "44665097.77",
    "sum_cash_payamt": "45737173.6",
    "sum_balc": "75475238.01",
    "sum_inscp_amt": "77089458.86",
    "sum_hi_agre_sumfee": "9839106.94",
    "sum_acct_mulaid_pay": "75457381.11",
    "sum_bydise_setl_payamt": "62921097.46",
    "sum_cvlserv_pay": "27092908.3",
    "sum_maf_pay": "24369533.31",
    "sum_ipt_days": "44670481.58",
    "avg_medfee_sumamt": "76744801.81",
    "avgnum_medfee_sumamt": "59310576.4",
    "avg_fund_pay_sumamt": "49081042.29",
    "avgnum_fund_pay_sumamt": "90415687.51",
    "avg_ipt_days": "62381978.43",
    "avgnum_ipt_days": "16864470.11",
    "prop_totlcnt_num": "66516952.35",
    "vix": "76618208.11",
    "etl_create_time": "2022-12-01"
  },
  {
    "timetype": "halfyearly",
    "setl_time": "2022-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "medinslv": "3",
    "insutype": "2",
    "hosp_natu_code": "2",
    "mdtrt_type": "310",
    "totalcnt_fixmedins_code": "4096",
    "totalcnt_psn_no": "87529",
    "totalnum_mdtrt_id": "9024",
    "sum_medfee_sumamt": "17808123.99",
    "sum_hifp_pay": "5166602.89",
    "sum_fund_pay_sumamt": "35322410.72",
    "sum_acct_pay": "68996845.44",
    "sum_cash_payamt": "16052873.45",
    "sum_balc": "36242872.18",
    "sum_inscp_amt": "7157027.69",
    "sum_hi_agre_sumfee": "51005257.98",
    "sum_acct_mulaid_pay": "82390079.86",
    "sum_bydise_setl_payamt": "83983495.28",
    "sum_cvlserv_pay": "62817286.76",
    "sum_maf_pay": "33800626.58",
    "sum_ipt_days": "54612436.39",
    "avg_medfee_sumamt": "59807870.59",
    "avgnum_medfee_sumamt": "52862308.07",
    "avg_fund_pay_sumamt": "67628069.12",
    "avgnum_fund_pay_sumamt": "16225297.32",
    "avg_ipt_days": "17938837.64",
    "avgnum_ipt_days": "47274797.67",
    "prop_totlcnt_num": "32028608.17",
    "vix": "94445058.02",
    "etl_create_time": "2022-12-01"
  },
  {
    "timetype": "halfyearly",
    "setl_time": "2022-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "medinslv": "2",
    "insutype": "2",
    "hosp_natu_code": "2",
    "mdtrt_type": "310",
    "totalcnt_fixmedins_code": "7167",
    "totalcnt_psn_no": "16392",
    "totalnum_mdtrt_id": "1149",
    "sum_medfee_sumamt": "64813323.05",
    "sum_hifp_pay": "8552356.15",
    "sum_fund_pay_sumamt": "67923088.09",
    "sum_acct_pay": "57563228.99",
    "sum_cash_payamt": "78113341.3",
    "sum_balc": "3112564.63",
    "sum_inscp_amt": "15893903.45",
    "sum_hi_agre_sumfee": "29538174.93",
    "sum_acct_mulaid_pay": "37483438.9",
    "sum_bydise_setl_payamt": "57008524.26",
    "sum_cvlserv_pay": "41881018.28",
    "sum_maf_pay": "63602207.11",
    "sum_ipt_days": "31207625.05",
    "avg_medfee_sumamt": "43689880.98",
    "avgnum_medfee_sumamt": "64028187.01",
    "avg_fund_pay_sumamt": "81222569.19",
    "avgnum_fund_pay_sumamt": "30950880.8",
    "avg_ipt_days": "63907548.82",
    "avgnum_ipt_days": "42559917.39",
    "prop_totlcnt_num": "87930550.97",
    "vix": "20127419.45",
    "etl_create_time": "2022-12-01"
  }
]
```

---

## 表: `fqz_cgzhan_tcq_yyxz`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| timetype | String |  |
| setl_time | String |  |
| admdvs_code | String |  |
| admdvs_name | String |  |
| hosp_natu_code | String |  |
| totalcnt_fixmedins_code | String |  |
| totalcnt_psn_no | String |  |
| totalnum_mdtrt_id | String |  |
| sum_medfee_sumamt | Float64 |  |
| sum_hifp_pay | Float64 |  |
| sum_fund_pay_sumamt | Float64 |  |
| sum_acct_pay | Float64 |  |
| sum_cash_payamt | Float64 |  |
| sum_balc | Float64 |  |
| sum_inscp_amt | Float64 |  |
| sum_hi_agre_sumfee | Float64 |  |
| sum_acct_mulaid_pay | Float64 |  |
| sum_bydise_setl_payamt | Float64 |  |
| sum_cvlserv_pay | Float64 |  |
| sum_maf_pay | Float64 |  |
| sum_ipt_days | Float64 |  |
| avg_medfee_sumamt | Float64 |  |
| avgnum_medfee_sumamt | Float64 |  |
| avg_fund_pay_sumamt | Float64 |  |
| avgnum_fund_pay_sumamt | Float64 |  |
| avg_ipt_days | Float64 |  |
| avgnum_ipt_days | Float64 |  |
| prop_totlcnt_num | Float64 |  |
| vix | Float64 |  |
| etl_create_time | DateTime |  |

### 数据样例 (前3条)

```json
[
  {
    "timetype": "quarterly",
    "setl_time": "2021-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "hosp_natu_code": "1",
    "totalcnt_fixmedins_code": "62413700.18",
    "totalcnt_psn_no": "89065538.49",
    "totalnum_mdtrt_id": "25945043.20",
    "sum_medfee_sumamt": "57908346.52",
    "sum_hifp_pay": "31320923.08",
    "sum_fund_pay_sumamt": "9487927.09",
    "sum_acct_pay": "96920268.09",
    "sum_cash_payamt": "68350602.27",
    "sum_balc": "76011184.55",
    "sum_inscp_amt": "65881864.82",
    "sum_hi_agre_sumfee": "96440122.6",
    "sum_acct_mulaid_pay": "87542060.76",
    "sum_bydise_setl_payamt": "80243765.45",
    "sum_cvlserv_pay": "73476356.16",
    "sum_maf_pay": "40092188.34",
    "sum_ipt_days": "83899780.73",
    "avg_medfee_sumamt": "85745498.23",
    "avgnum_medfee_sumamt": "9735145.52",
    "avg_fund_pay_sumamt": "63696710.46",
    "avgnum_fund_pay_sumamt": "33972719.48",
    "avg_ipt_days": "54791474.58",
    "avgnum_ipt_days": "60692654.13",
    "prop_totlcnt_num": "27332897.01",
    "vix": "21272541.69",
    "etl_create_time": "2024-01-24 14:33:44+08:00"
  },
  {
    "timetype": "quarterly",
    "setl_time": "2021-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "hosp_natu_code": "2",
    "totalcnt_fixmedins_code": "31343238.84",
    "totalcnt_psn_no": "47644527.39",
    "totalnum_mdtrt_id": "19709435.34",
    "sum_medfee_sumamt": "10148457.46",
    "sum_hifp_pay": "2977119.47",
    "sum_fund_pay_sumamt": "69326195.98",
    "sum_acct_pay": "44563859.24",
    "sum_cash_payamt": "7093421.67",
    "sum_balc": "23485852.04",
    "sum_inscp_amt": "48219451.11",
    "sum_hi_agre_sumfee": "29735762.46",
    "sum_acct_mulaid_pay": "42829524.04",
    "sum_bydise_setl_payamt": "94325483.66",
    "sum_cvlserv_pay": "90353335.01",
    "sum_maf_pay": "8077142.49",
    "sum_ipt_days": "86849887.73",
    "avg_medfee_sumamt": "22595311.97",
    "avgnum_medfee_sumamt": "44713574.86",
    "avg_fund_pay_sumamt": "81639058.92",
    "avgnum_fund_pay_sumamt": "37224496.39",
    "avg_ipt_days": "46743811.39",
    "avgnum_ipt_days": "78313479.17",
    "prop_totlcnt_num": "4393223.61",
    "vix": "42398126.42",
    "etl_create_time": "2024-01-24 14:33:44+08:00"
  },
  {
    "timetype": "quarterly",
    "setl_time": "2021-01",
    "admdvs_code": "110000",
    "admdvs_name": "北京市",
    "hosp_natu_code": "1",
    "totalcnt_fixmedins_code": "1730184.47",
    "totalcnt_psn_no": "21324.77",
    "totalnum_mdtrt_id": "580809.83",
    "sum_medfee_sumamt": "1006806.96",
    "sum_hifp_pay": "1867994.19",
    "sum_fund_pay_sumamt": "340699.81",
    "sum_acct_pay": "1108164.62",
    "sum_cash_payamt": "1803500.32",
    "sum_balc": "74363.83",
    "sum_inscp_amt": "186429.0",
    "sum_hi_agre_sumfee": "1772627.34",
    "sum_acct_mulaid_pay": "91999.49",
    "sum_bydise_setl_payamt": "1965408.0",
    "sum_cvlserv_pay": "1797724.17",
    "sum_maf_pay": "596436.42",
    "sum_ipt_days": "661895.42",
    "avg_medfee_sumamt": "551887.9",
    "avgnum_medfee_sumamt": "954891.27",
    "avg_fund_pay_sumamt": "1152183.99",
    "avgnum_fund_pay_sumamt": "1014439.47",
    "avg_ipt_days": "1640467.54",
    "avgnum_ipt_days": "734987.45",
    "prop_totlcnt_num": "1782198.34",
    "vix": "377511.83",
    "etl_create_time": "2024-01-24 14:33:44+08:00"
  }
]
```

---

## 表: `fqz_cgzhan_tcq_yyxz_jzdlb`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| timetype | String |  |
| setl_time | String |  |
| admdvs_code | String |  |
| admdvs_name | String |  |
| hosp_natu_code | String |  |
| mdtrt_type | String |  |
| totalcnt_fixmedins_code | String |  |
| totalcnt_psn_no | String |  |
| totalnum_mdtrt_id | String |  |
| sum_medfee_sumamt | Float64 |  |
| sum_hifp_pay | Float64 |  |
| sum_fund_pay_sumamt | Float64 |  |
| sum_acct_pay | Float64 |  |
| sum_cash_payamt | Float64 |  |
| sum_balc | Float64 |  |
| sum_inscp_amt | Float64 |  |
| sum_hi_agre_sumfee | Float64 |  |
| sum_acct_mulaid_pay | Float64 |  |
| sum_bydise_setl_payamt | Float64 |  |
| sum_cvlserv_pay | Float64 |  |
| sum_maf_pay | Float64 |  |
| sum_ipt_days | Float64 |  |
| avg_medfee_sumamt | Float64 |  |
| avgnum_medfee_sumamt | Float64 |  |
| avg_fund_pay_sumamt | Float64 |  |
| avgnum_fund_pay_sumamt | Float64 |  |
| avg_ipt_days | Float64 |  |
| avgnum_ipt_days | Float64 |  |
| prop_totlcnt_num | Float64 |  |
| vix | Float64 |  |
| etl_create_time | String |  |

### 数据样例 (前3条)

```json
[
  {
    "timetype": "halfyearly",
    "setl_time": "2022-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "hosp_natu_code": "4",
    "mdtrt_type": "310",
    "totalcnt_fixmedins_code": "40985",
    "totalcnt_psn_no": "318615",
    "totalnum_mdtrt_id": "37082",
    "sum_medfee_sumamt": "636011838.07",
    "sum_hifp_pay": "377597012.17",
    "sum_fund_pay_sumamt": "357734625.29",
    "sum_acct_pay": "227076243.89",
    "sum_cash_payamt": "371374197.27",
    "sum_balc": "245599052.51",
    "sum_inscp_amt": "436718722.49",
    "sum_hi_agre_sumfee": "323591341.89",
    "sum_acct_mulaid_pay": "380416530.81",
    "sum_bydise_setl_payamt": "395834745.58",
    "sum_cvlserv_pay": "298386784.64",
    "sum_maf_pay": "483023181.87",
    "sum_ipt_days": "308648656.8",
    "avg_medfee_sumamt": "473833900.92",
    "avgnum_medfee_sumamt": "250496796.16",
    "avg_fund_pay_sumamt": "194620348.99",
    "avgnum_fund_pay_sumamt": "370509273.69",
    "avg_ipt_days": "362811429.5",
    "avgnum_ipt_days": "361341322.9",
    "prop_totlcnt_num": "189441034.13",
    "vix": "507664511.36",
    "etl_create_time": ""
  },
  {
    "timetype": "halfyearly",
    "setl_time": "2022-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "hosp_natu_code": "2",
    "mdtrt_type": "310",
    "totalcnt_fixmedins_code": "46064",
    "totalcnt_psn_no": "406822",
    "totalnum_mdtrt_id": "38172",
    "sum_medfee_sumamt": "367234201.4",
    "sum_hifp_pay": "334388070.78",
    "sum_fund_pay_sumamt": "292669942.51",
    "sum_acct_pay": "362358436.93",
    "sum_cash_payamt": "371784116.34",
    "sum_balc": "436613509.34",
    "sum_inscp_amt": "437022467.94",
    "sum_hi_agre_sumfee": "395830892.32",
    "sum_acct_mulaid_pay": "466976255.49",
    "sum_bydise_setl_payamt": "421631835.2",
    "sum_cvlserv_pay": "374383156.53",
    "sum_maf_pay": "428136258.64",
    "sum_ipt_days": "424958621.88",
    "avg_medfee_sumamt": "389775172.81",
    "avgnum_medfee_sumamt": "387251734.9",
    "avg_fund_pay_sumamt": "424310228.76",
    "avgnum_fund_pay_sumamt": "384352450.15",
    "avg_ipt_days": "284780575.53",
    "avgnum_ipt_days": "312005730.08",
    "prop_totlcnt_num": "400916848.75",
    "vix": "461543779.62",
    "etl_create_time": ""
  },
  {
    "timetype": "halfyearly",
    "setl_time": "2022-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "hosp_natu_code": "1",
    "mdtrt_type": "310",
    "totalcnt_fixmedins_code": "42917",
    "totalcnt_psn_no": "414709",
    "totalnum_mdtrt_id": "33774",
    "sum_medfee_sumamt": "400416038.89",
    "sum_hifp_pay": "344691260.64",
    "sum_fund_pay_sumamt": "505415825.09",
    "sum_acct_pay": "315290062.38",
    "sum_cash_payamt": "357284960.61",
    "sum_balc": "460931228.31",
    "sum_inscp_amt": "611860955.43",
    "sum_hi_agre_sumfee": "468147773.46",
    "sum_acct_mulaid_pay": "405232150.9",
    "sum_bydise_setl_payamt": "447664287.59",
    "sum_cvlserv_pay": "449008222.57",
    "sum_maf_pay": "447555180.41",
    "sum_ipt_days": "401745560.76",
    "avg_medfee_sumamt": "393987979.8",
    "avgnum_medfee_sumamt": "429508243.61",
    "avg_fund_pay_sumamt": "353497155.67",
    "avgnum_fund_pay_sumamt": "320330868.19",
    "avg_ipt_days": "318500753.34",
    "avgnum_ipt_days": "415667690.94",
    "prop_totlcnt_num": "436525030.11",
    "vix": "598795708.06",
    "etl_create_time": ""
  }
]
```

---

## 表: `fqz_cgzhan_tcq_yyxz_xzlb_jzdlb`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| timetype | String |  |
| setl_time | String |  |
| admdvs_code | String |  |
| admdvs_name | String |  |
| insutype | String |  |
| hosp_natu_code | String |  |
| mdtrt_type | String |  |
| totalcnt_fixmedins_code | String |  |
| totalcnt_psn_no | String |  |
| totalnum_mdtrt_id | String |  |
| sum_medfee_sumamt | Float64 |  |
| sum_hifp_pay | Float64 |  |
| sum_fund_pay_sumamt | Float64 |  |
| sum_acct_pay | Float64 |  |
| sum_cash_payamt | Float64 |  |
| sum_balc | Float64 |  |
| sum_inscp_amt | Float64 |  |
| sum_hi_agre_sumfee | Float64 |  |
| sum_acct_mulaid_pay | Float64 |  |
| sum_bydise_setl_payamt | Float64 |  |
| sum_cvlserv_pay | Float64 |  |
| sum_maf_pay | Float64 |  |
| sum_ipt_days | Float64 |  |
| avg_medfee_sumamt | Float64 |  |
| avgnum_medfee_sumamt | Float64 |  |
| avg_fund_pay_sumamt | Float64 |  |
| avgnum_fund_pay_sumamt | Float64 |  |
| avg_ipt_days | Float64 |  |
| avgnum_ipt_days | Float64 |  |
| prop_totlcnt_num | Float64 |  |
| vix | Float64 |  |
| etl_create_time | String |  |

### 数据样例 (前3条)

```json
[
  {
    "timetype": "halfyearly",
    "setl_time": "2022-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "insutype": "1",
    "hosp_natu_code": "3",
    "mdtrt_type": "310",
    "totalcnt_fixmedins_code": "23325",
    "totalcnt_psn_no": "217568",
    "totalnum_mdtrt_id": "20567",
    "sum_medfee_sumamt": "190266975.61",
    "sum_hifp_pay": "221902445.77",
    "sum_fund_pay_sumamt": "166111316.34",
    "sum_acct_pay": "147198665.01",
    "sum_cash_payamt": "256622351.64",
    "sum_balc": "143346252.98",
    "sum_inscp_amt": "107160885.64",
    "sum_hi_agre_sumfee": "338122110.79",
    "sum_acct_mulaid_pay": "259779807.37",
    "sum_bydise_setl_payamt": "170047156.59",
    "sum_cvlserv_pay": "227778982.61",
    "sum_maf_pay": "260740157.77",
    "sum_ipt_days": "295969722.57",
    "avg_medfee_sumamt": "240821782.35",
    "avgnum_medfee_sumamt": "169853737.76",
    "avg_fund_pay_sumamt": "270424301.95",
    "avgnum_fund_pay_sumamt": "286339499.18",
    "avg_ipt_days": "194411737.47",
    "avgnum_ipt_days": "265209853.16",
    "prop_totlcnt_num": "137113928.65",
    "vix": "202833988.19",
    "etl_create_time": ""
  },
  {
    "timetype": "halfyearly",
    "setl_time": "2022-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "insutype": "1",
    "hosp_natu_code": "4",
    "mdtrt_type": "310",
    "totalcnt_fixmedins_code": "22814",
    "totalcnt_psn_no": "166277",
    "totalnum_mdtrt_id": "17817",
    "sum_medfee_sumamt": "331207724.72",
    "sum_hifp_pay": "152736800.39",
    "sum_fund_pay_sumamt": "170063124.46",
    "sum_acct_pay": "129302285.76",
    "sum_cash_payamt": "185079317.7",
    "sum_balc": "88567791.67",
    "sum_inscp_amt": "211255040.98",
    "sum_hi_agre_sumfee": "273195932.44",
    "sum_acct_mulaid_pay": "238508545.94",
    "sum_bydise_setl_payamt": "164251591.48",
    "sum_cvlserv_pay": "151304307.68",
    "sum_maf_pay": "194927515.84",
    "sum_ipt_days": "109665206.1",
    "avg_medfee_sumamt": "294163456.08",
    "avgnum_medfee_sumamt": "134115368.49",
    "avg_fund_pay_sumamt": "142873917.75",
    "avgnum_fund_pay_sumamt": "229866362.45",
    "avg_ipt_days": "251257679.59",
    "avgnum_ipt_days": "131593753.88",
    "prop_totlcnt_num": "146913989.42",
    "vix": "285467473.15",
    "etl_create_time": ""
  },
  {
    "timetype": "halfyearly",
    "setl_time": "2022-01",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "insutype": "2",
    "hosp_natu_code": "2",
    "mdtrt_type": "310",
    "totalcnt_fixmedins_code": "20279",
    "totalcnt_psn_no": "146085",
    "totalnum_mdtrt_id": "15088",
    "sum_medfee_sumamt": "220728626.27",
    "sum_hifp_pay": "118123033.49",
    "sum_fund_pay_sumamt": "146244323.81",
    "sum_acct_pay": "191764997.1",
    "sum_cash_payamt": "147105444.95",
    "sum_balc": "199980997.69",
    "sum_inscp_amt": "189193290.12",
    "sum_hi_agre_sumfee": "177022825.63",
    "sum_acct_mulaid_pay": "200421749.55",
    "sum_bydise_setl_payamt": "259684732.82",
    "sum_cvlserv_pay": "157164315.05",
    "sum_maf_pay": "148869504.45",
    "sum_ipt_days": "185166673.33",
    "avg_medfee_sumamt": "212788033.03",
    "avgnum_medfee_sumamt": "251280937.8",
    "avg_fund_pay_sumamt": "267238682.48",
    "avgnum_fund_pay_sumamt": "210310655.32",
    "avg_ipt_days": "163653476.01",
    "avgnum_ipt_days": "187944331.56",
    "prop_totlcnt_num": "190550869.0",
    "vix": "229694730.84",
    "etl_create_time": ""
  }
]
```

---

## 表: `fqz_dim_date`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| udate | String |  |
| date_string | Date |  |
| uquarter | String |  |
| umonth | String |  |
| uweekold | Int64 |  |
| day_of_week | String |  |
| uweek | String |  |
| nd | String |  |

### 数据样例 (前3条)

```json
[
  {
    "udate": "2020-01-01",
    "date_string": "2020-01-01",
    "uquarter": "1",
    "umonth": "1",
    "uweekold": "1",
    "day_of_week": "3",
    "uweek": "1",
    "nd": "2020"
  },
  {
    "udate": "2020-01-02",
    "date_string": "2020-01-02",
    "uquarter": "1",
    "umonth": "1",
    "uweekold": "1",
    "day_of_week": "4",
    "uweek": "1",
    "nd": "2020"
  },
  {
    "udate": "2020-01-03",
    "date_string": "2020-01-03",
    "uquarter": "1",
    "umonth": "1",
    "uweekold": "1",
    "day_of_week": "5",
    "uweek": "1",
    "nd": "2020"
  }
]
```

---

## 表: `fqz_dm_admdvs`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| prv_code | String |  |
| prv_name | String |  |
| prov | String |  |
| city_code | String |  |
| city_name | String |  |
| admdvs_code | String |  |
| admdvs_name | String |  |
| admdvs_lv | Int64 |  |

### 数据样例 (前3条)

```json
[
  {
    "prv_code": "100000",
    "prv_name": "国家医疗保障局",
    "prov": "GJ",
    "city_code": "",
    "city_name": "",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "admdvs_lv": "0"
  },
  {
    "prv_code": "110000",
    "prv_name": "北京市",
    "prov": "BJ",
    "city_code": "110000",
    "city_name": "北京市",
    "admdvs_code": "110000",
    "admdvs_name": "北京市",
    "admdvs_lv": "1"
  },
  {
    "prv_code": "110000",
    "prv_name": "北京市",
    "prov": "BJ",
    "city_code": "110101",
    "city_name": "东城区",
    "admdvs_code": "110101",
    "admdvs_name": "东城区",
    "admdvs_lv": "3"
  }
]
```

---

## 表: `fqz_dm_admdvs_sync`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| prv_code | String |  |
| prv_name | String |  |
| prov | String |  |
| city_code | String |  |
| city_name | String |  |
| admdvs_code | String |  |
| admdvs_name | String |  |
| admdvs_lv | Int64 |  |

### 数据样例 (前3条)

```json
[
  {
    "prv_code": "100000",
    "prv_name": "国家医疗保障局",
    "prov": "GJ",
    "city_code": "",
    "city_name": "",
    "admdvs_code": "100000",
    "admdvs_name": "国家医疗保障局",
    "admdvs_lv": "0"
  },
  {
    "prv_code": "110000",
    "prv_name": "北京市",
    "prov": "BJ",
    "city_code": "110000",
    "city_name": "北京市",
    "admdvs_code": "110000",
    "admdvs_name": "北京市",
    "admdvs_lv": "1"
  },
  {
    "prv_code": "110000",
    "prv_name": "北京市",
    "prov": "BJ",
    "city_code": "110101",
    "city_name": "东城区",
    "admdvs_code": "110101",
    "admdvs_name": "东城区",
    "admdvs_lv": "3"
  }
]
```

---

## 表: `fqz_dm_dicqueryCinfo`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| dic_type_code | String |  |
| nat_dic_val_code | String |  |
| nat_dic_val_name | String |  |

### 数据样例 (前3条)

```json
[
  {
    "dic_type_code": "TRNS_TYPE",
    "nat_dic_val_code": "-1",
    "nat_dic_val_name": "负交易"
  },
  {
    "dic_type_code": "SERV_JOIN_STAS",
    "nat_dic_val_code": "0",
    "nat_dic_val_name": "待接收"
  },
  {
    "dic_type_code": "SERV_SOUC",
    "nat_dic_val_code": "0",
    "nat_dic_val_name": "统一接口服务"
  }
]
```

---

## 表: `fqz_dm_time`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| udate | String |  |
| uyear | String |  |
| uhalfyear | String |  |
| uquarter | String |  |
| umonth | String |  |
| uweek | String |  |

### 数据样例 (前3条)

```json
[
  {
    "udate": "2020-01-01",
    "uyear": "2020",
    "uhalfyear": "1",
    "uquarter": "1",
    "umonth": "1",
    "uweek": "1"
  },
  {
    "udate": "2020-01-02",
    "uyear": "2020",
    "uhalfyear": "1",
    "uquarter": "1",
    "umonth": "1",
    "uweek": "1"
  },
  {
    "udate": "2020-01-03",
    "uyear": "2020",
    "uhalfyear": "1",
    "uquarter": "1",
    "umonth": "1",
    "uweek": "1"
  }
]
```

---

## 表: `fqz_drug_mcs_info_list`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| projecttype | String |  |
| projrctname | String |  |
| med_list_code | String |  |
| drug_genname | String |  |
| reg_name | String |  |
| drugstdcode | String |  |
| drug_dosform | String |  |
| drug_type | String |  |
| spec | String |  |
| each_dos | String |  |
| efcc_atd | Int64 |  |
| prodentp_code | String |  |
| prodentp_name | String |  |
| nat_hi_druglist_memo | String |  |
| vali_flag | String |  |

### 数据样例 (前3条)

```json
[
  {
    "projecttype": "11",
    "projrctname": "西药中成药",
    "med_list_code": "wHdMLlYv9i9V",
    "drug_genname": "",
    "reg_name": "头孢丙烯",
    "drugstdcode": "头孢丙烯",
    "drug_dosform": "含片",
    "drug_type": "国产",
    "spec": "0.25mg",
    "each_dos": "",
    "efcc_atd": "0",
    "prodentp_code": "oltx8zhBFB",
    "prodentp_name": "mfwYkaaW2hNl5iBC8B",
    "nat_hi_druglist_memo": "",
    "vali_flag": "1"
  },
  {
    "projecttype": "11",
    "projrctname": "西药中成药",
    "med_list_code": "wgonjyglob9Z",
    "drug_genname": "",
    "reg_name": "哌拉西林",
    "drugstdcode": "哌拉西林",
    "drug_dosform": "含片",
    "drug_type": "国产",
    "spec": "0.25mg",
    "each_dos": "",
    "efcc_atd": "0",
    "prodentp_code": "UhSr008cNI",
    "prodentp_name": "1H4y4SxXdCXoEnuVAX",
    "nat_hi_druglist_memo": "",
    "vali_flag": "1"
  },
  {
    "projecttype": "11",
    "projrctname": "西药中成药",
    "med_list_code": "Ale8YIud3CPe",
    "drug_genname": "",
    "reg_name": "哌拉西林三唑巴坦",
    "drugstdcode": "哌拉西林三唑巴坦",
    "drug_dosform": "含片",
    "drug_type": "国产",
    "spec": "0.25mg",
    "each_dos": "",
    "efcc_atd": "0",
    "prodentp_code": "eEEgKMn4NC",
    "prodentp_name": "mfwYkaaW2hNl5iBC8B",
    "nat_hi_druglist_memo": "",
    "vali_flag": "1"
  }
]
```

---

## 表: `fqz_fymx_test`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| prv_name | String |  |
| city_name | String |  |
| admdvs_name | String |  |
| psn_no | String |  |
| psn_name | String |  |
| certno | String |  |
| emp_no | String |  |
| emp_name | String |  |
| emp_type | String |  |
| gend | String |  |
| cert_gend | String |  |
| age | Int64 |  |
| insutype | String |  |
| med_type | String |  |
| psn_type | String |  |
| insu_admdvs | String |  |
| setl_id | String |  |
| begndate | String |  |
| enddate | String |  |
| setl_time | String |  |
| feelist_psn_no | String |  |
| fee_ocur_time | String |  |
| mdtrt_id | String |  |
| fixmedins_code | String |  |
| fixmedins_name | String |  |
| hilist_code | String |  |
| hilist_name | String |  |
| cnt | Float64 |  |
| pric | Float64 |  |
| det_item_fee_sumamt | Float64 |  |
| fx_level | String |  |

### 数据样例 (前3条)

```json
[
  {
    "prv_name": "贵州省\t",
    "city_name": "六盘水市\t",
    "admdvs_name": "钟山区\t",
    "psn_no": "52000002000000002000783649\t",
    "psn_name": "晋加洋\t",
    "certno": "520221200001131418\t",
    "emp_no": "52000002000000520206100309\t",
    "emp_name": "钟山区木果镇杨家寨村九组\t",
    "emp_type": "99\t",
    "gend": "1\t",
    "cert_gend": "nan\t",
    "age": "21",
    "insutype": "390\t",
    "med_type": "11\t",
    "psn_type": "15\t",
    "insu_admdvs": "520201\t",
    "setl_id": "520200G0000000494465\t",
    "begndate": "2021-05-03 00:00:00\t",
    "enddate": "2021-05-03 00:00:00\t",
    "setl_time": "2021-05-03 11:41:27\t",
    "feelist_psn_no": "52000002000000002000783649\t",
    "fee_ocur_time": "2021-05-03 11:41:56\t",
    "mdtrt_id": "520200CY100000190112\t",
    "fixmedins_code": "H52020101218\t",
    "fixmedins_name": "六盘水市水城县木果镇杨家寨村卫生室\t",
    "hilist_code": "ZD01BAY0318010302251\t",
    "hilist_name": "益母草颗粒\t",
    "cnt": "1.0",
    "pric": "14.0",
    "det_item_fee_sumamt": "14.0",
    "fx_level": "3"
  },
  {
    "prv_name": "贵州省\t",
    "city_name": "六盘水市\t",
    "admdvs_name": "钟山区\t",
    "psn_no": "52000002000000001000840121\t",
    "psn_name": "文武\t",
    "certno": "520221199303080032\t",
    "emp_no": "52000002000000000010063240\t",
    "emp_name": "水城县公安局（合同制辅警）\t",
    "emp_type": "30\t",
    "gend": "1\t",
    "cert_gend": "nan\t",
    "age": "28",
    "insutype": "310\t",
    "med_type": "53_04\t",
    "psn_type": "11\t",
    "insu_admdvs": "520221\t",
    "setl_id": "520200G0000000901403\t",
    "begndate": "2021-05-14 00:00:00\t",
    "enddate": "2021-05-14 00:00:00\t",
    "setl_time": "2021-05-14 12:43:14\t",
    "feelist_psn_no": "52000002000000001000840121\t",
    "fee_ocur_time": "2021-05-14 12:27:37\t",
    "mdtrt_id": "520200G0000001230893\t",
    "fixmedins_code": "H52020100022\t",
    "fixmedins_name": "六盘水安琪儿妇产医院\t",
    "hilist_code": "XG03FBC051A001020178890\t",
    "hilist_name": "雌二醇片/雌二醇地屈孕酮片复合包装\t",
    "cnt": "1.0",
    "pric": "111.8",
    "det_item_fee_sumamt": "111.8",
    "fx_level": "3"
  },
  {
    "prv_name": "贵州省\t",
    "city_name": "六盘水市\t",
    "admdvs_name": "钟山区\t",
    "psn_no": "52000002000000001000908795\t",
    "psn_name": "袁伟\t",
    "certno": "52020319860802021X\t",
    "emp_no": "52000002000000000010019065\t",
    "emp_name": "中国人民人寿保险股份有限公司六盘水中心支公司\t",
    "emp_type": "10\t",
    "gend": "1\t",
    "cert_gend": "nan\t",
    "age": "35",
    "insutype": "310\t",
    "med_type": "53_04\t",
    "psn_type": "11\t",
    "insu_admdvs": "520201\t",
    "setl_id": "520200G0000000965006\t",
    "begndate": "2021-05-16 00:00:00\t",
    "enddate": "2021-05-16 00:00:00\t",
    "setl_time": "2021-05-16 11:57:50\t",
    "feelist_psn_no": "52000002000000001000908795\t",
    "fee_ocur_time": "2021-05-16 11:37:41\t",
    "mdtrt_id": "520200G0000001316424\t",
    "fixmedins_code": "H52020100022\t",
    "fixmedins_name": "六盘水安琪儿妇产医院\t",
    "hilist_code": "XG03FBC051A001020178890\t",
    "hilist_name": "雌二醇片/雌二醇地屈孕酮片复合包装\t",
    "cnt": "1.0",
    "pric": "111.8",
    "det_item_fee_sumamt": "111.8",
    "fx_level": "3"
  }
]
```

---

## 表: `fqz_fymx_test1`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| prv_name	 | String |  |
| city_name	 | String |  |
| admdvs_name	 | String |  |
| psn_no	 | String |  |
| psn_name	 | String |  |
| certno	 | String |  |
| emp_no	 | String |  |
| emp_name	 | String |  |
| emp_type	 | String |  |
| gend	 | String |  |
| cert_gend	 | String |  |
| age	 | Int64 |  |
| insutype	 | String |  |
| med_type	 | String |  |
| psn_type	 | String |  |
| insu_admdvs	 | String |  |
| setl_id	 | String |  |
| begndate	 | String |  |
| enddate	 | String |  |
| setl_time	 | String |  |
| feelist_psn_no	 | String |  |
| fee_ocur_time	 | String |  |
| mdtrt_id	 | String |  |
| fixmedins_code	 | String |  |
| fixmedins_name	 | String |  |
| hilist_code	 | String |  |
| hilist_name	 | String |  |
| cnt	 | Float64 |  |
| pric	 | Float64 |  |
| det_item_fee_sumamt	 | Float64 |  |

### 数据样例 (前3条)

```json
[
  {
    "prv_name\t": "贵州省\t",
    "city_name\t": "六盘水市\t",
    "admdvs_name\t": "钟山区\t",
    "psn_no\t": "52000002000000002000783649\t",
    "psn_name\t": "晋加洋\t",
    "certno\t": "520221200001131418\t",
    "emp_no\t": "52000002000000520206100309\t",
    "emp_name\t": "钟山区木果镇杨家寨村九组\t",
    "emp_type\t": "99\t",
    "gend\t": "1\t",
    "cert_gend\t": "nan\t",
    "age\t": "21",
    "insutype\t": "390\t",
    "med_type\t": "11\t",
    "psn_type\t": "15\t",
    "insu_admdvs\t": "520201\t",
    "setl_id\t": "520200G0000000494465\t",
    "begndate\t": "2021-05-03 00:00:00\t",
    "enddate\t": "2021-05-03 00:00:00\t",
    "setl_time\t": "2021-05-03 11:41:27\t",
    "feelist_psn_no\t": "52000002000000002000783649\t",
    "fee_ocur_time\t": "2021-05-03 11:41:56\t",
    "mdtrt_id\t": "520200CY100000190112\t",
    "fixmedins_code\t": "H52020101218\t",
    "fixmedins_name\t": "六盘水市水城县木果镇杨家寨村卫生室\t",
    "hilist_code\t": "ZD01BAY0318010302251\t",
    "hilist_name\t": "益母草颗粒\t",
    "cnt\t": "1.0",
    "pric\t": "14.0",
    "det_item_fee_sumamt\t": "14.0"
  },
  {
    "prv_name\t": "贵州省\t",
    "city_name\t": "六盘水市\t",
    "admdvs_name\t": "钟山区\t",
    "psn_no\t": "52000002000000001000840121\t",
    "psn_name\t": "文武\t",
    "certno\t": "520221199303080032\t",
    "emp_no\t": "52000002000000000010063240\t",
    "emp_name\t": "水城县公安局（合同制辅警）\t",
    "emp_type\t": "30\t",
    "gend\t": "1\t",
    "cert_gend\t": "nan\t",
    "age\t": "28",
    "insutype\t": "310\t",
    "med_type\t": "53_04\t",
    "psn_type\t": "11\t",
    "insu_admdvs\t": "520221\t",
    "setl_id\t": "520200G0000000901403\t",
    "begndate\t": "2021-05-14 00:00:00\t",
    "enddate\t": "2021-05-14 00:00:00\t",
    "setl_time\t": "2021-05-14 12:43:14\t",
    "feelist_psn_no\t": "52000002000000001000840121\t",
    "fee_ocur_time\t": "2021-05-14 12:27:37\t",
    "mdtrt_id\t": "520200G0000001230893\t",
    "fixmedins_code\t": "H52020100022\t",
    "fixmedins_name\t": "六盘水安琪儿妇产医院\t",
    "hilist_code\t": "XG03FBC051A001020178890\t",
    "hilist_name\t": "雌二醇片/雌二醇地屈孕酮片复合包装\t",
    "cnt\t": "1.0",
    "pric\t": "111.8",
    "det_item_fee_sumamt\t": "111.8"
  },
  {
    "prv_name\t": "贵州省\t",
    "city_name\t": "六盘水市\t",
    "admdvs_name\t": "钟山区\t",
    "psn_no\t": "52000002000000001000908795\t",
    "psn_name\t": "袁伟\t",
    "certno\t": "52020319860802021X\t",
    "emp_no\t": "52000002000000000010019065\t",
    "emp_name\t": "中国人民人寿保险股份有限公司六盘水中心支公司\t",
    "emp_type\t": "10\t",
    "gend\t": "1\t",
    "cert_gend\t": "nan\t",
    "age\t": "35",
    "insutype\t": "310\t",
    "med_type\t": "53_04\t",
    "psn_type\t": "11\t",
    "insu_admdvs\t": "520201\t",
    "setl_id\t": "520200G0000000965006\t",
    "begndate\t": "2021-05-16 00:00:00\t",
    "enddate\t": "2021-05-16 00:00:00\t",
    "setl_time\t": "2021-05-16 11:57:50\t",
    "feelist_psn_no\t": "52000002000000001000908795\t",
    "fee_ocur_time\t": "2021-05-16 11:37:41\t",
    "mdtrt_id\t": "520200G0000001316424\t",
    "fixmedins_code\t": "H52020100022\t",
    "fixmedins_name\t": "六盘水安琪儿妇产医院\t",
    "hilist_code\t": "XG03FBC051A001020178890\t",
    "hilist_name\t": "雌二醇片/雌二醇地屈孕酮片复合包装\t",
    "cnt\t": "1.0",
    "pric\t": "111.8",
    "det_item_fee_sumamt\t": "111.8"
  }
]
```

---

## 表: `fqz_gz_jzsj_all_ql`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| psn_no | String |  |
| psn_name | String |  |
| gend | String |  |
| psn_cert_type | String |  |
| certno | String |  |
| brdy | DateTime |  |
| age | Float64 |  |
| psn_type | String |  |
| tel | String |  |
| addr | String |  |
| cvlserv_flag | String |  |
| cvlserv_lv | String |  |
| sp_psn_type | String |  |
| sp_psn_type_lv | String |  |
| insu_admdvs | String |  |
| admdvs_prv | String |  |
| admdvs_prvname | String |  |
| admdvs_city | String |  |
| admdvs_cityname | String |  |
| emp_no | String |  |
| emp_name | String |  |
| emp_type | String |  |
| econ_type | String |  |
| insutype | String |  |
| fixmedins_code | String |  |
| fixmedins_name | String |  |
| medinslv | String |  |
| hosp_lv | String |  |
| hosp_natu_code | String |  |
| fix_blng_admdvs | String |  |
| fix_blng_admdvs_city | String |  |
| pay_loc | String |  |
| med_typecode | String |  |
| med_type | String |  |
| med_bigtype | String |  |
| mdtrt_id | String |  |
| ipt_otp_no | String |  |
| start_date | DateTime |  |
| end_date | DateTime |  |
| adm_dept_code | String |  |
| adm_dept_name | String |  |
| dscg_dept_codg | String |  |
| dscg_dept_name | String |  |
| ipt_days | String |  |
| adm_bed | String |  |
| chfpdr_code | String |  |
| chfpdr_name | String |  |
| dise_no | String |  |
| dise_name | String |  |
| oprn_oprt_code | String |  |
| oprn_oprt_name | String |  |
| setl_id | String |  |
| setl_time | DateTime |  |
| medfee_sumamt | Float64 |  |
| hifp_pay | Float64 |  |
| fund_pay_sumamt | Float64 |  |
| acct_pay | Float64 |  |
| cash_payamt | Float64 |  |
| balc | Float64 |  |
| inscp_amt | Float64 |  |
| hi_agre_sumfee | Float64 |  |
| acct_mulaid_pay | Float64 |  |
| bydise_setl_payamt | Float64 |  |
| cvlserv_pay | Float64 |  |
| maf_pay | Float64 |  |
| year | String |  |
| updt_time | DateTime |  |
| crte_time | DateTime |  |
| dwh_created_dt | DateTime |  |
| src_dt | String |  |
| src_prv | String |  |
| vali_flag | String |  |
| uyear | String |  |
| uhalfyear | String |  |
| uquarter | String |  |
| umonth | String |  |
| uweek | String |  |
| prv | String |  |
| city | String |  |
| admdvs_code | Int64 |  |
| admdvs_name | String |  |
| adm_caty | String |  |
| inhosp_stas | Int64 |  |
| refd_setl_flag | Int64 |  |
| setl_type | Int64 |  |
| fulamt_ownpay_amt | Int64 |  |
| hifmi_pay | Int64 |  |
| hifob_pay | Int64 |  |
| hifdm_pay | Int64 |  |
| othfund_pay | Int64 |  |
| admdvs_district | Int64 |  |

### 数据样例 (前3条)

```json
[
  {
    "psn_no": "52000001000000003004108338",
    "psn_name": "",
    "gend": "1",
    "psn_cert_type": "01",
    "certno": "",
    "brdy": "1992-02-03 00:00:00+08:00",
    "age": "32.0",
    "psn_type": "11",
    "tel": "18613630353",
    "addr": "",
    "cvlserv_flag": "0",
    "cvlserv_lv": "",
    "sp_psn_type": "0",
    "sp_psn_type_lv": "",
    "insu_admdvs": "520199",
    "admdvs_prv": "520000",
    "admdvs_prvname": "贵州省",
    "admdvs_city": "520100",
    "admdvs_cityname": "贵阳市",
    "emp_no": "52000001000000000000001276",
    "emp_name": "贵州建工集团有限公司",
    "emp_type": "10",
    "econ_type": "170",
    "insutype": "310",
    "fixmedins_code": "z\fc�)�\u0007�\u000e�~����",
    "fixmedins_name": "�Lmi�nIpqq\u0019\b6<hI",
    "medinslv": "",
    "hosp_lv": "",
    "hosp_natu_code": "",
    "fix_blng_admdvs": "520114",
    "fix_blng_admdvs_city": "520100",
    "pay_loc": "2",
    "med_typecode": "41",
    "med_type": "定点药店购药",
    "med_bigtype": "门诊",
    "mdtrt_id": "520100G0001565001062",
    "ipt_otp_no": "",
    "start_date": "2024-03-02 21:07:58+08:00",
    "end_date": "2024-03-02 21:07:58+08:00",
    "adm_dept_code": "",
    "adm_dept_name": "",
    "dscg_dept_codg": "",
    "dscg_dept_name": "",
    "ipt_days": "0.0",
    "adm_bed": "",
    "chfpdr_code": "",
    "chfpdr_name": "",
    "dise_no": "",
    "dise_name": "",
    "oprn_oprt_code": "",
    "oprn_oprt_name": "",
    "setl_id": "520100G0000627311318",
    "setl_time": "2024-03-02 21:07:33+08:00",
    "medfee_sumamt": "36.0",
    "hifp_pay": "0.0",
    "fund_pay_sumamt": "0.0",
    "acct_pay": "36.0",
    "cash_payamt": "0.0",
    "balc": "4974.47",
    "inscp_amt": "0.0",
    "hi_agre_sumfee": "36.0",
    "acct_mulaid_pay": "0.0",
    "bydise_setl_payamt": "0.0",
    "cvlserv_pay": "0.0",
    "maf_pay": "0.0",
    "year": "2024",
    "updt_time": "2024-03-02 21:08:00+08:00",
    "crte_time": "2024-03-02 21:08:00+08:00",
    "dwh_created_dt": "2024-03-02 21:07:33+08:00",
    "src_dt": "202403",
    "src_prv": "520100",
    "vali_flag": "1",
    "uyear": "2024",
    "uhalfyear": "1",
    "uquarter": "1",
    "umonth": "3",
    "uweek": "9",
    "prv": "",
    "city": "5201",
    "admdvs_code": "520199",
    "admdvs_name": "贵阳市市本级",
    "adm_caty": "",
    "inhosp_stas": "0",
    "refd_setl_flag": "0",
    "setl_type": "2",
    "fulamt_ownpay_amt": "36",
    "hifmi_pay": "0",
    "hifob_pay": "0",
    "hifdm_pay": "0",
    "othfund_pay": "0",
    "admdvs_district": "520199"
  },
  {
    "psn_no": "52000001000000003004108338",
    "psn_name": "",
    "gend": "1",
    "psn_cert_type": "01",
    "certno": "",
    "brdy": "1992-02-03 00:00:00+08:00",
    "age": "32.0",
    "psn_type": "11",
    "tel": "18613630353",
    "addr": "",
    "cvlserv_flag": "0",
    "cvlserv_lv": "",
    "sp_psn_type": "0",
    "sp_psn_type_lv": "",
    "insu_admdvs": "520199",
    "admdvs_prv": "520000",
    "admdvs_prvname": "贵州省",
    "admdvs_city": "520100",
    "admdvs_cityname": "贵阳市",
    "emp_no": "52000001000000000000001276",
    "emp_name": "贵州建工集团有限公司",
    "emp_type": "10",
    "econ_type": "170",
    "insutype": "310",
    "fixmedins_code": "z\fc�)�\u0007�\u000e�~����",
    "fixmedins_name": "�Lmi�nIpqq\u0019\b6<hI",
    "medinslv": "",
    "hosp_lv": "",
    "hosp_natu_code": "",
    "fix_blng_admdvs": "520114",
    "fix_blng_admdvs_city": "520100",
    "pay_loc": "2",
    "med_typecode": "41",
    "med_type": "定点药店购药",
    "med_bigtype": "门诊",
    "mdtrt_id": "520100G0001566957858",
    "ipt_otp_no": "",
    "start_date": "2024-03-04 21:32:36+08:00",
    "end_date": "2024-03-04 21:32:36+08:00",
    "adm_dept_code": "",
    "adm_dept_name": "",
    "dscg_dept_codg": "",
    "dscg_dept_name": "",
    "ipt_days": "0.0",
    "adm_bed": "",
    "chfpdr_code": "",
    "chfpdr_name": "",
    "dise_no": "",
    "dise_name": "",
    "oprn_oprt_code": "",
    "oprn_oprt_name": "",
    "setl_id": "520100G0000629148645",
    "setl_time": "2024-03-04 21:30:50+08:00",
    "medfee_sumamt": "30.0",
    "hifp_pay": "0.0",
    "fund_pay_sumamt": "0.0",
    "acct_pay": "30.0",
    "cash_payamt": "0.0",
    "balc": "4930.32",
    "inscp_amt": "30.0",
    "hi_agre_sumfee": "30.0",
    "acct_mulaid_pay": "0.0",
    "bydise_setl_payamt": "0.0",
    "cvlserv_pay": "0.0",
    "maf_pay": "0.0",
    "year": "2024",
    "updt_time": "2024-03-04 21:32:37+08:00",
    "crte_time": "2024-03-04 21:32:37+08:00",
    "dwh_created_dt": "2024-03-04 21:30:50+08:00",
    "src_dt": "202403",
    "src_prv": "520100",
    "vali_flag": "1",
    "uyear": "2024",
    "uhalfyear": "1",
    "uquarter": "1",
    "umonth": "3",
    "uweek": "10",
    "prv": "",
    "city": "5201",
    "admdvs_code": "520199",
    "admdvs_name": "贵阳市市本级",
    "adm_caty": "",
    "inhosp_stas": "0",
    "refd_setl_flag": "0",
    "setl_type": "2",
    "fulamt_ownpay_amt": "0",
    "hifmi_pay": "0",
    "hifob_pay": "0",
    "hifdm_pay": "0",
    "othfund_pay": "0",
    "admdvs_district": "520199"
  },
  {
    "psn_no": "52000001000000003004108338",
    "psn_name": "",
    "gend": "1",
    "psn_cert_type": "01",
    "certno": "",
    "brdy": "1992-02-03 00:00:00+08:00",
    "age": "32.0",
    "psn_type": "11",
    "tel": "18613630353",
    "addr": "",
    "cvlserv_flag": "0",
    "cvlserv_lv": "",
    "sp_psn_type": "0",
    "sp_psn_type_lv": "",
    "insu_admdvs": "520199",
    "admdvs_prv": "520000",
    "admdvs_prvname": "贵州省",
    "admdvs_city": "520100",
    "admdvs_cityname": "贵阳市",
    "emp_no": "52000001000000000000001276",
    "emp_name": "贵州建工集团有限公司",
    "emp_type": "10",
    "econ_type": "170",
    "insutype": "310",
    "fixmedins_code": "z\fc�)�\u0007�\u000e�~����",
    "fixmedins_name": "�Lmi�nIpqq\u0019\b6<hI",
    "medinslv": "",
    "hosp_lv": "",
    "hosp_natu_code": "",
    "fix_blng_admdvs": "520114",
    "fix_blng_admdvs_city": "520100",
    "pay_loc": "2",
    "med_typecode": "41",
    "med_type": "定点药店购药",
    "med_bigtype": "门诊",
    "mdtrt_id": "520100G0001573656397",
    "ipt_otp_no": "",
    "start_date": "2024-03-11 20:51:52+08:00",
    "end_date": "2024-03-11 20:51:52+08:00",
    "adm_dept_code": "",
    "adm_dept_name": "",
    "dscg_dept_codg": "",
    "dscg_dept_name": "",
    "ipt_days": "0.0",
    "adm_bed": "",
    "chfpdr_code": "",
    "chfpdr_name": "",
    "dise_no": "",
    "dise_name": "",
    "oprn_oprt_code": "",
    "oprn_oprt_name": "",
    "setl_id": "520100G0000635464774",
    "setl_time": "2024-03-11 20:49:51+08:00",
    "medfee_sumamt": "56.0",
    "hifp_pay": "0.0",
    "fund_pay_sumamt": "0.0",
    "acct_pay": "56.0",
    "cash_payamt": "0.0",
    "balc": "4738.56",
    "inscp_amt": "25.2",
    "hi_agre_sumfee": "56.0",
    "acct_mulaid_pay": "0.0",
    "bydise_setl_payamt": "0.0",
    "cvlserv_pay": "0.0",
    "maf_pay": "0.0",
    "year": "2024",
    "updt_time": "2024-03-11 20:51:54+08:00",
    "crte_time": "2024-03-11 20:51:54+08:00",
    "dwh_created_dt": "2024-03-11 20:49:51+08:00",
    "src_dt": "202403",
    "src_prv": "520100",
    "vali_flag": "1",
    "uyear": "2024",
    "uhalfyear": "1",
    "uquarter": "1",
    "umonth": "3",
    "uweek": "11",
    "prv": "",
    "city": "5201",
    "admdvs_code": "520199",
    "admdvs_name": "贵阳市市本级",
    "adm_caty": "",
    "inhosp_stas": "0",
    "refd_setl_flag": "0",
    "setl_type": "2",
    "fulamt_ownpay_amt": "28",
    "hifmi_pay": "0",
    "hifob_pay": "0",
    "hifdm_pay": "0",
    "othfund_pay": "0",
    "admdvs_district": "520199"
  }
]
```

---

## 表: `fqz_gz_jzsj_all_ql_clean`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| psn_no | String |  |
| psn_name | String |  |
| gend | String |  |
| psn_cert_type | String |  |
| certno | String |  |
| brdy | DateTime |  |
| age | Float64 |  |
| psn_type | String |  |
| tel | String |  |
| addr | String |  |
| cvlserv_flag | String |  |
| cvlserv_lv | String |  |
| sp_psn_type | String |  |
| sp_psn_type_lv | String |  |
| insu_admdvs | String |  |
| admdvs_prv | String |  |
| admdvs_prvname | String |  |
| admdvs_city | String |  |
| admdvs_cityname | String |  |
| emp_no | String |  |
| emp_name | String |  |
| emp_type | String |  |
| econ_type | String |  |
| insutype | String |  |
| fixmedins_code | String |  |
| fixmedins_name | String |  |
| medinslv | String |  |
| hosp_lv | String |  |
| hosp_natu_code | String |  |
| fix_blng_admdvs | String |  |
| fix_blng_admdvs_city | String |  |
| pay_loc | String |  |
| med_typecode | String |  |
| med_type | String |  |
| med_bigtype | String |  |
| mdtrt_id | String |  |
| ipt_otp_no | String |  |
| start_date | DateTime |  |
| end_date | DateTime |  |
| adm_dept_code | String |  |
| adm_dept_name | String |  |
| dscg_dept_codg | String |  |
| dscg_dept_name | String |  |
| ipt_days | String |  |
| adm_bed | String |  |
| chfpdr_code | String |  |
| chfpdr_name | String |  |
| dise_no | String |  |
| dise_name | String |  |
| oprn_oprt_code | String |  |
| oprn_oprt_name | String |  |
| setl_id | String |  |
| setl_time | DateTime |  |
| medfee_sumamt | Float64 |  |
| hifp_pay | Float64 |  |
| fund_pay_sumamt | Float64 |  |
| acct_pay | Float64 |  |
| cash_payamt | Float64 |  |
| balc | Float64 |  |
| inscp_amt | Float64 |  |
| hi_agre_sumfee | Float64 |  |
| acct_mulaid_pay | Float64 |  |
| bydise_setl_payamt | Float64 |  |
| cvlserv_pay | Float64 |  |
| maf_pay | Float64 |  |
| year | String |  |
| updt_time | DateTime |  |
| crte_time | DateTime |  |
| dwh_created_dt | DateTime |  |
| src_dt | String |  |
| src_prv | String |  |
| vali_flag | String |  |
| uyear | String |  |
| uhalfyear | String |  |
| uquarter | String |  |
| umonth | String |  |
| uweek | String |  |
| prv | String |  |
| city | String |  |
| admdvs_code | Int64 |  |
| admdvs_name | String |  |
| adm_caty | String |  |
| inhosp_stas | Int64 |  |
| refd_setl_flag | Int64 |  |
| setl_type | Int64 |  |
| fulamt_ownpay_amt | Int64 |  |
| hifmi_pay | Int64 |  |
| hifob_pay | Int64 |  |
| hifdm_pay | Int64 |  |
| othfund_pay | Int64 |  |
| admdvs_district | Int64 |  |

### 数据样例 (前3条)

```json
[
  {
    "psn_no": "52000001000000001000746581",
    "psn_name": "���\u0000Ĥ�Dd'\u001b�υk",
    "gend": "2",
    "psn_cert_type": "01",
    "certno": "y/ؒ\u0011�0\u0001\u0000��|��\u0016",
    "brdy": "1970-01-01 08:00:00+08:00",
    "age": "59.0",
    "psn_type": "12",
    "tel": "13195123798",
    "addr": "",
    "cvlserv_flag": "0",
    "cvlserv_lv": "",
    "sp_psn_type": "0",
    "sp_psn_type_lv": "",
    "insu_admdvs": "520199",
    "admdvs_prv": "520000",
    "admdvs_prvname": "贵州省",
    "admdvs_city": "520100",
    "admdvs_cityname": "贵阳市",
    "emp_no": "52000001000000000000028771",
    "emp_name": "中铁五局集团实业发展有限公司",
    "emp_type": "10",
    "econ_type": "110",
    "insutype": "310",
    "fixmedins_code": "T.�0����3k�U\u001c\u001cbr",
    "fixmedins_name": "1=��Jɭ���#bM\n��",
    "medinslv": "",
    "hosp_lv": "",
    "hosp_natu_code": "",
    "fix_blng_admdvs": "520102",
    "fix_blng_admdvs_city": "520100",
    "pay_loc": "2",
    "med_typecode": "41",
    "med_type": "定点药店购药",
    "med_bigtype": "门诊",
    "mdtrt_id": "520100G0001607236123",
    "ipt_otp_no": "",
    "start_date": "2024-04-19 20:53:54+08:00",
    "end_date": "2024-04-19 20:53:54+08:00",
    "adm_dept_code": "",
    "adm_dept_name": "",
    "dscg_dept_codg": "",
    "dscg_dept_name": "",
    "ipt_days": "0.0",
    "adm_bed": "",
    "chfpdr_code": "",
    "chfpdr_name": "",
    "dise_no": "",
    "dise_name": "",
    "oprn_oprt_code": "",
    "oprn_oprt_name": "",
    "setl_id": "520100G0000667514323",
    "setl_time": "2024-04-19 20:50:50+08:00",
    "medfee_sumamt": "36.6",
    "hifp_pay": "0.0",
    "fund_pay_sumamt": "0.0",
    "acct_pay": "36.6",
    "cash_payamt": "0.0",
    "balc": "359.23",
    "inscp_amt": "34.62",
    "hi_agre_sumfee": "36.6",
    "acct_mulaid_pay": "0.0",
    "bydise_setl_payamt": "0.0",
    "cvlserv_pay": "0.0",
    "maf_pay": "0.0",
    "year": "2024",
    "updt_time": "2024-04-19 20:53:55+08:00",
    "crte_time": "2024-04-19 20:53:55+08:00",
    "dwh_created_dt": "2024-04-19 20:50:50+08:00",
    "src_dt": "202404",
    "src_prv": "520100",
    "vali_flag": "1",
    "uyear": "2024",
    "uhalfyear": "1",
    "uquarter": "2",
    "umonth": "4",
    "uweek": "16",
    "prv": "",
    "city": "5201",
    "admdvs_code": "520199",
    "admdvs_name": "贵阳市市本级",
    "adm_caty": "",
    "inhosp_stas": "0",
    "refd_setl_flag": "0",
    "setl_type": "2",
    "fulamt_ownpay_amt": "0",
    "hifmi_pay": "0",
    "hifob_pay": "0",
    "hifdm_pay": "0",
    "othfund_pay": "0",
    "admdvs_district": "520199"
  },
  {
    "psn_no": "52000001000000001000746581",
    "psn_name": "���\u0000Ĥ�Dd'\u001b�υk",
    "gend": "2",
    "psn_cert_type": "01",
    "certno": "y/ؒ\u0011�0\u0001\u0000��|��\u0016",
    "brdy": "1970-01-01 08:00:00+08:00",
    "age": "59.0",
    "psn_type": "12",
    "tel": "13195123798",
    "addr": "",
    "cvlserv_flag": "0",
    "cvlserv_lv": "",
    "sp_psn_type": "0",
    "sp_psn_type_lv": "",
    "insu_admdvs": "520199",
    "admdvs_prv": "520000",
    "admdvs_prvname": "贵州省",
    "admdvs_city": "520100",
    "admdvs_cityname": "贵阳市",
    "emp_no": "52000001000000000000028771",
    "emp_name": "中铁五局集团实业发展有限公司",
    "emp_type": "10",
    "econ_type": "110",
    "insutype": "310",
    "fixmedins_code": "T.�0����3k�U\u001c\u001cbr",
    "fixmedins_name": "1=��Jɭ���#bM\n��",
    "medinslv": "",
    "hosp_lv": "",
    "hosp_natu_code": "",
    "fix_blng_admdvs": "520102",
    "fix_blng_admdvs_city": "520100",
    "pay_loc": "2",
    "med_typecode": "41",
    "med_type": "定点药店购药",
    "med_bigtype": "门诊",
    "mdtrt_id": "520100G0001607236123",
    "ipt_otp_no": "",
    "start_date": "2024-04-19 20:53:54+08:00",
    "end_date": "2024-04-19 20:53:54+08:00",
    "adm_dept_code": "",
    "adm_dept_name": "",
    "dscg_dept_codg": "",
    "dscg_dept_name": "",
    "ipt_days": "0.0",
    "adm_bed": "",
    "chfpdr_code": "",
    "chfpdr_name": "",
    "dise_no": "",
    "dise_name": "",
    "oprn_oprt_code": "",
    "oprn_oprt_name": "",
    "setl_id": "520100G0000667514323",
    "setl_time": "2024-04-19 20:50:50+08:00",
    "medfee_sumamt": "36.6",
    "hifp_pay": "0.0",
    "fund_pay_sumamt": "0.0",
    "acct_pay": "36.6",
    "cash_payamt": "0.0",
    "balc": "359.23",
    "inscp_amt": "34.62",
    "hi_agre_sumfee": "36.6",
    "acct_mulaid_pay": "0.0",
    "bydise_setl_payamt": "0.0",
    "cvlserv_pay": "0.0",
    "maf_pay": "0.0",
    "year": "2024",
    "updt_time": "2024-04-19 20:53:55+08:00",
    "crte_time": "2024-04-19 20:53:55+08:00",
    "dwh_created_dt": "2024-04-19 20:50:50+08:00",
    "src_dt": "202404",
    "src_prv": "520100",
    "vali_flag": "1",
    "uyear": "2024",
    "uhalfyear": "1",
    "uquarter": "2",
    "umonth": "4",
    "uweek": "16",
    "prv": "",
    "city": "5201",
    "admdvs_code": "520199",
    "admdvs_name": "贵阳市市本级",
    "adm_caty": "",
    "inhosp_stas": "0",
    "refd_setl_flag": "0",
    "setl_type": "2",
    "fulamt_ownpay_amt": "0",
    "hifmi_pay": "0",
    "hifob_pay": "0",
    "hifdm_pay": "0",
    "othfund_pay": "0",
    "admdvs_district": "520199"
  },
  {
    "psn_no": "52000001000000001000746581",
    "psn_name": "���\u0000Ĥ�Dd'\u001b�υk",
    "gend": "2",
    "psn_cert_type": "01",
    "certno": "y/ؒ\u0011�0\u0001\u0000��|��\u0016",
    "brdy": "1970-01-01 08:00:00+08:00",
    "age": "59.0",
    "psn_type": "12",
    "tel": "13195123798",
    "addr": "",
    "cvlserv_flag": "0",
    "cvlserv_lv": "",
    "sp_psn_type": "0",
    "sp_psn_type_lv": "",
    "insu_admdvs": "520199",
    "admdvs_prv": "520000",
    "admdvs_prvname": "贵州省",
    "admdvs_city": "520100",
    "admdvs_cityname": "贵阳市",
    "emp_no": "52000001000000000000028771",
    "emp_name": "中铁五局集团实业发展有限公司",
    "emp_type": "10",
    "econ_type": "110",
    "insutype": "310",
    "fixmedins_code": "T.�0����3k�U\u001c\u001cbr",
    "fixmedins_name": "1=��Jɭ���#bM\n��",
    "medinslv": "",
    "hosp_lv": "",
    "hosp_natu_code": "",
    "fix_blng_admdvs": "520102",
    "fix_blng_admdvs_city": "520100",
    "pay_loc": "2",
    "med_typecode": "41",
    "med_type": "定点药店购药",
    "med_bigtype": "门诊",
    "mdtrt_id": "520100G0001607236123",
    "ipt_otp_no": "",
    "start_date": "2024-04-19 20:53:54+08:00",
    "end_date": "2024-04-19 20:53:54+08:00",
    "adm_dept_code": "",
    "adm_dept_name": "",
    "dscg_dept_codg": "",
    "dscg_dept_name": "",
    "ipt_days": "0.0",
    "adm_bed": "",
    "chfpdr_code": "",
    "chfpdr_name": "",
    "dise_no": "",
    "dise_name": "",
    "oprn_oprt_code": "",
    "oprn_oprt_name": "",
    "setl_id": "520100G0000667514323",
    "setl_time": "2024-04-19 20:50:50+08:00",
    "medfee_sumamt": "36.6",
    "hifp_pay": "0.0",
    "fund_pay_sumamt": "0.0",
    "acct_pay": "36.6",
    "cash_payamt": "0.0",
    "balc": "359.23",
    "inscp_amt": "34.62",
    "hi_agre_sumfee": "36.6",
    "acct_mulaid_pay": "0.0",
    "bydise_setl_payamt": "0.0",
    "cvlserv_pay": "0.0",
    "maf_pay": "0.0",
    "year": "2024",
    "updt_time": "2024-04-19 20:53:55+08:00",
    "crte_time": "2024-04-19 20:53:55+08:00",
    "dwh_created_dt": "2024-04-19 20:50:50+08:00",
    "src_dt": "202404",
    "src_prv": "520100",
    "vali_flag": "1",
    "uyear": "2024",
    "uhalfyear": "1",
    "uquarter": "2",
    "umonth": "4",
    "uweek": "16",
    "prv": "",
    "city": "5201",
    "admdvs_code": "520199",
    "admdvs_name": "贵阳市市本级",
    "adm_caty": "",
    "inhosp_stas": "0",
    "refd_setl_flag": "0",
    "setl_type": "2",
    "fulamt_ownpay_amt": "0",
    "hifmi_pay": "0",
    "hifob_pay": "0",
    "hifdm_pay": "0",
    "othfund_pay": "0",
    "admdvs_district": "520199"
  }
]
```

---

## 表: `fqz_gz_jzsj_all_ql_fixed`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| psn_no | String |  |
| psn_name | String |  |
| gend | String |  |
| psn_cert_type | String |  |
| certno | String |  |
| brdy | DateTime |  |
| age | Float64 |  |
| psn_type | String |  |
| tel | String |  |
| addr | String |  |
| cvlserv_flag | String |  |
| cvlserv_lv | String |  |
| sp_psn_type | String |  |
| sp_psn_type_lv | String |  |
| insu_admdvs | String |  |
| admdvs_prv | String |  |
| admdvs_prvname | String |  |
| admdvs_city | String |  |
| admdvs_cityname | String |  |
| emp_no | String |  |
| emp_name | String |  |
| emp_type | String |  |
| econ_type | String |  |
| insutype | String |  |
| fixmedins_code | String |  |
| fixmedins_name | String |  |
| medinslv | String |  |
| hosp_lv | String |  |
| hosp_natu_code | String |  |
| fix_blng_admdvs | String |  |
| fix_blng_admdvs_city | String |  |
| pay_loc | String |  |
| med_typecode | String |  |
| med_type | String |  |
| med_bigtype | String |  |
| mdtrt_id | String |  |
| ipt_otp_no | String |  |
| start_date | DateTime |  |
| end_date | DateTime |  |
| adm_dept_code | String |  |
| adm_dept_name | String |  |
| dscg_dept_codg | String |  |
| dscg_dept_name | String |  |
| ipt_days | String |  |
| adm_bed | String |  |
| chfpdr_code | String |  |
| chfpdr_name | String |  |
| dise_no | String |  |
| dise_name | String |  |
| oprn_oprt_code | String |  |
| oprn_oprt_name | String |  |
| setl_id | String |  |
| setl_time | DateTime |  |
| medfee_sumamt | Float64 |  |
| hifp_pay | Float64 |  |
| fund_pay_sumamt | Float64 |  |
| acct_pay | Float64 |  |
| cash_payamt | Float64 |  |
| balc | Float64 |  |
| inscp_amt | Float64 |  |
| hi_agre_sumfee | Float64 |  |
| acct_mulaid_pay | Float64 |  |
| bydise_setl_payamt | Float64 |  |
| cvlserv_pay | Float64 |  |
| maf_pay | Float64 |  |
| year | String |  |
| updt_time | DateTime |  |
| crte_time | DateTime |  |
| dwh_created_dt | DateTime |  |
| src_dt | String |  |
| src_prv | String |  |
| vali_flag | String |  |
| uyear | String |  |
| uhalfyear | String |  |
| uquarter | String |  |
| umonth | String |  |
| uweek | String |  |
| prv | String |  |
| city | String |  |
| admdvs_code | Int64 |  |
| admdvs_name | String |  |
| adm_caty | String |  |
| inhosp_stas | Int64 |  |
| refd_setl_flag | Int64 |  |
| setl_type | Int64 |  |
| fulamt_ownpay_amt | Int64 |  |
| hifmi_pay | Int64 |  |
| hifob_pay | Int64 |  |
| hifdm_pay | Int64 |  |
| othfund_pay | Int64 |  |
| admdvs_district | Int64 |  |

### 数据样例 (前3条)

```json
[
  {
    "psn_no": "52000001000000003004108338",
    "psn_name": "",
    "gend": "1",
    "psn_cert_type": "01",
    "certno": "",
    "brdy": "1992-02-03 00:00:00+08:00",
    "age": "32.0",
    "psn_type": "11",
    "tel": "18613630353",
    "addr": "",
    "cvlserv_flag": "0",
    "cvlserv_lv": "",
    "sp_psn_type": "0",
    "sp_psn_type_lv": "",
    "insu_admdvs": "520199",
    "admdvs_prv": "520000",
    "admdvs_prvname": "贵州省",
    "admdvs_city": "520100",
    "admdvs_cityname": "贵阳市",
    "emp_no": "52000001000000000000001276",
    "emp_name": "贵州建工集团有限公司",
    "emp_type": "10",
    "econ_type": "170",
    "insutype": "310",
    "fixmedins_code": "z\fc�)�\u0007�\u000e�~����",
    "fixmedins_name": "�Lmi�nIpqq\u0019\b6<hI",
    "medinslv": "",
    "hosp_lv": "",
    "hosp_natu_code": "",
    "fix_blng_admdvs": "520114",
    "fix_blng_admdvs_city": "520100",
    "pay_loc": "2",
    "med_typecode": "41",
    "med_type": "定点药店购药",
    "med_bigtype": "门诊",
    "mdtrt_id": "520100G0001566957858",
    "ipt_otp_no": "",
    "start_date": "2024-03-04 21:32:36+08:00",
    "end_date": "2024-03-04 21:32:36+08:00",
    "adm_dept_code": "",
    "adm_dept_name": "",
    "dscg_dept_codg": "",
    "dscg_dept_name": "",
    "ipt_days": "0.0",
    "adm_bed": "",
    "chfpdr_code": "",
    "chfpdr_name": "",
    "dise_no": "",
    "dise_name": "",
    "oprn_oprt_code": "",
    "oprn_oprt_name": "",
    "setl_id": "520100G0000629148645",
    "setl_time": "2024-03-04 21:30:50+08:00",
    "medfee_sumamt": "30.0",
    "hifp_pay": "0.0",
    "fund_pay_sumamt": "0.0",
    "acct_pay": "30.0",
    "cash_payamt": "0.0",
    "balc": "4930.32",
    "inscp_amt": "30.0",
    "hi_agre_sumfee": "30.0",
    "acct_mulaid_pay": "0.0",
    "bydise_setl_payamt": "0.0",
    "cvlserv_pay": "0.0",
    "maf_pay": "0.0",
    "year": "2024",
    "updt_time": "2024-03-04 21:32:37+08:00",
    "crte_time": "2024-03-04 21:32:37+08:00",
    "dwh_created_dt": "2024-03-04 21:30:50+08:00",
    "src_dt": "202403",
    "src_prv": "520100",
    "vali_flag": "1",
    "uyear": "2024",
    "uhalfyear": "1",
    "uquarter": "1",
    "umonth": "3",
    "uweek": "10",
    "prv": "",
    "city": "5201",
    "admdvs_code": "520199",
    "admdvs_name": "贵阳市市本级",
    "adm_caty": "",
    "inhosp_stas": "0",
    "refd_setl_flag": "0",
    "setl_type": "2",
    "fulamt_ownpay_amt": "0",
    "hifmi_pay": "0",
    "hifob_pay": "0",
    "hifdm_pay": "0",
    "othfund_pay": "0",
    "admdvs_district": "520199"
  },
  {
    "psn_no": "52000001000000003004108338",
    "psn_name": "",
    "gend": "1",
    "psn_cert_type": "01",
    "certno": "",
    "brdy": "1992-02-03 00:00:00+08:00",
    "age": "32.0",
    "psn_type": "11",
    "tel": "18613630353",
    "addr": "",
    "cvlserv_flag": "0",
    "cvlserv_lv": "",
    "sp_psn_type": "0",
    "sp_psn_type_lv": "",
    "insu_admdvs": "520199",
    "admdvs_prv": "520000",
    "admdvs_prvname": "贵州省",
    "admdvs_city": "520100",
    "admdvs_cityname": "贵阳市",
    "emp_no": "52000001000000000000001276",
    "emp_name": "贵州建工集团有限公司",
    "emp_type": "10",
    "econ_type": "170",
    "insutype": "310",
    "fixmedins_code": "z\fc�)�\u0007�\u000e�~����",
    "fixmedins_name": "�Lmi�nIpqq\u0019\b6<hI",
    "medinslv": "",
    "hosp_lv": "",
    "hosp_natu_code": "",
    "fix_blng_admdvs": "520114",
    "fix_blng_admdvs_city": "520100",
    "pay_loc": "2",
    "med_typecode": "41",
    "med_type": "定点药店购药",
    "med_bigtype": "门诊",
    "mdtrt_id": "520100G0001573656397",
    "ipt_otp_no": "",
    "start_date": "2024-03-11 20:51:52+08:00",
    "end_date": "2024-03-11 20:51:52+08:00",
    "adm_dept_code": "",
    "adm_dept_name": "",
    "dscg_dept_codg": "",
    "dscg_dept_name": "",
    "ipt_days": "0.0",
    "adm_bed": "",
    "chfpdr_code": "",
    "chfpdr_name": "",
    "dise_no": "",
    "dise_name": "",
    "oprn_oprt_code": "",
    "oprn_oprt_name": "",
    "setl_id": "520100G0000635464774",
    "setl_time": "2024-03-11 20:49:51+08:00",
    "medfee_sumamt": "56.0",
    "hifp_pay": "0.0",
    "fund_pay_sumamt": "0.0",
    "acct_pay": "56.0",
    "cash_payamt": "0.0",
    "balc": "4738.56",
    "inscp_amt": "25.2",
    "hi_agre_sumfee": "56.0",
    "acct_mulaid_pay": "0.0",
    "bydise_setl_payamt": "0.0",
    "cvlserv_pay": "0.0",
    "maf_pay": "0.0",
    "year": "2024",
    "updt_time": "2024-03-11 20:51:54+08:00",
    "crte_time": "2024-03-11 20:51:54+08:00",
    "dwh_created_dt": "2024-03-11 20:49:51+08:00",
    "src_dt": "202403",
    "src_prv": "520100",
    "vali_flag": "1",
    "uyear": "2024",
    "uhalfyear": "1",
    "uquarter": "1",
    "umonth": "3",
    "uweek": "11",
    "prv": "",
    "city": "5201",
    "admdvs_code": "520199",
    "admdvs_name": "贵阳市市本级",
    "adm_caty": "",
    "inhosp_stas": "0",
    "refd_setl_flag": "0",
    "setl_type": "2",
    "fulamt_ownpay_amt": "28",
    "hifmi_pay": "0",
    "hifob_pay": "0",
    "hifdm_pay": "0",
    "othfund_pay": "0",
    "admdvs_district": "520199"
  },
  {
    "psn_no": "52000001000000003004108338",
    "psn_name": "",
    "gend": "1",
    "psn_cert_type": "01",
    "certno": "",
    "brdy": "1992-02-03 00:00:00+08:00",
    "age": "32.0",
    "psn_type": "11",
    "tel": "18613630353",
    "addr": "",
    "cvlserv_flag": "0",
    "cvlserv_lv": "",
    "sp_psn_type": "0",
    "sp_psn_type_lv": "",
    "insu_admdvs": "520199",
    "admdvs_prv": "520000",
    "admdvs_prvname": "贵州省",
    "admdvs_city": "520100",
    "admdvs_cityname": "贵阳市",
    "emp_no": "52000001000000000000001276",
    "emp_name": "贵州建工集团有限公司",
    "emp_type": "10",
    "econ_type": "170",
    "insutype": "310",
    "fixmedins_code": "z\fc�)�\u0007�\u000e�~����",
    "fixmedins_name": "�Lmi�nIpqq\u0019\b6<hI",
    "medinslv": "",
    "hosp_lv": "",
    "hosp_natu_code": "",
    "fix_blng_admdvs": "520114",
    "fix_blng_admdvs_city": "520100",
    "pay_loc": "2",
    "med_typecode": "41",
    "med_type": "定点药店购药",
    "med_bigtype": "门诊",
    "mdtrt_id": "520100G0001565001062",
    "ipt_otp_no": "",
    "start_date": "2024-03-02 21:07:58+08:00",
    "end_date": "2024-03-02 21:07:58+08:00",
    "adm_dept_code": "",
    "adm_dept_name": "",
    "dscg_dept_codg": "",
    "dscg_dept_name": "",
    "ipt_days": "0.0",
    "adm_bed": "",
    "chfpdr_code": "",
    "chfpdr_name": "",
    "dise_no": "",
    "dise_name": "",
    "oprn_oprt_code": "",
    "oprn_oprt_name": "",
    "setl_id": "520100G0000627311318",
    "setl_time": "2024-03-02 21:07:33+08:00",
    "medfee_sumamt": "36.0",
    "hifp_pay": "0.0",
    "fund_pay_sumamt": "0.0",
    "acct_pay": "36.0",
    "cash_payamt": "0.0",
    "balc": "4974.47",
    "inscp_amt": "0.0",
    "hi_agre_sumfee": "36.0",
    "acct_mulaid_pay": "0.0",
    "bydise_setl_payamt": "0.0",
    "cvlserv_pay": "0.0",
    "maf_pay": "0.0",
    "year": "2024",
    "updt_time": "2024-03-02 21:08:00+08:00",
    "crte_time": "2024-03-02 21:08:00+08:00",
    "dwh_created_dt": "2024-03-02 21:07:33+08:00",
    "src_dt": "202403",
    "src_prv": "520100",
    "vali_flag": "1",
    "uyear": "2024",
    "uhalfyear": "1",
    "uquarter": "1",
    "umonth": "3",
    "uweek": "9",
    "prv": "",
    "city": "5201",
    "admdvs_code": "520199",
    "admdvs_name": "贵阳市市本级",
    "adm_caty": "",
    "inhosp_stas": "0",
    "refd_setl_flag": "0",
    "setl_type": "2",
    "fulamt_ownpay_amt": "36",
    "hifmi_pay": "0",
    "hifob_pay": "0",
    "hifdm_pay": "0",
    "othfund_pay": "0",
    "admdvs_district": "520199"
  }
]
```

---

## 表: `fqz_ptzy_hosp`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| setl_rq | String |  |
| fixmedins_code | String |  |
| fixmedins_name | String |  |
| medinslv | String |  |
| medins_natu | String |  |
| provice_code | String |  |
| admdvs | String |  |
| medfee_sumamt | Decimal(18, 2) |  |
| fund_pay_sumamt | Decimal(18, 2) |  |
| acct_pay | Decimal(18, 2) |  |
| cash_payamt | Decimal(18, 2) |  |
| ipt_days_hj | Int64 |  |
| crt_time | DateTime |  |

### 数据样例 (前3条)

```json
[
  {
    "setl_rq": "202604",
    "fixmedins_code": "H005",
    "fixmedins_name": "广州中医药大学第一附属医院",
    "medinslv": "3",
    "medins_natu": "1",
    "provice_code": "440000",
    "admdvs": "440100",
    "medfee_sumamt": "800.00",
    "fund_pay_sumamt": "500.00",
    "acct_pay": "100.00",
    "cash_payamt": "200.00",
    "ipt_days_hj": "45",
    "crt_time": "2026-04-02 03:17:13+08:00"
  }
]
```

---

## 表: `fqz_ztk_psn_yearly`

### 字段定义

| 字段名 | 类型 | 注释 |
| :--- | :--- | :--- |
| setl_rq | String |  |
| certno | String |  |
| psn_name | String |  |
| admdvs | String |  |
| provice_code | String |  |
| jzcs | Int32 |  |
| jzcs_zy | Int32 |  |
| medfee_sumamt | Decimal(18, 2) |  |
| fund_pay_sumamt | Decimal(18, 2) |  |
| acct_pay | Decimal(18, 2) |  |
| cash_payamt | Decimal(18, 2) |  |
| ipt_days_hj | Int64 |  |
| crt_time | DateTime |  |

### 数据样例 (前3条)

```json
[
  {
    "setl_rq": "202604",
    "certno": "440100198001011234",
    "psn_name": "李四 (可疑进常客)",
    "admdvs": "440100",
    "provice_code": "440000",
    "jzcs": "15",
    "jzcs_zy": "5",
    "medfee_sumamt": "80000.00",
    "fund_pay_sumamt": "60000.00",
    "acct_pay": "5000.00",
    "cash_payamt": "15000.00",
    "ipt_days_hj": "20",
    "crt_time": "2026-04-02 03:17:13+08:00"
  }
]
```

---

