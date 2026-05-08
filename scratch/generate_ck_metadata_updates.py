import os
import re
import clickhouse_connect
from dotenv import load_dotenv

def get_metadata_and_generate_sql():
    load_dotenv()
    host = os.getenv("CLICKHOUSE_HOST", "127.0.0.1")
    port = int(os.getenv("CLICKHOUSE_PORT", "8123"))
    user = os.getenv("CLICKHOUSE_USER", "default")
    
    # 建立确定性物理连接
    client = clickhouse_connect.get_client(host=host, port=port, username=user)
    
    # 1. 抓取物理现状
    print(">>> 正在探测 ClickHouse 物理表结构...")
    tables = client.query("SELECT name, comment FROM system.tables WHERE database = 'default' AND name LIKE 'fqz_%'").result_rows
    columns = client.query("SELECT table, name, comment FROM system.columns WHERE database = 'default' AND table LIKE 'fqz_%'").result_rows
    
    print(f"探测到 {len(tables)} 张相关表和 {len(columns)} 个物理字段。")
    
    # 2. 从文档中提取语义 (简化版演示，实际会读取全文)
    # 我们将主要针对 ql 表和 yd_1 表进行深度对位
    updates = []
    
    # 表名备注建议
    table_comments = {
        "fqz_all_yy_yd_1": "全量结算明细快照表 - 用于医院维度快速审计",
        "fqz_gz_jzsj_all_ql": "原始就诊全库 - 18GB 生产数据落仓点",
        "fqz_gz_jzsj_all_ql_clean": "ql 原始就诊表清洗快照",
        "fqz_gz_jzsj_all_ql_fixed": "ql 原始就诊表修复快照"
    }
    
    # 字段备注建议 (从百科提取的核心字段)
    col_comments = {
        "psn_no": "参保人编号 - 用于跨期行为追踪",
        "med_type": "医疗类别 (门诊/住院/药店)",
        "setl_time": "结算日期",
        "medfee_sumamt": "医疗费总额",
        "hifp_pay": "统筹基金支付 - 审计核心资金项",
        "dise_name": "诊断名称",
        "fixmedins_code": "医药机构/医院编码"
    }

    # 3. 生成 DDL 建议 (ALTER TABLE ... COMMENT)
    print("\n--- 建议执行的 DDL 语句 (物理安全) ---")
    for t_name, current_comment in tables:
        if t_name in table_comments:
             # ClickHouse 变更表注释语法
             updates.append(f"ALTER TABLE {t_name} MODIFY COMMENT '{table_comments[t_name]}';")
    
    for t_col_table, t_col_name, current_comment in columns:
        if t_col_name in col_comments:
             # 修改字段注释语法 (MODIFY COLUMN ... COMMENT)
             updates.append(f"ALTER TABLE {t_col_table} MODIFY COLUMN {t_col_name} COMMENT '{col_comments[t_col_name]}';")

    for sql in updates[:10]: # 展示前10条样例
        print(sql)
    
    print(f"\n即将生成的总变更量: {len(updates)} 条。")
    client.close()

if __name__ == "__main__":
    get_metadata_and_generate_sql()
