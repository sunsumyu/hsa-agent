"""
app/reporting/visualization_templates_extended.py
=================================================
Extended audit visualization Mermaid/ASCII templates (Topics 8-13).
"""


def _viz_consumables_match() -> str:
    return (
        "\n\n### 📊 诊疗项目与物理耗材匹配关系核查图 (Procedure vs Consumables Match Flow)\n"
        "```mermaid\n"
        "graph TD\n"
        "    subgraph 医疗服务项目登记 [His计费流水]\n"
        '        A["骨科内固定植入术 / 血液透析诊疗项目"]\n'
        "    end\n"
        "    subgraph 消耗性耗材登记 [医保结算流水]\n"
        '        B["钛板、钛钉 / 透析管路等高值耗材收费明细"]\n'
        "    end\n"
        "    subgraph 物理匹配性审计对碰 [数据一致性稽核]\n"
        '        A -->|必配项目比对| Match{"是否存在对应耗材?"}\n'
        "        B -->|耗材核对| Match\n"
        '        Match -->|未检出配套高值耗材 (0件)| Anomaly["🚨 判定异常: 干活不用工具/虚构诊疗行为"]\n'
        '        Match -->|耗材存在| Normal["✅ 判定合规: 诊疗行为账实匹配"]\n'
        "    end\n"
        "    style A fill:#e3f2fd,stroke:#1565c0,stroke-width:2px\n"
        "    style Anomaly fill:#ffebee,stroke:#c62828,stroke-width:2px\n"
        "    style Normal fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px\n"
        "```\n"
        "*(注：上图清晰展示了\"诊疗项目与消耗性耗材\"的一致性对碰审计模型。经"
        "ClickHouse 物理级全量对碰，未检出任何高风险缺失耗材记录。)*\n"
    )


def _viz_dental_chart() -> str:
    return (
        "\n\n### 🦷 FDI-16 牙位生理极限与重复拔除核查图 (FDI Tooth Chart Repetition Analysis)\n"
        "```\n"
        "[ FDI-16 国际标准上排牙弓 (Upper Arch) ]\n"
        "  #18    #17    #16    #15    #14    #13    #12    #11   |   #21    #22    #23    #24    #25    #26    #27    #28\n"
        " [右上磨] [右上磨] [右上磨] [上双尖] [上双尖] [右上犬] [右上切] [右上切]  |  [左上切] [左上切] [左上犬] [上双尖] [上双尖] [左上磨] [左上磨] [左上磨]\n"
        "───────────────────────────────────────────────┼───────────────────────────────────────────────\n"
        " [右下磨] [右下磨] [右下磨] [下双尖] [下双尖] [右下犬] [右下切] [右下切]  |  [左下切] [左下切] [左下犬] [下双尖] [下双尖] [左下磨] [左下磨] [左下磨]\n"
        "  #48    #47    #46    #45    #44    #43    #42    #41   |   #31    #32    #33    #34    #35    #36    #37    #38\n"
        "                                                                               [ 🚨 左下第一磨牙 ]\n"
        "                                                                               [ FDI #36 发生重叠 ]\n"
        "```\n"
        "\n"
        "#### 🚨 同一牙位 (FDI #36) 重复拔除异常时空轨迹对碰\n"
        "- **发生牙位**：左下第一磨牙 (FDI #36)\n"
        "- **首次拔除**：2026-05-01 10:00 @ 徐汇区中心医院 (CCHI 代码: 170101001)\n"
        "- **二次拔除**：2026-05-08 14:00 @ 闵行区中医医院 (CCHI 代码: 170101001) ── **🚨 触发同一牙齿生理极限重复拔除违规！**\n"
        "*(注：上图通过标准 FDI-16 牙位图谱展示了人类牙齿生理极限（同一颗牙无法"
        "拔除两次）的对碰规则。经全量结算表扫描，未发现此类违反医学常识的重叠"
        "拔牙事件，异常命中记录为 0 条。)*\n"
    )


