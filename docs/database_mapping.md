# 🏥 医疗审计数据库：全域业务语义字典 (v1.0)

本指南旨在揭示 ClickHouse 数据库中 `fqz_` 前缀相关表的物理结构与其背后隐含的 **医疗保障审计** 业务逻辑。

---

## 🏗️ 命名规范指引 (Naming Convention)

为了提高 Agent 和开发者的理解效率，本库遵循以下缩写规范：
- `fqz_`: **F**raud/Audit (欺诈审计/医疗审计前缀)
- `tcq`: **T**ong **C**hou **Q**v (统筹区)
- `admdvs`: **Adm**inistrative **D**i**v**i**s**ions (行政区划)
- `jzdlb`: **J**iu **Z**hen **D**a **L**ei **B**ie (就诊类别：住院、门诊等)
- `xzlb`: **X**ian **Z**hong **L**ei **B**ie (险种类别：城乡居民、城镇职工等)
- `yydj`: **Y**i **Y**uan **D**eng **J**i (医院等级：三甲、二甲等)
- `yyxz`: **Y**i **Y**uan **X**ing **Z**hi (医院性质：公立、民营)
- `cgzhan`: **C**hao **G**uo **Zhan** (占比/产出占比统计)

---

## 1. 📂 结算核心域 (Settlement Core)
包含最细颗粒度的就诊结算明细，是所有审计分析的数据源头。

### `fqz_all_yy_yd_1` (核心结算宽表)
**功能描述**：全量医保结算流水，包含患者、机构、费用的全维信息。

| 字段名 | 业务语义 | 说明 |
| :--- | :--- | :--- |
| fixmedins_code | 定点医疗机构代码 | 医院的唯一标识 |
| fixmedins_name | 医疗机构名称 | 医院的名称 |
| psn_no | 个人编号 | 患者/参保人的唯一脱敏 ID |
| medfee_sumamt | 医疗总费用 | 本次就诊的总金额 |
| fund_pay_sumamt | 统筹基金支付 | 医保报销的大头部分 |
| setl_time | 结算日期/时间 | 该笔费用入账的时间点 |

---

## 2. 📂 采购/产出占比统计域 (Aggregation & Share Statistics)
这部分表以 `fqz_cgzhan_` 为前缀，主要用于统计不同维度的基金占用和业务量占比。

### `fqz_cgzhan_hosp` (医院维度占比统计)
**功能描述**：按医院统计的各类指标汇总，用于横向比较。

| 字段名 | 业务语义 | 说明 |
| :--- | :--- | :--- |
| sum_hifp_pay | 统筹支付总额 | 汇总的医保报销金额 |
| sum_acct_pay | 个人账户支付总额 | 医保卡余额支付部分 |
| sum_cash_payamt | 个人现金支付 | 患者自掏腰包的部分 |
| sum_inscp_amt | 政策内金额 | 符合医保报销目录的费用总计 |
| vix | 离散度/波动指标 | 用于衡量该院数据是否偏离平均值 |

---

## 💡 使用指南
- **Agent 推演**：通过在 Prompt 中指定本字典，Agent 将能准确执行 `SELECT sum(sum_hifp_pay) FROM fqz_cgzhan_tcq WHERE admdvs_name = '贵阳市'`。
- **关联路径**：大部分表通过 `admdvs` 或 `fixmedins_code` 实现关联。
