from app.db_conn import get_clickhouse_client
from loguru import logger

def fix_clickhouse_schema():
    client = get_clickhouse_client()
    table = "fqz_fymx_test1"
    
    logger.info(f"开始诊断并修复表 {table} 的字段污染问题...")
    
    # 1. 获取所有字段
    res = client.query(f"DESCRIBE TABLE {table}")
    dirty_columns = []
    for row in res.result_rows:
        col_name = row[0]
        if "\t" in col_name:
            dirty_columns.append(col_name)
            
    if not dirty_columns:
        logger.info("未发现污染字段，表结构正常。")
        return

    logger.info(f"发现 {len(dirty_columns)} 个污染字段，准备重命名...")
    
    # 2. 执行重命名
    for dirty_col in dirty_columns:
        clean_col = dirty_col.strip('\t')
        rename_sql = f'ALTER TABLE {table} RENAME COLUMN "{dirty_col}" TO {clean_col}'
        try:
            client.command(rename_sql)
            logger.success(f"已修复: {repr(dirty_col)} -> {clean_col}")
        except Exception as e:
            logger.error(f"修复失败 {repr(dirty_col)}: {e}")

    logger.info("数据库表修复完成！")

if __name__ == "__main__":
    fix_clickhouse_schema()