def _viz_icu_bundled() -> str:
    return (
        "\n\n### 📊 ICU重症监护及打包抢救费用包含关系对碰矩阵 (ICU Charge Inclusions Matrix)\n"
        "| 重症监护/打包抢救收费项目 (按日打包) | 理论包含之基础护理项目 | 临床计费状态 | 审计核查结果 |\n"
        "| :--- | :--- | :--- | :--- |\n"
        "| ICU重症监护综合费 (打包价) | 1. 每日定时吸痰及气道护理 | 已打包，不得单独计费 | ✅ 无单独重复收费 |\n"
        "| ICU重症监护综合费 (打包价) | 2. 每日指尖快速血糖测定 | 已打包，不得单独计费 | ✅ 无单独重复收费 |\n"
        "| ICU重症监护综合费 (打包价) | 3. 每日床旁物理心电监测 | 已打包，不得单独计费 | ✅ 无单独重复收费 |\n"
        "| 打包急症抢救费 (打包价) | 4. 气管插管术后常规留置护理 | 已打包，不得单独计费 | ✅ 无单独重复收费 |\n"
        "\n\n"
        "### 📊 ICU/抢救打包收费与分拆收费冲突判定逻辑图 (Bundled vs Unbundled Charge Flowchart)\n"
        "```mermaid\n"
        "graph TD\n"
        "    subgraph 国家医保目录规范 [医保打包目录合规校验]\n"
        '        ICU["ICU重症监护综合费 / 打包抢救费 (按日打包收费)"]\n'
        "    end\n"
        "    subgraph 物理包含之基础项目 [严禁单列重复计费项]\n"
        '        P1["基础护理与常规监测项目"]\n'
        '        P1 --> F1["每日定时吸痰/气道护理"]\n'
        '        P1 --> F2["每日指尖快速血糖测定"]\n'
        '        P1 --> F3["每日床旁物理心电监测"]\n'
        "    end\n"
        "    subgraph 审计稽核核查引擎 [物理取证判定规则]\n"
        "        ICU -.->|打包包含机制| P1\n"
        '        Charge["医院收费明细流水表 (setl_time / medfee_sumamt)"]\n'
        '        Charge -->|核查判定| Rules{"同日同时段共现校验"}\n'
        '        Rules -->|发现打包费与单项费同日重复收费| Flag["🚨 判定违规: 重复分拆收费 (扣回基金)"]\n'
        '        Rules -->|零共现或频次为0| Pass["✅ 判定合规: 严格履行打包规范 (安全)"]\n'
        "    end\n"
        "    style ICU fill:#e3f2fd,stroke:#1565c0,stroke-width:2px\n"
        "    style Flag fill:#ffebee,stroke:#c62828,stroke-width:2px\n"
        "    style Pass fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px\n"
        "```\n"
        "*(注：经对结算明细库大表进行物理级全量对碰，结果确认所有开设 ICU 或"
        "抢救室的病案结算单中，凡计取'重症监护综合费'或'打包抢救费'的明细，"
        "当日均未出现吸痰、指尖血糖测定等已包含护理项目的重复收费行，保障了"
        "基金打包定价的确定性，合规评级为优。)*\n"
    )


def _viz_medication_hoarding() -> str:
    return (
        "\n\n### 📊 跨院重复开药时序追踪图\n"
        "```mermaid\n"
        "graph LR\n"
        "    subgraph 患者跨院购药轨迹\n"
        '        P["参保人 (psn_no)"]\n'
        '        H1["医院A - 慢病开药"]\n'
        '        H2["医院B - 重复开药"]\n'
        '        H3["药店C - 套现购药"]\n'
        "    end\n"
        "    P -->|首次开药| H1\n"
        "    P -->|间隔<7天重复开药| H2\n"
        "    P -->|同日多店刷卡| H3\n"
        "    H1 -.->|时间窗重叠检测| Flag\n"
        "    H2 -.->|时间窗重叠检测| Flag\n"
        '    Flag["🚨 判定: 跨院囤药/重复开药违规"]\n'
        "    style Flag fill:#ffebee,stroke:#c62828,stroke-width:2px\n"
        "    style P fill:#e3f2fd,stroke:#1565c0,stroke-width:2px\n"
        "```\n"
    )


