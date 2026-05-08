import os
import clickhouse_connect
from dotenv import load_dotenv

def apply_metadata_comments():
    load_dotenv()
    host = os.getenv("CLICKHOUSE_HOST", "127.0.0.1")
    port = int(os.getenv("CLICKHOUSE_PORT", "8123"))
    user = os.getenv("CLICKHOUSE_USER", "default")
    
    client = clickhouse_connect.get_client(host=host, port=port, username=user)
    
    # --- 1. 定义表级语义字典 (Table Level) ---
    TABLE_GLOSSARY = {
        "fqz_all_yy_yd_1": "全量结算明细快照表 - 用于医院维度快速审计",
        "fqz_gz_jzsj_all_ql": "原始就诊全库 - 18GB 生产数据落仓点",
        "fqz_gz_jzsj_all_ql_clean": "ql 原始就诊表清洗中间快照",
        "fqz_gz_jzsj_all_ql_fixed": "ql 原始就诊表修复过程快照",
        "fqz_cgzhan_hosp": "医院综合能力与风险统计表",
        "fqz_cgzhan_hosp_fee": "医院费用分类统计表 (药品/耗材占比分析)",
        "fqz_cgzhan_tcq": "统筹区基金平衡性统计表",
        "fqz_cgzhan_tcq_xzlb": "统筹区险种分类统计表 (职工/居民分析)",
        "fqz_ztk_psn_yearly": "参保人年度风险画像专题表",
        "fqz_admdvs": "医保标准行政区划字典表",
        "fqz_dm_admdvs": "格式化医保区划工作表",
        "fqz_dm_admdvs_sync": "行政区划同步源表",
        "fqz_dm_dicqueryCinfo": "医保标准字典对照表 (性别/状态码等)",
        "fqz_drug_mcs_info_list": "国家标准药品及耗材名录库",
        "fqz_dim_date": "通用审计时间维度坐标表",
        "fqz_dm_time": "精细化时间维度索引表"
    }

    # --- 2. 定义字段级语义字典 (Column Level) ---
    # 定义通用的全局字段含义，会自动匹配到所有包含这些字段的表中
    GLOBAL_COLUMN_GLOSSARY = {
        "psn_no": "参保人唯一编号",
        "psn_name": "参保人姓名",
        "certno": "身份证号码",
        "fixmedins_code": "医药机构/医院编码",
        "fixmedins_name": "医药机构名称",
        "hifp_pay": "统筹基金支付金额 (医保报销核心)",
        "acct_pay": "个人账户支付金额",
        "cash_payamt": "个人现金支付金额",
        "maf_pay": "医疗救助资金支付",
        "med_type": "医疗类别 (门诊/住院/药店)",
        "setl_time": "结算时间",
        "start_date": "入院/开始日期",
        "end_date": "出院/结束日期",
        "ipt_days": "住院天数",
        "dise_name": "诊断名称/疾病描述",
        "medfee_sumamt": "医疗费总金额",
        "fund_pay_sumamt": "基金支付总额 (含统筹及各类补助)",
        "hosp_lv": "医院等级",
        "admdvs_code": "行政区划代码",
        "admdvs_name": "行政区划名称",
        "vix": "变异/离散系数 (指标偏离度，核心预警项)",
        "sum_hifp_pay": "统筹支付总金额 (聚合项)",
        "avg_medfee_sumamt": "次均医疗费用 (审计分解收费核心指标)"
    }

    print(">>> 正在启动物理映射同步流程...")

    # 3. 抓取物理现状，防止向不存在的列下发指令
    exist_cols = client.query("SELECT table, name FROM system.columns WHERE database = 'default'").result_rows
    # 建立 (table, column) 快速索引
    physical_map = {(row[0], row[1]) for row in exist_cols}
    
    exist_tables = client.query("SELECT name FROM system.tables WHERE database = 'default'").result_rows
    physical_tables = {row[0] for row in exist_tables}

    # 4. 执行表级注入
    print(f"\n[STEP 1] Applying Table Comments (Target: {len(TABLE_GLOSSARY)})...")
    for t_name, t_desc in TABLE_GLOSSARY.items():
        if t_name in physical_tables:
            try:
                client.command(f"ALTER TABLE {t_name} MODIFY COMMENT '{t_desc}'")
                print(f"SUCCESS: {t_name} -> {t_desc}")
            except Exception as e:
                print(f"ERROR: {t_name} failed: {e}")

    # 5. 执行字段级注入
    print(f"\n[STEP 2] Applying Column Comments (Target: {len(GLOBAL_COLUMN_GLOSSARY)} entries)...")
    success_count = 0
    for t_name in physical_tables:
        if not t_name.startswith("fqz_"): continue
        
        for c_name, c_desc in GLOBAL_COLUMN_GLOSSARY.items():
            if (t_name, c_name) in physical_map:
                try:
                    # 使用 COMMENT COLUMN 语法进行轻量级元数据变更
                    client.command(f"ALTER TABLE {t_name} COMMENT COLUMN {c_name} '{c_desc}'")
                    success_count += 1
                except Exception as e:
                    pass
    
    print(f"\n>>> Metadata Sync Done. Applied {success_count} column comments.")
    client.close()

if __name__ == "__main__":
    apply_metadata_comments()
