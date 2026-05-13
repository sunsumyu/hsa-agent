import asyncio
import uuid
from typing import Type, Dict, Any, Optional, List
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from loguru import logger
from app.db_conn import get_clickhouse_client
from app.neo4j_manager import neo4j_manager
from app.perf_monitor import perf_monitor

class FederatedAuditInput(BaseModel):
    cypher_query: str = Field(description=(
        "The Cypher query to execute in Neo4j. "
        "IMPORTANT Cypher syntax rules: "
        "(1) Do NOT use SQL syntax like BETWEEN, use comparison operators instead: n.date >= '2024-01-01' AND n.date <= '2024-12-31'. "
        "(2) Use single colon for labels: (n:Patient), not (n:Patient:Person). "
        "(3) Use --> for directed relationships. "
        "(4) RETURN must include the target_field."
    ))
    target_field: str = Field(default="psn_no", description="The field name in the Cypher result to use as the primary key for the sideloader (e.g., 'psn_no', 'hosp_code').")
    description: str = Field(description="A brief description of what this federated query is looking for.")

class FederatedAuditSkill(BaseTool):
    """
    [V65.0 POE] 联邦审计侧载技能 (Sideloader Skill):
    跨库处理海量关联数据。自动在 Neo4j 中发现团伙，并在 ClickHouse 中创建临时表进行“侧载”，
    避免将海量 ID 传回大模型上下文，解决 OOM 和 SQL 长度限制问题。
    """
    name: str = "federated_graph_sideloader"
    description: str = (
        "【企业级三阶段审计技能】首先执行 Graph (Cypher) 查询发现关联团伙。 "
        "此技能会返回一个 ClickHouse 临时表名。 "
        "你必须分两步执行：(1) 调用此工具获取临时表名；(2) 在后续 SQL 中使用该表进行 JOIN。"
    )
    args_schema: Type[BaseModel] = FederatedAuditInput

    @perf_monitor.time_it("FEDERATED_SIDELOADER")
    async def _arun(self, cypher_query: str, target_field: str = "psn_no", description: str = "") -> Dict[str, Any]:
        logger.info(f"🕸️ [Sideloader] Starting Federated Query: {description}")
        
        try:
            # 1. 执行图查询
            def _exec_neo4j():
                driver = neo4j_manager.get_driver()
                with driver.session() as session:
                    result = session.run(cypher_query)
                    return [record.get(target_field) for record in result if record.get(target_field)]
            
            ids = await asyncio.to_thread(_exec_neo4j)
            count = len(ids)
            
            if count == 0:
                return {
                    "status": "SUCCESS",
                    "message": "图谱核查完成，未发现匹配的关联节点。",
                    "count": 0,
                    "raw_evidence": []
                }

            # 2. 判断是否触发侧载逻辑 (阈值设为 50)
            if count <= 50:
                logger.info(f"✅ [Sideloader] 数据量小 ({count})，直接返回内存数据。")
                return {
                    "status": "SUCCESS",
                    "message": f"图谱核查成功，发现 {count} 条记录，已直接返回。",
                    "count": count,
                    "raw_evidence": [{"psn_no": id} for id in ids[:50]]
                }

            # 3. 触发物理侧载 (Sideloader)
            logger.warning(f"🚀 [Sideloader] 数据量大 ({count})，正在执行 ClickHouse 物理侧载...")
            
            # 生成唯一的临时表名 (Session 级别)
            temp_table_name = f"tmp_sideloader_{uuid.uuid4().hex[:8]}"
            
            def _exec_clickhouse_sideload(ids_to_load):
                client = get_clickhouse_client()
                # 创建临时表
                client.command(f"CREATE TEMPORARY TABLE IF NOT EXISTS {temp_table_name} (id String) ENGINE = Memory")
                # 批量插入数据 (Sideloader 核心步骤)
                # 将 ID 列表转化为嵌套列表以符合 clickhouse_connect 的要求
                data = [[str(i)] for i in ids_to_load]
                client.insert(temp_table_name, data, column_names=['id'])
                return temp_table_name

            await asyncio.to_thread(_exec_clickhouse_sideload, ids)
            
            # 4. 返回语义代理结果
            return {
                "status": "SIDELOADED",
                "message": (
                    f"⚠️ [物理侧载完成] 发现海量关联数据 ({count} 条)。\n"
                    f"为了性能优化，数据已自动载入 ClickHouse 临时表 `{temp_table_name}`。\n"
                    f"请直接编写 SQL 进行 JOIN 关联查询，例如：\n"
                    f"SELECT SUM(medfee_sumamt) FROM fqz_gz_jzsj_all_ql "
                    f"INNER JOIN {temp_table_name} ON fqz_gz_jzsj_all_ql.{target_field} = {temp_table_name}.id"
                ),
                "temp_table": temp_table_name,
                "count": count,
                "target_field": target_field,
                "trace_hint": f"[联邦侧载] 已将 {count} 个 ID 载入临时表 {temp_table_name}"
            }

        except Exception as e:
            error_msg = f"联邦查询执行失败: {str(e)}"
            logger.error(f"❌ [Sideloader ERROR] {error_msg}")
            return {
                "status": "ERROR",
                "error_message": error_msg,
                "suggestion": "请检查 Cypher 语法或目标字段名称是否正确。"
            }

    def _run(self, *args, **kwargs):
        raise NotImplementedError("Use async version _arun")
