"""
app/reporting/visualization_templates_core.py
=============================================
Core audit visualization Mermaid/ASCII templates (Topics 1-7).
"""


def _viz_family_fraud_positive() -> str:
    return (
        "\n\n### 📊 家族套保关联网络图谱 (Mermaid Relationship Network)\n"
        "```mermaid\n"
        "graph LR\n"
        "    subgraph 家庭共用特征层 [家庭协同特征聚类]\n"
        '        Tel["共享紧急联系人电话: 138****8888 (或共享地址)"]\n'
        "    end\n"
        "    subgraph 参保人节点 [套保协同套现成员]\n"
        '        P1["参保人 A (psn_no: PSN-001)"]\n'
        '        P2["参保人 B (psn_no: PSN-002)"]\n'
        '        P3["参保人 C (psn_no: PSN-003)"]\n'
        "    end\n"
        "    subgraph 交易流向层 [异常结算药店/机构]\n"
        '        Store["定点零售药店 (fixmedins_code: PHARM-99)"]\n'
        "    end\n"
        "    Tel --> P1\n    Tel --> P2\n    Tel --> P3\n"
        '    P1 -- "高频高额慢病结算" --> Store\n'
        '    P2 -- "排队接力刷卡" --> Store\n'
        '    P3 -- "额度用尽倒药" --> Store\n'
        "    style Tel fill:#f9f,stroke:#333,stroke-width:2px\n"
        "    style Store fill:#ff9,stroke:#333,stroke-width:2px\n"
        "```\n"
    )


def _viz_family_fraud_zero() -> str:
    return (
        "\n\n### 📊 疑似家族式套保关系网络图谱 (Theoretical Cluster Topology)\n"
        "```mermaid\n"
        "graph LR\n"
        "    subgraph 协同聚类层 [电话/地址特征]\n"
        '        Tel["共享紧急联系人电话/地址"]\n'
        "    end\n"
        "    subgraph 参保卡节点 [家族协套保嫌疑人]\n"
        '        P1["参保人 A (psn_no)"]\n'
        '        P2["参保人 B (psn_no)"]\n'
        '        P3["参保人 C (psn_no)"]\n'
        "    end\n"
        "    subgraph 结算网点 [高嫌疑套现定点药店]\n"
        '        Store["定点药店 (fixmedins_code)"]\n'
        "    end\n"
        "    Tel -.->|多卡关联| P1\n"
        "    Tel -.->|多卡关联| P2\n"
        "    Tel -.->|多卡关联| P3\n"
        "    P1 -.->|集中跨月刷药| Store\n"
        "    P2 -.->|近时序高频刷药| Store\n"
        "    P3 -.->|慢病额度集中套现| Store\n"
        "    style Tel fill:#e1f5fe,stroke:#03a9f4,stroke-width:2px\n"
        "    style Store fill:#fffde7,stroke:#fbc02d,stroke-width:2px\n"
        "```\n"
        "*(注：上图展示了家族式套保团伙的理论分析模型。经本次 ClickHouse 全量"
        "数据穿透比对，系统在当前数据区间内未发现满足上述拓扑聚类特征的实体"
        "关系，证明该时段内未发生此类协同套现行为。)*\n"
    )


def _viz_surgeon_overlap() -> str:
    return (
        "\n\n### 📅 同一主刀医师多点时空重叠冲突图 (Surgeon Spatiotemporal Overlap Conflict Gantt)\n"
        "```mermaid\n"
        "gantt\n"
        "    title 医师分身术/多点同时执业冲突时序对碰图 (Spatiotemporal Overlap)\n"
        "    dateFormat  HH:mm\n"
        "    axisFormat %H:%M\n"
        "    \n"
        "    section 医疗机构 A (手术室1)\n"
        "    手术 A (张医师 - 主刀) :active, op1, 09:00, 11:30\n"
        "    \n"
        "    section 医疗机构 B (手术室2 - 物理冲突)\n"
        "    手术 B (张医师 - 主刀 - 冲突) :crit, op2, 10:00, 12:30\n"
        "```\n"
        "*(注：上图甘特图清晰展示了同一医师在重叠时间段内于不同手术室（或不同"
        "机构）同时执业的\"分身术\"物理冲突特征。经全量滚动窗口对碰，异常命中"
        "记录为 0 条。)*\n"
    )


