"""
Semantic Prompt Formatter Deep Module.
Adheres to Matt Pocock's Deep Module design: encapsulates defensive type cast
rule derivation and prompt markdown table synthesis behind a clean interface.
"""
from typing import List, Dict, Any


class SemanticPromptFormatter:
    """将语义检索到的字段及元数据格式化为带有防御性 Cast 建议的 Prompt 注入文本"""

    @staticmethod
    def format_for_prompt(items: List[Dict[str, Any]]) -> str:
        """将检索结果格式化为带有防御性 Cast 建议的 Markdown 表格"""
        if not items:
            return "暂未检索到相关物理字段。"

        lines = [
            "| 表名 | 字段名 | 物理类型 | 语义/审计价值 | 核心编写建议 |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
        for it in items:
            dtype = it.get("type", "String")
            suggestion = "直接使用"
            col_lower = str(it.get("column", "")).lower()

            # 企业级防御性 Cast 逻辑生成
            if "string" in dtype.lower():
                if any(x in col_lower for x in ["amt", "fee", "pay", "days", "count", "age"]):
                    suggestion = f"String 数值，必须使用 toInt32OrZero({it['column']}) 或 toFloat64OrZero()"
                elif "date" in col_lower or "time" in col_lower:
                    suggestion = f"String 日期，必须使用 toDate({it['column']}) 或 toDateTime()"

            table = it.get("table", "")
            column = it.get("column", "")
            desc = it.get("desc", "")
            lines.append(f"| {table} | {column} | {dtype} | {desc} | {suggestion} |")

        return "\n".join(lines)
