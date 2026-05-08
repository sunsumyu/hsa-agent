import asyncio
from typing import Type, Dict, Any, Union
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from loguru import logger

class SQLExecutionInput(BaseModel):
    sql: str = Field(description="The ClickHouse SQL query to execute. Must be a valid read-only SELECT statement.")

class SQLSafeExecutionSkill(BaseTool):
    name: str = "build_and_validate_sql"
    description: str = "Safely execute a generated SQL query on the database. It includes built-in validation, syntax checking, and safe physical execution. Do NOT use evaluator/critic nodes to fix SQL errors; rely on the error messages returned by this tool."
    args_schema: Type[BaseModel] = SQLExecutionInput

    async def _arun(self, sql: str) -> Union[str, Dict[str, Any]]:
        from app.security import SQLGuardian
        from app.db_conn import get_clickhouse_client
        from app.tools import _clean_encrypted_fields
        
        logger.info(f"🛡️ [Skill] Validating and Executing SQL...")
        
        try:
            safe_sql = SQLGuardian.validate_sql(sql)
            
            client = get_clickhouse_client()
            result = await asyncio.to_thread(client.query, safe_sql)
            
            cols = result.column_names
            records = [{cols[j]: row[j] for j in range(len(cols))} for row in result.result_rows]
            clean_records = _clean_encrypted_fields(records)
            
            count = len(clean_records)
            logger.success(f"✅ [Skill] SQL execution succeeded, {count} records returned.")
            
            return {
                "status": "SUCCESS",
                "record_count": count,
                "records_sample": clean_records[:50],
                "methodology": f"自定义 SQL 取证查询。核查口径：{safe_sql[:200]}...",
                "sql_logic": safe_sql,
                "trace_hint": f"[SQL Execution] 执行物理查询 | 命中 {count} 条记录"
            }
            
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"⚠️ [Skill] SQL execution failed: {error_msg}")
            return {
                "status": "ERROR",
                "error_message": error_msg,
                "suggestion": "Please review the error message. If a field does not exist, use lookup_medical_schema tool to find the correct field. If syntax is wrong, correct it."
            }

    def _run(self, sql: str) -> Union[str, Dict[str, Any]]:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                return loop.create_task(self._arun(sql))
        except RuntimeError:
            pass
        return asyncio.run(self._arun(sql))
