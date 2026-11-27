"""
app/core/context/funnel_hierarchy_sideload.py
===============================================
[Matt Pocock Deep Module] 语义漏斗第三层：知识图谱多跳级联与 ClickHouse 物理联邦侧载
专职负责：
1. Neo4j 连接探测与 Cypher 树状层级多跳级联
2. 物理机构编码提取与去重
3. ClickHouse 内存临时表创建与快速插入侧载
"""

import asyncio
import hashlib
import time
from typing import List, Optional
from loguru import logger

from app.infra.neo4j_manager import neo4j_manager
from app.infra.db_conn import get_clickhouse_client


async def sideload_hospital_hierarchy(levels: List[str]) -> Optional[str]:
    """【漏斗第三层】Graph Hierarchy：知识图谱多跳级联与联邦侧载至 ClickHouse 临时表"""
    if not levels:
        return None
    
    # 1. 检测 Neo4j 是否连接
    if not neo4j_manager.is_connected:
        try:
            neo4j_manager.get_driver()
        except Exception:
            logger.warning("⚠️ [Funnel] Neo4j 服务不可达，将通过内存物理规则对齐机构编码")
            return None

    logger.info(f"🕸️ [Funnel] 启动图谱多跳关联分析: {levels}")
    
    # 2. 构造 Cypher 进行上下位层级多跳级联获取所有的 fixmedins_code
    cypher = """
    MATCH (h:Hospital)-[:BELONGS_TO*1..2]->(lv:Level)
    WHERE any(item IN $levels WHERE lv.name CONTAINS item)
    RETURN h.fixmedins_code AS code
    """
    
    try:
        def _exec_cypher():
            with neo4j_manager.get_driver().session() as session:
                res = session.run(cypher, {"levels": levels})
                return [record["code"] for record in res if record["code"]]
                
        hospital_codes = await asyncio.to_thread(_exec_cypher)
        hospital_codes = list(set(hospital_codes))
        
        if not hospital_codes:
            logger.warning(f"[Funnel] 图谱多跳返回空节点，无法生成侧载临时表。")
            return None
            
        # 3. 物理联邦侧载：写入 ClickHouse 内存临时表
        batch_id = hashlib.md5(f"{time.time()}_{len(hospital_codes)}".encode()).hexdigest()[:8]
        temp_table = f"fqz_temp_sl_{batch_id}"
        
        client = get_clickhouse_client()
        create_sql = f"CREATE TABLE IF NOT EXISTS {temp_table} (id String) ENGINE = Memory"
        
        # 使用 clickhouse-connect 执行物理侧载
        if hasattr(client.client, 'execute'):
            client.client.execute(create_sql)
            client.client.execute(f"INSERT INTO {temp_table} (id) VALUES", [(x,) for x in hospital_codes])
        else:
            client.client.command(create_sql)
            client.client.insert(temp_table, [[x] for x in hospital_codes], column_names=['id'])
            
        logger.success(f"✅ [Funnel] 联邦侧载成功！图谱关联 {len(hospital_codes)} 家机构侧载至 ClickHouse 临时表: {temp_table}")
        return temp_table
        
    except Exception as e:
        logger.error(f"❌ [Funnel] 联邦侧载失败: {e}")
        return None