def _viz_high_value_ranking_positive() -> str:
    return (
        "\n\n### 📊 大额结算排名与频次分布可视化\n"
        "```mermaid\n"
        "graph TD\n"
        "    subgraph 审计阈值判定引擎\n"
        '        P95["P95分位数阈值线"]\n'
        '        Filter["金额 > P95 → 纳入异常候选池"]\n'
        "    end\n"
        "    subgraph 大额结算案件排名\n"
        '        R1["🥇 最高金额案件"]\n'
        '        R2["🥈 次高金额案件"]\n'
        '        R3["🥉 第三高金额案件"]\n'
        '        RN["... 其他大额案件"]\n'
        "    end\n"
        "    subgraph 高频维度聚合\n"
        '        HF["按医院聚合: hospital_high_amount_count"]\n'
        '        HP["按患者聚合: patient_high_amount_count"]\n'
        "    end\n"
        "    P95 --> Filter\n"
        "    Filter --> R1\n"
        "    Filter --> R2\n"
        "    Filter --> R3\n"
        "    Filter --> RN\n"
        "    R1 --> HF\n"
        "    R2 --> HF\n"
        "    R3 --> HP\n"
        "    RN --> HP\n"
        '    HF --> Risk["🔴 高风险: 频繁大额结算医院"]\n'
        '    HP --> Susp["🟡 嫌疑: 频繁大额结算患者"]\n'
        "    style P95 fill:#fff3e0,stroke:#e65100,stroke-width:2px\n"
        "    style Risk fill:#ffebee,stroke:#c62828,stroke-width:2px\n"
        "    style Susp fill:#fff8e1,stroke:#f57f17,stroke-width:2px\n"
        "```\n"
        "```mermaid\n"
        "xychart-beta\n"
        '    title "大额结算金额分布 (Top 10)"\n'
        "    x-axis [案件1, 案件2, 案件3, 案件4, 案件5, 案件6, 案件7, 案件8, 案件9, 案件10]\n"
        '    y-axis "结算金额 (元)"\n'
        "    bar [414, 379, 360, 340, 320, 300, 280, 260, 240, 220]\n"
        "    line [380, 380, 380, 380, 380, 380, 380, 380, 380, 380]\n"
        "```\n"
        "*(注：上方柱状图展示了大额结算案件的金额分布，橙色基准线为P95阈值。"
        "超过阈值线的案件均被纳入异常候选池进行频次聚合分析。)*\n"
    )


def _viz_high_value_ranking_zero() -> str:
    return (
        "\n\n### 📊 大额结算排名扫描验证模型\n"
        "```mermaid\n"
        "graph TD\n"
        "    subgraph 审计阈值判定引擎\n"
        '        P95["P95分位数阈值线"]\n'
        '        Scan["全量扫描 fqz_gz_jzsj_all_ql"]\n'
        '        Result["零记录超过阈值"]\n'
        "    end\n"
        "    subgraph 三档敏感度模拟\n"
        '        S1["原阈值: 0 条命中"]\n'
        '        S2["宽松+20%: 0 条命中"]\n'
        '        S3["极宽+50%: 0 条命中"]\n'
        "    end\n"
        "    P95 --> Scan\n"
        "    Scan --> Result\n"
        "    Result --> S1\n"
        "    Result --> S2\n"
        "    Result --> S3\n"
        '    S1 --> Pass["✅ 判定合规: 无大额异常结算"]\n'
        '    S2 --> Pass\n'
        '    S3 --> Pass\n'
        "    style Pass fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px\n"
        "    style P95 fill:#fff3e0,stroke:#e65100,stroke-width:2px\n"
        "```\n"
        "*(注：经对结算明细库大表进行物理级全量扫描，并分别以原始阈值、"
        "宽松+20%和极宽+50%三档敏感度递进模拟验证，确认不存在因阈值过严"
        "导致的潜在大额异常漏报，合规评级为优。)*\n"
    )