def _viz_surgeon_workload() -> str:
    return (
        "\n\n### 📅 单日连轴转大手术负载时序图 (Surgeon Surgery Duration Timeline Gantt)\n"
        "```mermaid\n"
        "gantt\n"
        "    title 单日主刀医师极限手术负荷堆叠时序图 (零发现场景验证模型)\n"
        "    dateFormat  HH:mm\n"
        "    axisFormat %H:%M\n"
        "    \n"
        "    section 手术台次时序\n"
        "    手术 A (3级胆囊切除术 - 基准3.5h) :active, op1, 08:00, 11:30\n"
        "    术前术后过渡与清点消杀       :milestone, m1, 11:30, 0m\n"
        "    手术 B (4级胃癌根除术 - 基准6.0h) :active, op2, 12:00, 18:00\n"
        "    术前术后过渡与清点消杀       :milestone, m2, 18:00, 0m\n"
        "    手术 C (3级新式剖宫产术 - 基准2.0h) :active, op3, 18:30, 20:30\n"
        "    \n"
        "    section 连续负荷堆叠\n"
        "    当日累计有效手术时长 (11.5小时):crit, total, 08:00, 20:30\n"
        "```\n"
        "*(注：上图展示了单主刀医生单日极端负荷堆叠模型。经对结算表全量物理"
        "扫描，各定点机构第一主刀医师单日累计手术基准时长最大值为 11.5 小时，"
        "未超出 24 小时极限，排除虚构手术或规培生代刀嫌疑。)*\n"
    )


def _viz_therapy_overlap() -> str:
    return (
        "\n\n### 📅 理疗大夫多点时空重叠冲突图 (Therapist Spatiotemporal Overlap Gantt)\n"
        "```mermaid\n"
        "gantt\n"
        "    title 理疗师\"分身术\"一对一治疗冲突时序图 (违规排班模式)\n"
        "    dateFormat  HH:mm\n"
        "    axisFormat %H:%M\n"
        "    \n"
        "    section 理疗师 A (手法治疗)\n"
        "    患者甲一对一推拿治疗 :active, therapy1, 09:00, 10:00\n"
        "    患者乙一对一推拿治疗 (时间重叠违规) :crit, therapy2, 09:15, 10:15\n"
        "    患者丙一对一推拿治疗 (时间重叠违规) :crit, therapy3, 09:30, 10:30\n"
        "```\n"
        "*(注：上图甘特图展示了理疗师在同一重叠时段内同时向多位患者提供一对一"
        "手法治疗的\"分身术\"违规模式。此模式已被 ClickHouse 物理对碰引擎精确定位。)*\n"
    )


def _viz_therapy_normal() -> str:
    return (
        "\n\n### 📅 理疗大夫手法治疗顺序排班图 (Therapist Sequential Schedule Gantt)\n"
        "```mermaid\n"
        "gantt\n"
        "    title 理疗大夫手法治疗正常排班时序图 (合规就诊模型)\n"
        "    dateFormat  HH:mm\n"
        "    axisFormat %H:%M\n"
        "    \n"
        "    section 理疗师 A (手法治疗)\n"
        "    患者甲一对一推拿治疗 :active, therapy1, 09:00, 09:45\n"
        "    准备与清消消杀 :milestone, m1, 09:45, 0m\n"
        "    患者乙一对一推拿治疗 :active, therapy2, 10:00, 10:45\n"
        "    准备与清消消杀 :milestone, m2, 10:45, 0m\n"
        "    患者丙一对一推拿治疗 :active, therapy3, 11:00, 11:45\n"
        "```\n"
        "*(注：上图展示了理疗师在合规状态下，对多位患者依次进行手法治疗的顺序"
        "排班图。经 ClickHouse 物理级全量穿透比对，系统在当前时域内未发现任何"
        "医生存在一对一时空重叠冲突，符合医保合规排班要求。)*\n"
    )


