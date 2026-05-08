# 📚 HSA 医疗审计经验库 (Cognitive Export)
**导出时间**: 鍛ㄤ簲 2026/05/01
**总案例数**: 1

---

### 案例 1: 重复收费审计
**审计逻辑/SQL模板**:
```sql
审计经验：针对重复收费（如同一天多次结算），应使用以下 SQL 逻辑：
SELECT psn_no, setl_time, count(*) as cnt FROM fqz_gz_jzsj_all_ql GROUP BY psn_no, setl_time HAVING cnt > 1. 
核心证据：PSN_NO 是患者唯一标识，SETL_TIME 是结算日期。
```
**元数据**: `{'topic': '重复收费审计'}`

---
