from app.db_conn import get_clickhouse_client
from loguru import logger

def verify_fixed_schema():
    client = get_clickhouse_client()
    table = "fqz_fymx_test1"
    
    # 待验证的“曾受污染”字段
    test_fields = [
        "psn_no", 
        "gend", 
        "hilist_name", 
        "fixmedins_name", 
        "setl_time", 
        "det_item_fee_sumamt"
    ]
    
    logger.info(f"正在验证修复后的表 {table} 字段访问性...")
    
    # 1. 尝试直接查询这些字段（不带任何转义和制表符）
    fields_str = ", ".join(test_fields)
    sql = f"SELECT {fields_str} FROM {table} LIMIT 5"
    
    try:
        res = client.query(sql)
        logger.success("--- [验证成功] ---")
        logger.info(f"SQL 执行成功: {sql}")
        logger.info(f"获取到 {len(res.result_rows)} 条测试数据。")
        
        # 打印一行样例，确保数据读取正确
        if res.result_rows:
            sample = dict(zip(test_fields, res.result_rows[0]))
            logger.info(f"数据样例: {sample}")
            
    except Exception as e:
        logger.error(f"--- [验证失败] ---")
        logger.error(f"字段访问异常: {e}")
        logger.info("提示：如果报错中仍出现 'Unknown expression identifier'，说明重命名操作未完全覆盖。")

if __name__ == "__main__":
    verify_fixed_schema()