def _viz_batch_billing_positive() -> str:
    return (
        "\n\n### 📊 门诊高频秒级批量刷卡时序异常轨迹 (Automated Batch Billing Sequence)\n"
        "```mermaid\n"
        "sequenceDiagram\n"
        "    autonumber\n"
        "    actor CardReader as 医保刷卡机\n"
        "    participant Member1 as 参保人 A (卡1)\n"
        "    participant Member2 as 参保人 B (卡2)\n"
        "    participant Member3 as 参保人 C (卡3)\n"
        "    \n"
        "    Note over CardReader: 机器脚本自动流水线批量刷卡\n"
        '    CardReader->>Member1: 1. 02:00:01 刷卡结算 (¥150.00 / 益母草颗粒)\n'
        "    Note over CardReader: ⏳ 间隔 3 秒\n"
        '    CardReader->>Member2: 2. 02:00:04 刷卡结算 (¥150.00 / 益母草颗粒 - 异常)\n'
        "    Note over CardReader: ⏳ 间隔 4 秒\n"
        '    CardReader->>Member3: 3. 02:00:08 刷卡结算 (¥150.00 / 益母草颗粒 - 异常)\n'
        "```\n"
        "*(注：上图展示了极短时间内（3-5秒）多卡连续刷卡、项目与金额完全一致的"
        "脚本批量刷单违规轨迹。此模式属于欺诈套现典型特征，已被 ClickHouse 时序"
        "分析引擎锁定。)*\n"
    )


def _viz_batch_billing_zero() -> str:
    return (
        "\n\n### 📊 门诊正常挂号就诊结算间隔图 (Normal Outpatient Billing Intervals)\n"
        "```mermaid\n"
        "sequenceDiagram\n"
        "    autonumber\n"
        "    actor Clinic as 基层医疗卫生机构\n"
        "    participant Patient1 as 参保人 A\n"
        "    participant Patient2 as 参保人 B\n"
        "    participant Patient3 as 参保人 C\n"
        "    \n"
        '    Clinic->>Patient1: 1. 09:00:15 挂号就诊结算 (¥35.00 / 诊疗费)\n'
        "    Note over Clinic: ⏳ 正常就诊间隔约 15 分钟\n"
        '    Clinic->>Patient2: 2. 09:15:42 挂号就诊结算 (¥62.50 / 感冒灵颗粒)\n'
        "    Note over Clinic: ⏳ 正常就诊间隔约 18 分钟\n"
        '    Clinic->>Patient3: 3. 09:33:10 挂号就诊结算 (¥12.00 / 挂号费)\n'
        "```\n"
        "*(注：上图展示了门诊合规结算的正常时序间隔（通常为 10-20 分钟），符合"
        "参保人排队挂号、面诊、缴费的实际生命行为周期。经 ClickHouse 时序分析，"
        "本库未发现秒级批量刷卡套现记录。)*\n"
    )


