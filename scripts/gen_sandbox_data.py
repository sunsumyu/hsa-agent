import os
import random
import datetime
import clickhouse_connect
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

# ClickHouse 连接配置
def get_clickhouse_client():
    try:
        client = clickhouse_connect.get_client(
            host=os.getenv("CLICKHOUSE_HOST", "127.0.0.1"),
            port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
            username="",
            password=""
        )
        return client
    except Exception as e:
        logger.error(f"ClickHouse 连接失败: {e}")
        return None

# 仿真数据列表
REAL_LOOKING_HOSPITALS = [
    "上海中医药大学附属岳阳医院", "复旦大学附属儿科医院", "瑞金医院", "华山医院",
    "江苏省人民医院", "浙江大学医学院附属第一医院", "武汉同济医院", "协和医院",
    "德济综合医院", "曙光医疗中心", "同舟妇幼保健院"
]

DRUG_NAMES = ["阿莫西林", "头孢克肟", "奥司他韦", "布洛芬", "阿司匹林", "胰岛素"]

def init_sandbox_db(client):
    """初始化沙箱数据库和表"""
    logger.info("正在初始化沙箱数据库结构...")
    client.command("CREATE DATABASE IF NOT EXISTS hsa_sandbox")
    
    # 结算汇总表
    client.command("""
    CREATE TABLE IF NOT EXISTS hsa_sandbox.fqz_all_yy_yd_1 (
        fixmedins_name String,
        medfee_sumamt Float64,
        setl_time DateTime,
        admdvs String,
        psn_no String
    ) ENGINE = Memory
    """)
    
    # 住院明细表
    client.command("""
    CREATE TABLE IF NOT EXISTS hsa_sandbox.fqz_ptzy_hosp (
        fixmedins_code String,
        fixmedins_name String,
        ipt_days_hj Int32,
        medfee_sumamt Float64,
        setl_rq Date,
        psn_no String,
        diag_name String
    ) ENGINE = Memory
    """)
    logger.info("数据库表结构初始化完成 (使用 Memory 引擎)。")

def generate_data(client, count=200):
    """生成仿真数据，包含正常数据和稽核埋点"""
    logger.info(f"正在生成 {count} 条仿真数据...")
    
    summary_data = []
    detail_data = []
    
    psn_list = [f"P{i:05d}" for i in range(1, 51)] # 50 个虚拟患者
    
    for _ in range(count):
        hosp = random.choice(REAL_LOOKING_HOSPITALS)
        psn = random.choice(psn_list)
        amount = round(random.uniform(500, 15000), 2)
        dt = datetime.datetime.now() - datetime.timedelta(days=random.randint(1, 365))
        
        # 填充汇总表
        summary_data.append([hosp, amount, dt, "310000", psn])
        
        # 填充明细表 (如果是住院)
        if random.random() > 0.5:
            days = random.randint(3, 20)
            diag = random.choice(["上呼吸道感染", "高血压", "糖尿病", "肺炎", "冠心病"])
            detail_data.append([
                f"H{REAL_LOOKING_HOSPITALS.index(hosp):03d}", 
                hosp, days, amount, dt.date(), psn, diag
            ])

    # 插入违规埋点：同日异地住院 (同一病人在同一天在两家医院有结算)
    logger.info("正在埋入违规陷阱案例...")
    bad_psn = "P99999"
    bad_date = datetime.datetime(2026, 1, 15)
    # 医院1
    summary_data.append(["瑞金医院", 12000.0, bad_date, "310000", bad_psn])
    detail_data.append(["H003", "瑞金医院", 7, 12000.0, bad_date.date(), bad_psn, "肺炎"])
    # 医院2 (同日，但在江苏)
    summary_data.append(["江苏省人民医院", 8000.0, bad_date + datetime.timedelta(hours=2), "320000", bad_psn])
    detail_data.append(["H005", "江苏省人民医院", 7, 8000.0, bad_date.date(), bad_psn, "糖尿病"])

    # 插入汇总排名案例 (针对 golden_dataset 中的排名查询)
    logger.info("正在埋入排名基准数据...")
    summary_data.append(["德济综合医院", 239528.27, bad_date, "310000", "P_RANK_1"])
    summary_data.append(["曙光医疗中心", 225678.16, bad_date, "310000", "P_RANK_2"])
    summary_data.append(["同舟妇幼保健院", 210558.63, bad_date, "310000", "P_RANK_3"])

    # 执行插入
    if summary_data:
        client.insert("hsa_sandbox.fqz_all_yy_yd_1", summary_data, column_names=['fixmedins_name', 'medfee_sumamt', 'setl_time', 'admdvs', 'psn_no'])
    if detail_data:
        client.insert("hsa_sandbox.fqz_ptzy_hosp", detail_data, column_names=['fixmedins_code', 'fixmedins_name', 'ipt_days_hj', 'medfee_sumamt', 'setl_rq', 'psn_no', 'diag_name'])
    
    logger.info("仿真数据填充完成。")

if __name__ == "__main__":
    cli = get_clickhouse_client()
    if cli:
        init_sandbox_db(cli)
        generate_data(cli)
        logger.success("沙箱环境就绪！")
