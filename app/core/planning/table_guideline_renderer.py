from typing import Optional
from app.core.registry.archetype_registry import archetype_registry

TABLE_HINTS = {
    "fqz_fymx_test": """
【⚠️ 物理表选择指引 (TABLE SELECTION HINT)】
根据场景关键词检测，建议使用 `fqz_fymx_test` 表。

理由：
1. 乡镇卫生院/村卫生室/门诊统筹场景的费用数据存储在 `fqz_fymx_test`
2. `fqz_fymx_test.fixmedins_name` 是真实中文机构名，可 LIKE 匹配
3. `fqz_gz_jzsj_all_ql.fixmedins_name` 是加密混淆字段，无法中文匹配
4. 两表 setl_id 完全不重叠，JOIN 会导致数据丢失

字段注意事项：
- `fqz_fymx_test.setl_time` 是 String 类型且尾部带 \\t，**严禁**直接 toDateTime()，必须用 toDateTime(substring(trim(setl_time),1,19)) 转换
- 必须用 trim(...) 清理字符串字段
- med_type 编码：11=门诊统筹，21=住院，53_04=特病门诊

注意：以上仅为表选择指引，SQL 查询模式请根据审计方法论和用户原始问题自行决定，不要照搬历史 SQL 模板。
""",
    "fqz_all_yy_yd": """
【⚠️ 物理表选择指引 (TABLE SELECTION HINT)】
当前审计任务涉及医疗机构/药店名录普查与统计，物理主表为 `fqz_all_yy_yd`。
机构代码为 `fixmedins_code`，机构名称为 `fixmedins_name`，机构类型为 `medins_type`，有效标志为 `vali_flag`。
严禁使用 `yyjg_zzml`、`medical_institutions` 等任何虚构表名！必须直接在 `fqz_all_yy_yd` 上执行 SQL 统计！
""",
    "fqz_admdvs": """
【⚠️ 物理表选择指引 (TABLE SELECTION HINT)】
当前任务涉及医保行政区划字典与层级，物理主表为 `fqz_admdvs`。
真实物理字段如下：
- 区划代码为 `admdvs`
- 区划名称为 `admdvs_name`
- 区划层级为 `admdvs_lv`（1=国家级, 2=省级, 3=市级, 4=区县级）
- 上级区划代码为 `prnt_admdvs`
严禁探查 system.tables 或捏造外部表名！直接在 `fqz_admdvs` 上按 `admdvs_lv` 分组统计即可。
""",
    "fqz_cgzhan_hosp_fee": """
【⚠️ 物理表选择指引 (TABLE SELECTION HINT)】
当前审计任务涉及定点医药机构宏观月度费用报表统计，物理主表为 `fqz_cgzhan_hosp_fee`。
核心真实字段如下：
- `sum_medfee_sumamt`：医疗总费用金额（数值型）
- `sum_hifp_pay`：统筹基金支出金额（数值型）
- `sum_fund_pay_sumamt`：医保基金支付总额合计（数值型）
- `setl_time`：结算统计月份/时间（如 '2024-01'）
- `timetype`：时间统计维度（如 'monthly'）
- `fixmedins_code`：定点医药机构代码
- `fixmedins_name`：医药机构名称
严禁使用“定点医药机构宏观月度费用统计报表”等虚构中文表名！统计总期数直接使用 count(*)，统计累计医疗总费用使用 sum(sum_medfee_sumamt)，统计统筹基金总支出使用 sum(sum_hifp_pay)。
""",
    "fqz_gz_jzsj_all_ql": """
【⚠️ 物理表选择指引 (TABLE SELECTION HINT)】
当前审计任务涉及医保就诊结算底表与对账，物理主表为 `fqz_gz_jzsj_all_ql`。
核心真实字段如下：
- `medfee_sumamt`：医疗总费用金额
- `fund_pay_sumamt`：统筹基金支付金额（若排查纯自费/零基金支付，条件为 fund_pay_sumamt = 0 AND medfee_sumamt > 0）
- `setl_id`：就诊结算批次号/标识
- `psn_no`：参保人员编号
- `setl_time`：结算时间
严禁使用“就诊结算底表”、“结算表”等虚假中文表名！
""",
    "fqz_drug_mcs_info_list": """
【⚠️ 物理表选择指引 (TABLE SELECTION HINT)】
当前任务涉及医保药品目录与药品特征分类，物理主表为 `fqz_drug_mcs_info_list`。
药品代码为 `med_list_code`，药品通用名/商品名为 `drug_prodname` / `genname_codg`。
"""
}


def render_table_guidelines(primary_table: str, user_query: str) -> Optional[str]:
    """[V178.10 / Matt Pocock Deep Module] 
    生成综合物理表选择指引与领域任务原型不变式强约束提示语。

    隐藏实现细节：
    - 多物理表专有 Prompt 模板映射
    - 实体混淆与字段类型防坑指引
    - Archetype 原型结构守卫的不变式聚合装配
    """
    table_hint = TABLE_HINTS.get(primary_table)
    
    archetype_hints = []
    for arch in archetype_registry.match_archetypes(user_query):
        if arch.enforcement_hint:
            archetype_hints.append(f"【🚨 {arch.display_name}结构守卫】\n{arch.enforcement_hint}")

    if not table_hint and not archetype_hints:
        return None

    parts = []
    if table_hint:
        parts.append(table_hint.strip())
    if archetype_hints:
        parts.append("\n\n".join(archetype_hints))

    return "\n\n".join(parts)