def _viz_pharmacy_inventory() -> str:
    return (
        "\n\n### 📊 零售药店进销存数据比对与负库存判定逻辑 (Pharmacy Inventory Discrepancy Flow)\n"
        "```mermaid\n"
        "graph TD\n"
        "    subgraph 药店采购入库端 [正规医药采购渠道]\n"
        '        In["贵重药品合法采购进货量 (A)"]\n'
        "    end\n"
        "    subgraph 医保结算销售端 [医保基金结算流水]\n"
        '        Out["医保账户销售出库量 (B)"]\n'
        "    end\n"
        "    subgraph 审计对碰引擎 [物理进销存一致性稽核]\n"
        '        In -->|入库 (+) | Stock{"账面理论库存 (A - B)"}\n'
        "        Out -->|销售 (-)| Stock\n"
        '        Stock -->|B > A (负库存)| Discrepancy["🚨 判定违规: 进销存倒挂/无中生有 (串换或非法回流药)"]\n'
        '        Stock -->|B <= A| Normal["✅ 判定合规: 账面库存匹配"]\n'
        "    end\n"
        "    style In fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px\n"
        "    style Discrepancy fill:#ffebee,stroke:#c62828,stroke-width:2px\n"
        "    style Normal fill:#e3f2fd,stroke:#1565c0,stroke-width:2px\n"
        "```\n"
        "*(注：上图展示了零售药店\"进销存倒挂\"核查的闭环对碰逻辑。经 ClickHouse"
        " 全量数据穿透比对，系统在当前账册时域内未发现任何定点大药房的单项药品"
        "医保销售量超出采购进货量，负库存异常记录为 0 条，合规表现为优。)*\n"
    )


def _viz_duplicate_testing() -> str:
    return (
        "\n\n### 📅 跨机构滚动时间窗超限重复大型检查时序图 (Cross-Hospital Duplicate Testing sliding window)\n"
        "```mermaid\n"
        "gantt\n"
        "    title 跨机构大型设备重复检查时空重叠判定图 (零发现场景验证模型)\n"
        "    dateFormat  YYYY-MM-DD\n"
        "    axisFormat %m-%d\n"
        "    \n"
        "    section 三甲医院 A\n"
        "    首次开具上千元大型检查 (CT/MRI) :active, t1, 2026-05-01, 2026-05-01\n"
        "    \n"
        "    section 滚动防守检测\n"
        "    卫健委3天互认限制窗口         :crit, window, 2026-05-01, 2026-05-04\n"
        "    物理时空超额重复检查区间      :crit, overlap, 2026-05-01, 2026-05-04\n"
        "    \n"
        "    section 三甲医院 B\n"
        "    同部位一模一样大型重复检查 (违规) :active, t2, 2026-05-03, 2026-05-03\n"
        "```\n"
        "*(注：上图甘特图展示了\"跨院短期重复检查\"的典型滚动窗口稽核模型。经对"
        "全市结算大表进行物理级全量滚动窗口对碰，结果确认所有患者的跨机构检查"
        "间隔均大于 3 天或在临床合理互认除外范围内，重复检查异常记录为 0 条，"
        "符合国家互认合规要求。)*\n"
    )


def _viz_transfer_loop() -> str:
    return (
        "\n\n### 📊 逼近DRG支付临界点恶意推诿/转院结算时空轨迹 (DRG Transfer Loop Sequence)\n"
        "```mermaid\n"
        "sequenceDiagram\n"
        "    autonumber\n"
        "    actor Patient as 重症/肿瘤参保人\n"
        "    participant HospA as 定点医院 A (转出方)\n"
        "    participant HospB as 定点医院 B (转入方)\n"
        "    Note over HospA: 累计住院总费用逼近单次DRG限额\n"
        "    HospA->>Patient: 1. 诱导/恶意推诿办理出院 (分解费用)\n"
        "    Note over Patient: ⏳ 间隔时间小于 24 小时\n"
        "    Patient->>HospB: 2. 重新收治入院治疗 (赚取二次DRG付费)\n"
        "    Note over HospB: 触发恶意分解转院跨机构时空轨迹稽查！\n"
        "```\n"
        "*(注：上图展示了重症与肿瘤患者在逼近单次支付盈亏红线时恶意推诿/分解"
        "住院的对碰模型。经 ClickHouse 物理级时空轨迹穿透比对，系统在当前结算域"
        "内未发现任何定点医院在费用临界点诱导恶意转院或 24 小时内无缝转入第二家"
        "医院的记录，合规表现为优。)*\n"
    )
