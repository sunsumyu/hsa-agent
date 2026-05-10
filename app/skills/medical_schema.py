from typing import Type, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool
from app.schema_injector import schema_injector
from app.neo4j_manager import field_kg

class MedicalSchemaInput(BaseModel):
    keywords: str = Field(description="The keywords or intent to search for medical database fields (e.g., '重复住院', '总金额').")

class MedicalSchemaSkill(BaseTool):
    name: str = "lookup_medical_schema"
    description: str = "Search for physical database schema fields based on business keywords to avoid hallucinating field names."
    args_schema: Type[BaseModel] = MedicalSchemaInput

    def _run(self, keywords: str) -> str:
        # 1. Try deterministic mapping from FieldKnowledgeGraph first
        kg_hint = field_kg.format_for_prompt(max_fields=6)
        
        # 2. Augment with semantic search from SchemaInjector
        injector_hint = schema_injector.inject(user_question=keywords, top_k=5, include_warning=False)
        
        correction_hint = (
            "\n**[🚨 高频错误字段纠正]**\n"
            "- 如果你想用 `det_item_name` 或 `item_name`，**必须**改用 `hilist_name`。\n"
            "- 如果你想用 `medical_category` 或 `type_name`，**必须**改用 `med_type`。\n"
            "- 如果你想用 `hosp_code`，**必须**改用 `fixmedins_code`。"
        )
        
        combined_hint = f"{kg_hint}\n\n**[语义相关字段召回]**\n{injector_hint}\n{correction_hint}"
        
        if not injector_hint or "未检索到" in injector_hint:
            if kg_hint:
                return kg_hint
            return "No matching schema fields found. Please try different keywords or use get_table_schema."
        
        return combined_hint
        
    async def _arun(self, keywords: str) -> str:
        return self._run(keywords)
