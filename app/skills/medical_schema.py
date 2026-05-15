from typing import Type, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from app.schema_injector import schema_injector
from app.neo4j_manager import field_kg

class MedicalSchemaInput(BaseModel):
    keywords: str = Field(description="The keywords or intent to search for medical database fields (e.g., '重复住院', '总金额').")

class MedicalSchemaSkill(BaseTool):
    name: str = "lookup_medical_schema"
    description: str = (
        "医保业务字典与物理 Schema 映射中心。当你需要将业务需求（如“重复住院”、“个人账户支付”）转化成数据库字段时，**必须**调用此工具。 "
        "它不仅返回物理表结构（DDL），还包含字段的业务定义、敏感字段提示以及“避坑指南”。 "
        "在构建任何审计逻辑或编写 SQL 之前，优先通过此工具核实物理真相，严禁凭直觉猜测字段名。"
    )
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
