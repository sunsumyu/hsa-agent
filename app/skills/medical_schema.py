from typing import Type, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from app.schema_injector import schema_injector
from app.neo4j_manager import field_kg

class MedicalSchemaInput(BaseModel):
    keywords: str = Field(description="The keywords or intent to search for medical database fields (e.g., '重复住院', '总金额').")

class MedicalSchemaSkill(BaseTool):
    name: str = "lookup_medical_schema"
    description: str = "Search for physical database schema fields based on business keywords. Returns the FULL field list of relevant tables to avoid hallucinating field names."
    args_schema: Type[BaseModel] = MedicalSchemaInput

    def _run(self, keywords: str) -> str:
        # [V90.5] 分区分层注入：根据关键词分类定表，返回目标表全量 DDL
        # 1. 全量 DDL（主力信息源）
        ddl_hint = schema_injector.inject(user_question=keywords, include_warning=True)

        # 2. 知识图谱补充（别名映射、禁用字段提示）
        kg_hint = field_kg.format_for_prompt(max_fields=6)

        if not ddl_hint or "Schema 警告" in ddl_hint:
            if kg_hint:
                return kg_hint
            return "No matching schema fields found. Please try different keywords or use get_table_schema."

        combined = f"{ddl_hint}\n\n{kg_hint}"
        return combined

    async def _arun(self, keywords: str) -> str:
        return self._run(keywords)