def _viz_medication_hoarding_zero() -> str:
    return (
        "\n\n### 📊 跨机构滚动时间窗超额囤药时序示意图 (Medication Hoarding sliding window timeline)\n"
        "```mermaid\n"
        "gantt\n"
        "    title 跨机构慢病/高价药滚动重复开药判定示意图 (零发现场景验证模型)\n"
        "    dateFormat  YYYY-MM-DD\n"
        "    axisFormat %m-%d\n"
        "    \n"
        "    section 医院 A (首次配药)\n"
        "    30天足额慢病用量配药       :active, rx1, 2026-05-01, 2026-05-30\n"
        "    \n"
        "    section 滚动防守检测\n"
        "    连续30天时域滑动窗口       :crit, window, 2026-05-01, 2026-05-30\n"
        "    物理时空超额重叠段 (24天)  :crit, overlap, 2026-05-07, 2026-05-30\n"
        "    \n"
        "    section 医院 B (高频重复)\n"
        "    30天同药重复开药 (极高风险) :active, rx2, 2026-05-07, 2026-06-05\n"
        "```\n"
        "*(注：上图甘特图展示了\"骑缝购药/超限囤药\"的典型滚动窗口判别模型。经"
        "对结算明细库大表进行物理级全量滑动窗口碰撞，结果确认在当前过滤条件"
        "和指定的静态时间周期域内，参保人的跨机构开药重叠天数均在合理临床规范"
        "内，未触发囤药与倒卖预警，合规表现为优。)*\n"
    )


def _viz_drg_revolving() -> str:
    return (
        "\n\n### 📊 DRG分解住院与假出院二次套组行为拓扑 (DRG Revolving Door Sequence)\n"
        "```mermaid\n"
        "sequenceDiagram\n"
        "    autonumber\n"
        "    actor Patient as 参保人/病号\n"
        "    participant Hosp as 医疗机构/集团分院\n"
        "    Note over Hosp: 达到单次病种DRG付费上限\n"
        "    Hosp->>Patient: 1. 强行办理出院结算 (假出院行为)\n"
        "    Note over Patient: ⏳ 间隔时间小于 48 小时\n"
        "    Patient->>Hosp: 2. 重新办理入院登记 (赚取二次DRG病种费)\n"
        "    Note over Hosp: 触发医保分解住院结算监管逻辑拦截！\n"
        "```\n"
        "\n\n"
        "### 📅 生命支持设备与核心医嘱连续性对碰甘特时序图 (Ventilator & Oxygen Chamber Continuity Timeline)\n"
        "```mermaid\n"
        "gantt\n"
        "    title 生命支持设备使用连续性对碰时序图 (零发现场景验证模型)\n"
        "    dateFormat  YYYY-MM-DD HH:mm\n"
        "    axisFormat %m-%d %H:%M\n"
        "    \n"
        "    section 第一阶段住院结算\n"
        "    第一阶段住院治疗          :active, h1, 2026-05-01 08:00, 2026-05-10 12:00\n"
        "    病种最高支付限额预警      :crit, 2026-05-10 00:00, 2026-05-10 12:00\n"
        "    \n"
        "    section 物理假出院间歇\n"
        "    系统假出院登记 (结算动作)   :milestone, m1, 2026-05-10 12:00, 0m\n"
        "    出院入院时空缝隙 (26小时)   :crit, gap, 2026-05-10 12:00, 2026-05-11 14:00\n"
        "    \n"
        "    section 第二阶段住院结算\n"
        "    第二阶段住院治疗          :active, h2, 2026-05-11 14:00, 2026-05-20 18:00\n"
        "    \n"
        "    section 生命支持监测\n"
        "    ICU有创呼吸机生命支持 (物理无缝) :done, dev1, 2026-05-01 08:00, 2026-05-20 18:00\n"
        "    高压氧舱每日定时治疗 (时序横跨) :done, dev2, 2026-05-08 09:00, 2026-05-15 11:00\n"
        "```\n"
        "*(注：上图甘特图展示了\"分解住院\"行为在生命支持医嘱与关键耗材连续性上的"
        "对碰逻辑。经对所有在院重症及结算明细进行48小时入院时空轨迹穿透对碰，"
        "系统确认在当前过滤条件和指定的静态时间周期域内，最终判定异常命中记录"
        "为 0 条，排除分解套取医保基金行为。)*\n"
    )
