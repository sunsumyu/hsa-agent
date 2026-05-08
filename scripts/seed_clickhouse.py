import clickhouse_connect
import random
from datetime import datetime, timedelta
from loguru import logger

def absolute_saturation_seed():
    logger.info(">>> [V38.9.16 绝对饱和] 正在同步最后别名网格...")
    
    try:
        client = clickhouse_connect.get_client(host='127.0.0.1', port=8123)
    except Exception as e:
        logger.error(f"连接失败: {e}")
        return

    # 1. 物理重置
    client.command("DROP TABLE IF EXISTS fqz_all_yy_yd_1")
    client.command("DROP TABLE IF EXISTS k21")
    client.command("DROP TABLE IF EXISTS fqz_cgzhan_hosp")

    # 2. 重建“绝对全维度万能宽表”
    # 穷举所有业务可能用到的命名别名
    universal_fields = """
        psn_no String,
        medfee_sumamt Decimal(18, 2),
        amount Decimal(18, 2) ALIAS medfee_sumamt,
        ipt_days Int32,
        stay_days Int32 ALIAS ipt_days,
        visit_count Int32 ALIAS 1,
        setl_time DateTime,
        settle_date Date,
        settle_time DateTime ALIAS setl_time,
        adm_time DateTime ALIAS setl_time,
        admit_time DateTime ALIAS setl_time,
        dscg_time DateTime ALIAS setl_time,
        dsch_time DateTime ALIAS setl_time,
        ipt_date Date ALIAS settle_date,
        adate Date ALIAS settle_date,
        adm_date Date ALIAS settle_date,
        admit_date Date ALIAS settle_date,
        visit_date Date ALIAS settle_date,
        opmt_date Date ALIAS settle_date,
        out_date Date ALIAS settle_date,
        dscg_date Date ALIAS settle_date,
        dsch_date Date ALIAS settle_date,
        fixmedins_name String,
        org_name String,
        hosp_id String,
        org_id String,
        org_code String,
        fixmedins_code String,
        admdvs String DEFAULT '440100'
    """
    
    client.command(f"CREATE TABLE fqz_all_yy_yd_1 ({universal_fields}) ENGINE = Memory")
    client.command("CREATE TABLE k21 AS fqz_all_yy_yd_1")
    client.command("CREATE TABLE fqz_cgzhan_hosp (hosp_id String, org_id String, org_code String, org_name String) ENGINE = Memory")

    logger.info("✔ 物理绝对饱和底座已落成")

    # 3. 注入确证数据
    target_psn = "PSN_20210002"
    start_date = datetime(2021, 1, 1)
    data = []
    for _ in range(10):
        medfee = random.uniform(8000, 20000)
        dt = start_date + timedelta(days=random.randint(0, 360))
        d_val = dt.date()
        data.append([
            target_psn, medfee, random.randint(3, 15), 
            dt, d_val, "中山大学附属第一医院", "中山大学附属第一医院", "H002", "H002", "H002", "H002"
        ])
    
    try:
        client.insert('fqz_all_yy_yd_1', data, column_names=[
            'psn_no', 'medfee_sumamt', 'ipt_days', 'setl_time', 'settle_date', 
            'fixmedins_name', 'org_name', 'hosp_id', 'org_id', 'org_code', 'fixmedins_code'
        ])
        client.insert('k21', data, column_names=[
            'psn_no', 'medfee_sumamt', 'ipt_days', 'setl_time', 'settle_date', 
            'fixmedins_name', 'org_name', 'hosp_id', 'org_id', 'org_code', 'fixmedins_code'
        ])
        logger.info(f"✔ 成功注入 10 条确证数据到绝对饱和底座")
    except Exception as e:
        logger.error(f"注入失败: {e}")

if __name__ == "__main__":
    absolute_saturation_seed()
