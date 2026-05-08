# 📜 医疗审计数据库：全域 32 表业务百科索引 (v3.0)

本指南针对 ClickHouse `fqz_` 系列数据库进行 **地毯式解析**。涵盖了从核心流水到治理过程表的所有 32 个物理条目，旨在为 Agent 推演和离案审计提供 100% 的语义支撑。

---

## 🏛️ 通用业务指标字典 (Global Glossary)
在所有具备财务属性的表中，以下缩写遵循统一的医疗保障审计业务定义：

- **`hifp` (HIFP)**: **统筹基金支付**。医保报销的核心资金，审计骗保、套取基金的主要监控对象。
- **`acct`**: **个人账户支付**。参保人医保卡内的余额支付。
- **`cash`**: **个人现金支付**。患者自掏腰包的纯现金支出。
- **`maf` (MAF)**: **医疗救助支付**。针对贫困、残疾等特殊人群的补偿性资金。
- **`cvlserv`**: **公务员补助**。
- **`inscp` (In-Scope)**: **政策内费用**。符合医保“三大目录”规定可报销的费用基数。
- **`hi_agre`**: **合规费用**。经过前置审核后确认为真实的就医费用总计。
- **`vix` (Variation Index)**: **离散系数/变异指数**。标志该指标与统筹区均值的偏离度，`vix > 1` 通常意味着异常增长风险。

---

## 📂 核心域 A：结算流水资产 (Core Settlement)
包含最细颗粒度的原始记录，是所有分析的“发源地”。

### 1. `fqz_all_yy_yd_1` - 全量结算明细快照表
系统中颗粒度较粗的统计快照，常用于医院维度的快速费用审计。
> [!CAUTION]
> **物理限制**：由于该表不包含 `psn_no` 字段，**严禁**使用此表进行患者维度的跨院/跨期行为审计。

| 物理字段 | 业务含义 | 类型 | 审计注意点 |
| :--- | :--- | :--- | :--- |
| `fixmedins_code` | 医院编码 | String | 该表的 Order By 键，过滤性能极佳。 |
| `medfee_sumamt` | 医疗总额 | Decimal | 建议使用 toFloat64() 进行跨表计算。 |
| `setl_time` | 结算日期 | DateTime | 物理类型为原生 DateTime。 |

### 2. `fqz_gz_jzsj_all_ql` - 原始就诊全库
18GB 生产数据的主要落仓点。这是审计的“原始物证”。

| 物理字段 | 业务含义 | 类型 | 核心审计意义 |
| :--- | :--- | :--- | :--- |
| `psn_no` | 参保人编号 | String | 用于跨年度、跨地域追踪同一患者的就医行为。 |
| `psn_name` | 姓名 | String | 患者实名信息。 |
| `gend` | 性别 | String | 审计特定病种（如男性结算妇科检查）的违规逻辑。 |
| `certno` | 身份证号 | String | 唯一身份标志，识别虚假开户。 |
| `brdy` | 出生日期 | String | |
| `age` | 年龄 | String | 识别“老药新开”或儿童医保滥用。 |
| `psn_type` | 人员类别 | String | 区分职工、居民、灵活就业人员，审计待遇差额。 |
| `insutype` | 险种类型 | String | 区分基本医疗、大病补等。 |
| `fixmedins_code` | 医院编码 | String | 审计的核心主体锚点。 |
| `fixmedins_name` | 医院名称 | String | |
| `hosp_lv` | 医院等级 | String | 关联起步线、报销比例。 |
| `med_type` | 医疗类别 | String | 区分门诊、住院、药店刷卡。 |
| `start_date` | 入院日期 | String/DateTime | **[类型碎片化]**：在 default 库中为 String，需强制转换。 |
| `end_date` | 出院日期 | String/DateTime | |
| `ipt_days` | 住院天数 | String | **[物理陷阱]**：全域 String，SUM 前必须 toInt32OrZero()。 |
| `dise_name` | 诊断名称 | String | 审计“高套编码”的关键：对比收费明细与病情诊断。 |
| `medfee_sumamt` | 总医疗费 | Float64 | 本次结算的总账单。 |
| `hifp_pay` | 统筹基金支付 | Float64 | **审计重灾区**：医保报销出的真实资金。 |
| `fund_pay_sumamt` | 报销总额 | Float64 | 包含统筹及各类补助的总和。 |
| `acct_pay` | 个人账户支付 | Float64 | |
| `cash_payamt` | 个人现金自付 | Float64 | |
| `crte_time` | 入库时间 | DateTime | 系统结算的时间戳。 |

> [!TIP]
> 上表仅列出核心高频字段。该表物理上包含 93 个字段，涵盖了行政区划（`admdvs_code`）、科室信息（`adm_dept_name`）及异地标识（`pay_loc`）等全量细节。

### 3. `fqz_gz_jzsj_all_ql_clean / _fixed`
- **定位**：这两张表是 `ql` 表在数据采集过程中的物理快照。
- **解析逻辑**：其字段定义与 `fqz_gz_jzsj_all_ql` **完全一致**。
- **业务价值**：用于比对数据清洗前后（如日期格式修正）的记录完整性，防止数据在入库时被“吃掉”。

---

## 📂 核心域 B：产出统计分析 (CGZHAN - Production Stats)
本区域包含 17 张预聚合表，是审计报表和图表展示的核心数据源。

