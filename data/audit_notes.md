# 🛡️ Argus 智能体审计外部便签簿 (Structured Audit Notes)
> 本便签簿由智能体在多轮 ReAct 交互中自主维护，用于跨上下文窗口重建时固化关键状态与证据。
>
> ⚠️ **时间衰减策略**：便签超过 30 天自动降权 50%，超过 90 天自动降权 80%，历史便签仅供参考，不作为当前查询的强制模板。

---
## 📌 [TIME_DECAY_CONFIG]
- default_ttl_days: 30
- decay_factor_30d: 0.5
- decay_factor_90d: 0.2
- max_notes_per_session: 10

---

## 📌 [SQL_EVIDENCE] - 2026-06-20 03:00:00
【便签清空说明】
由于历史便签中存在错误的 SQL 模式（如 GROUP BY medfee_sumamt），已执行清空操作。
后续便签写入时将自动附带 TTL 标记，避免过时错误模板污染新查询。

---## 📌 [SQL_EVIDENCE] - 2026-06-20 20:27:48
> TTL: 30天 | 过期日期: 2026-07-20

成功执行核心审计 SQL，筛选出最近 5 年单次结算金额高于 P95 分位数的异常案件，并统计各医院和患者出现大额结算的次数。SQL 语句：WITH p95 AS (SELECT quantile(0.95)(medfee_sumamt) FROM fqz_gz_jzsj_all_ql WHERE setl_time >= subtractYears(today(), 5)) SELECT psn_no, psn_name, fixmedins_code, fixmedins_name, medfee_sumamt, setl_id, setl_time, COUNT(*) OVER (PARTITION BY psn_no) AS patient_high_amount_count, COUNT(*) OVER (PARTITION BY fixmedins_code) AS hospital_high_amount_count FROM fqz_gz_jzsj_all_ql WHERE medfee_sumamt > (SELECT * FROM p95) AND setl_time >= subtractYears(today(), 5) ORDER BY medfee_sumamt DESC LIMIT 100

---

## 📌 [SQL_EVIDENCE] - 2026-06-20 21:17:34
> TTL: 30天 | 过期日期: 2026-07-20

成功执行核心审计 SQL，筛选出最近 5 年的结算数据，按单次结算金额从高到低排序，并统计各医院和患者出现大额结算的次数。SQL 语句：SELECT psn_no, psn_name, fixmedins_code, fixmedins_name, medfee_sumamt, setl_id, setl_time, COUNT(*) OVER (PARTITION BY psn_no) AS patient_high_amount_count, COUNT(*) OVER (PARTITION BY fixmedins_code) AS hospital_high_amount_count FROM fqz_gz_jzsj_all_ql WHERE setl_time >= subtractYears(today(), 5) ORDER BY medfee_sumamt DESC LIMIT 100

---

## 📌 [SQL_EVIDENCE] - 2026-06-20 21:29:23
> TTL: 30天 | 过期日期: 2026-07-20

成功执行核心审计 SQL，筛选出最近 5 年的结算数据，按单次结算金额从高到低排序，获取单次结算金额排名最高的案件。SQL 语句：SELECT psn_no, psn_name, fixmedins_code, fixmedins_name, medfee_sumamt, setl_id, setl_time FROM fqz_gz_jzsj_all_ql WHERE setl_time >= subtractYears(today(), 5) ORDER BY medfee_sumamt DESC LIMIT 100

---

