from app.infra.db_conn import get_clickhouse_client
from loguru import logger
import time

def clean_clickhouse_data():
    client = get_clickhouse_client()
    table = "fqz_fymx_test1"
    
    logger.info(f"开始数据内容清洗: {table}...")
    
    # 1. 获取所有 String 类型的字段
    res = client.query(f"DESCRIBE TABLE {table}")
    string_columns = []
    for row in res.result_rows:
        col_name = row[0]
        col_type = row[1]
        if "String" in col_type:
            string_columns.append(col_name)
            
    if not string_columns:
        logger.warning("未发现字符串字段。")
        return

    # 2. 对每个字段提交异步更新指令
    # 使用 replaceAll 彻底替换掉所有的 \t
    for col in string_columns:
        update_sql = f"ALTER TABLE {table} UPDATE {col} = replaceAll({col}, '\\t', '') WHERE {col} LIKE '%\\t%'"
        try:
            client.command(update_sql)
            logger.info(f"已提交强制替换任务: {col}")
        except Exception as e:
            logger.error(f"字段 {col} 提交失败: {e}")

    # 3. 等待异步任务完成
    logger.info("正在等待 ClickHouse 后台清洗任务完成 (Mutations)...")
    while True:
        check_sql = f"SELECT count() FROM system.mutations WHERE table = '{table}' AND is_done = 0"
        pending = client.query(check_sql).result_rows[0][0]
        if pending == 0:
            break
        logger.debug(f"尚有 {pending} 个清洗任务运行中...")
        time.sleep(2)

    logger.success(f"🎉 数据库表 {table} 数据内容清洗成功！")

if __name__ == "__main__":
    clean_clickhouse_data()
