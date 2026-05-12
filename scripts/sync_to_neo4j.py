
from loguru import logger
from app.db_conn import get_clickhouse_client
from app.neo4j_manager import neo4j_manager
from dotenv import load_dotenv

load_dotenv()

def sync_clickhouse_to_neo4j(limit: int = 50000):
    """
    [企业级] ETL 侧载管道：将 ClickHouse 关系型数据同步至 Neo4j 图数据库。
    采用 UNWIND 批量写入模式，优化海量数据导入性能。
    """
    logger.info(f"🚀 启动图谱数据同步流水线 (Limit: {limit})...")
    
    try:
        # 1. 从 ClickHouse 提取种子关联数据
        ck = get_clickhouse_client()
        sql = f"""
        SELECT 
            psn_no, 
            fixmedins_code, 
            fixmedins_name, 
            tel, 
            SUM(medfee_sumamt) as total_amt,
            COUNT(*) as visit_count
        FROM fqz_gz_jzsj_all_ql
        WHERE psn_no != '' AND tel != ''
        GROUP BY psn_no, fixmedins_code, fixmedins_name, tel
        ORDER BY total_amt DESC
        LIMIT {limit}
        """
        rows = ck.query(sql)
        if not rows:
            logger.warning("⚠️ ClickHouse 未返回任何有效关联数据，请检查数据源。")
            return
            
        logger.info(f"🚚 成功提取 {len(rows)} 条关联记录，准备写入 Neo4j...")

        # 2. 批量写入 Neo4j
        driver = neo4j_manager.get_driver()
        with driver.session() as session:
            # 使用 UNWIND 优化批量写入
            # 逻辑：创建 Patient, Hospital, Phone 节点并建立关系
            cypher = """
            UNWIND $rows AS row
            // 创建节点
            MERGE (p:Patient {psn_no: row.psn_no})
            MERGE (h:Hospital {fixmedins_code: row.fixmedins_code})
            ON CREATE SET h.name = row.fixmedins_name
            MERGE (t:Phone {tel: row.tel})
            
            // 建立关系
            MERGE (p)-[v:VISITED]->(h)
            ON CREATE SET v.total_amt = row.total_amt, v.count = row.visit_count
            ON MATCH SET v.total_amt = v.total_amt + row.total_amt, v.count = v.count + row.visit_count
            
            MERGE (p)-[:HAS_PHONE]->(t)
            """
            
            # 针对 clickhouse_connect 返回的 Dict 列表，Neo4j 可以直接接收
            session.run(cypher, rows=rows)
            
        logger.success(f"✅ [Neo4j] 同步完成。已构建 {len(rows)} 组核心关联链路。")
        
    except Exception as e:
        logger.error(f"❌ 数据同步过程中发生异常: {e}")

if __name__ == "__main__":
    # 默认同步 5 万条记录，涵盖主要高风险团伙范围
    sync_clickhouse_to_neo4j(limit=50000)