### 1. 命名维度解码 (Dimensional Decoding)
所有的 `cgzhan_` 表通过后缀组合来定义其统计深度：
- **`tcq`**: 统筹区 (Medical Insurance District)
- **`xzlb`**: 险种类别 (职工/居民)
- **`jzdlb`**: 就诊大类别 (门诊/住院)
- **`yydj`**: 医院等级 (三级/二级/一级)
- **`yyxz`**: 医院性质 (公立/民营)

### 2. 17张统计表全景对位表
| 表名 | 统计维度 (Dimensions) | 核心用途 |
| :--- | :--- | :--- |
| `fqz_cgzhan_hosp` | 医院 | 医院综合能力与负担分析 |
| `fqz_cgzhan_hosp_fee` | 医院 + 费用分类 | 审计药品、耗材、诊察费占比 |
| `fqz_cgzhan_tcq` | 统筹区 | 区域间基金平衡性对账 |
| `fqz_cgzhan_tcq_xzlb` | 统筹区 + 险种 | 职工/居民待遇差分析 |
| `fqz_cgzhan_tcq_jzdlb` | 统筹区 + 就诊类 | 门诊/住院流向监控 |
| `fqz_cgzhan_tcq_yydj_yyxz` | 统筹区 + 等级 + 性质 | 审计“民营三级”等特殊机构集聚风险 |
| `fqz_cgzhan_tcq_yydj_yyxz_xzlb_jzdlb` | 全维度交叉 | **最精细统计项**，用于锁定极小颗粒度的异常 |
| ... (以此类推) | ... | 覆盖截图中的所有 17 种排列组合 |

### 3. CGZHAN 域通用核心指标 (Metric Definitions)
以下字段在上述 17 张表中具备完全一致的物理含义：

| 物理字段 | 业务含义 | 计算/审计逻辑 |
| :--- | :--- | :--- |
| `sum_medfee_sumamt` | 医疗费总额 | 该统计维度下的资金底盘。 |
| `sum_hifp_pay` | 统筹支付总额 | 关注“大盘”是否超出预算。 |
| `sum_ipt_days` | 住院总天数 | 监控“人均住院天数”的异常。 |
| `avg_medfee_sumamt` | 次均费用 | 审计“乱收费、分解收费”的首要指标。 |
| `prop_totlcnt_num` | 统计占比 | 该项指标（如某类险种）占当前总维度的比例。 |
| `vix` | **变异/离散指数** | **【核心】** 偏离该维度均值的程度，>1.5 视为重点审计风险点。 |

---

## 📂 核心域 C：风险专题路径 (ZTK - Topic Library)

### 1. `fqz_ztk_psn_yearly` - 参保人年度画像
- **业务意义**：记录每个人每年的就诊频次(`jzcs`)、住院天数(`ipt_days_hj`)，用于捕捉“药头”和“异常住院”。

## 📂 辅助域 D：系统维表与字典 (Dimensions)
维表是审计推演的坐标轴，决定了数据如何被切片和分类。

### 1. 区域与标准对照 (Geography & Standards)
- **`fqz_admdvs` / `fqz_dm_admdvs` / `fqz_dm_admdvs_sync`**:
    - **逻辑说明**：包含了全国医保标准的行政区划。其中 `sync` 为数据同步源，`dm_admdvs` 为格式化后的审计工作表。
    - **关键字段**：`admdvs` (行政区划代码), `admdvs_name` (区划名称), `prnt_admdvs` (父级区划代码), `admdvs_lv` (区划级别：0国家/1省/2市)。

- **`fqz_dm_dicqueryCinfo`**:
    - **核心用途**：医保业务代码对照。例如将性别代码 `1` 映射为 `男`。

- **`fqz_drug_mcs_info_list`**:
    - **核心用途**：药品及耗材国家标准名录库。
    - **关键字段**：`drug_genname` (通用名), `prodentp_name` (生产厂家), `drug_type` (西药/中草药)。

### 2. 时间坐标轴 (Temporal Dimension)
- **`fqz_dim_date` / `fqz_dm_time`**:
    - **核心用途**：提供连续的时间序列，用于支持“同比”、“环比”以及“趋势波动”审计。

---

## 📂 过程域 E：风险专题与治理区 (Topics & Governance)
包含特定分析场景的专题库，以及您提到的治理中间表（无关表说明）。

### 1. 风险画像专题 (Risk Profiling)
- **`fqz_ztk_psn_yearly`**:
    - **核心指标**：`jzcs` (年总就诊次数), `medfee_sumamt` (年总金额)。
    - **审计价值**：锁定年度“药贩子”或单一年度结算极高的反常账户。

- **`fqz_ptzy_hosp`**:
    - **审计价值**：专门用于“普通住院”维度的效率和风险基准值计算。

### 2.治理辅助与无关表 (Auxiliary & Irrelevant)
**[此区域表仅作为数据完整性对账或历史快照，无需在审计业务层直接操作]**

- **`fqz_fymx_test` / `test1`**:
    - **用途**：数据同步脚本在迁移 `fee` 明细表时的临时抽样库，用于验证字段对齐。

- **`fqz_gz_jzsj_all_ql_clean` / `fixed`**:
    - **定位**：18GB 全量数据在纠偏过程中的物理镜像。标记为无关是因为 `default.fqz_gz_jzsj_all_ql` 已经是它们修复后的合集。

---

## 💡 开发参考 (Developer Notes)
- **关联建议**：大部分表通过 `admdvs` 或 `fixmedins_code` 实现强关联。
- **性能提示**：在大表查询时，务必利用 `setl_time` 或 `uyear` 字段进行分区剪枝。
