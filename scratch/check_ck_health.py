from app.infra.db_conn import get_clickhouse_client
ck_client = get_clickhouse_client()
from loguru import logger

def check_health():
    logger.info(">>> 检查 ClickHouse Mutation 进度...")
    mutations = ck_client.query("SELECT mutation_id, command, is_done FROM system.mutations WHERE is_done = 0").result_rows
    if not mutations:
        logger.success("✅ 所有物理清洗任务已完成，数据库处于最优状态。")
    else:
        logger.warning(f"⚠️ 发现 {len(mutations)} 个正在运行的 Mutation 任务：")
        for m in mutations:
            logger.info(f"   ID: {m[0]} | Command: {m[1][:50]}...")

    logger.info(">>> 测试优化后的跨院重叠算子性能...")
    # 测试 SQL 性能（不带 LIMIT，看 count）
    try:
        start_time = 0
        test_sql = """
            SELECT count() FROM (
                SELECT psn_no, count(DISTINCT fixmedins_code) as hosp_count
                FROM fqz_gz_jzsj_all_ql
                WHERE toYear(toDateTime(setl_time)) = 2024
                GROUP BY psn_no, toDate(setl_time)
                HAVING hosp_count > 1
            )
        """
        res = ck_client.query(test_sql).result_rows
        logger.success(f"✅ 优化算子执行成功，命中异常：{res[0][0]} 条")
    except Exception as e:
        logger.error(f"❌ 算子执行失败: {e}")

if __name__ == "__main__":
    check_health()
