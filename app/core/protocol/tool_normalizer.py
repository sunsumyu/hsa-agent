import re
import json
from dataclasses import dataclass
from typing import Any, List, Optional
import sqlglot

@dataclass(frozen=True)
class NormalizedToolCallResult:
    tool_calls: List[dict]
    synthesized_sql: Optional[str]
    is_synthesized: bool

class ToolResponseNormalizer:
    """
    工业级大模型工具调用输入网关 (Tool Ingestion Gateway)。
    屏蔽各大模型服务商、反向代理、不同推理引擎吐出的非标准结构与残留标签。
    """
    
    @classmethod
    def clean_sql_ast(cls, sql: str) -> str:
        """剥离尾部残留的 XML/DSML 闭合标签与 JSON 结构杂质，严格保护 SQL 单引号字面量"""
        if not sql:
            return ""

        cand = sql.strip().rstrip(';； \n\r\t')
        # 0. 若已完全符合 ClickHouse 语法，保留原有单引号，只剔除分号空白
        try:
            sqlglot.parse_one(cand, read="clickhouse")
            return cand
        except Exception:
            pass

        # 1. 切除任何 XML / DSML / HTML 结束标签及其后内容 (匹配任意形式的 </...>)
        cand = re.split(r'</[^>]+>', cand)[0].strip()

        # 2. 剥除末尾残留的 markdown 标记
        cand = re.sub(r'```+$', '', cand).strip()

        # 3. 剥除末尾残留的 JSON 闭合符号与转义杂质 (严禁剥除 SQL 字符串字面量单引号 ')
        cand = re.sub(r'["\}\]\s]+$', '', cand).strip().rstrip(';； \n\r\t')

        # 再次尝试 AST 解析确认
        try:
            sqlglot.parse_one(cand, read="clickhouse")
            return cand
        except Exception:
            pass

        # 4. 容错修复：如果单引号不成对（奇数个），尝试修复末尾单引号
        if cand.count("'") % 2 == 1:
            if cand.endswith("'"):
                cand_fixed = cand[:-1].strip()
                try:
                    sqlglot.parse_one(cand_fixed, read="clickhouse")
                    return cand_fixed
                except Exception:
                    pass
            else:
                cand_fixed = cand + "'"
                try:
                    sqlglot.parse_one(cand_fixed, read="clickhouse")
                    return cand_fixed
                except Exception:
                    pass

        return cand

    @classmethod
    def normalize(cls, raw_content: Any, existing_tool_calls: Optional[List[dict]] = None) -> NormalizedToolCallResult:
        # 若已有原生合法的 tool_calls，仍对其参数内部的 SQL 进行清洗，去除残留脏标记
        if existing_tool_calls:
            first_sql = None
            clean_calls = []
            for tc in existing_tool_calls:
                args = tc.get("args") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        pass
                if isinstance(args, dict) and "sql" in args:
                    clean_s = cls.clean_sql_ast(args["sql"])
                    if not first_sql and clean_s:
                        first_sql = clean_s
                    tc_clean = dict(tc)
                    tc_clean["args"] = dict(args)
                    tc_clean["args"]["sql"] = clean_s
                    clean_calls.append(tc_clean)
                else:
                    clean_calls.append(tc)
            return NormalizedToolCallResult(tool_calls=clean_calls, synthesized_sql=first_sql, is_synthesized=False)

        content_str = str(raw_content) if raw_content is not None else ""
        synthesized_sql = None

        # 方言 1: <tool_call> JSON 结构
        tc_json = re.search(r"<tool_call>\s*(\{[\s\S]*?\})\s*(?:</tool_call>|$)", content_str)
        if tc_json:
            try:
                payload = json.loads(tc_json.group(1).strip())
                args = payload.get("arguments") or payload.get("args") or {}
                if isinstance(args, str):
                    args = json.loads(args)
                if isinstance(args, dict) and "sql" in args:
                    synthesized_sql = cls.clean_sql_ast(args["sql"])
            except Exception:
                pass

        # 方言 2: JSON 字段 "sql": "..."
        if not synthesized_sql and ('"execute_audit_sql"' in content_str or '<tool_call>' in content_str):
            sql_field = re.search(r'"sql"\s*:\s*"((?:[^"\\]|\\.)*)"', content_str)
            if sql_field:
                try:
                    cand = json.loads('"' + sql_field.group(1) + '"')
                    synthesized_sql = cls.clean_sql_ast(cand)
                except Exception:
                    pass

        # 方言 3: DSML / XML 工具调用 (<arg_value> 或 parameter 或 <execute_audit_sql>，兼容全角符号)
        if not synthesized_sql:
            xml_match = re.search(
                r"(?:<arg_value>|<[^>]*?parameter[^>]*>|<execute_audit_sql>)\s*([\s\S]*?)(?:</[^>]+>|$)",
                content_str,
                re.IGNORECASE
            )
            if xml_match:
                cand = cls.clean_sql_ast(xml_match.group(1).strip())
                if cls._is_sql_head(cand):
                    synthesized_sql = cand

        # 方言 4: Markdown 代码块 (```sql ... ```)
        if not synthesized_sql:
            code_blocks = re.findall(r"```(?:sql)?\s*([\s\S]*?)\s*```", content_str, re.IGNORECASE)
            for block in code_blocks:
                cand = cls.clean_sql_ast(block.strip())
                if cls._is_sql_head(cand):
                    synthesized_sql = cand
                    break

        # 方言 5: 裸 SQL 抽取 (包含 WITH CTE 与 SELECT)
        if not synthesized_sql:
            raw_match = re.search(
                r"\b((?:WITH\b[\s\S]*?\bSELECT\b|SELECT\b)[\s\S]*?\bFROM\s+fqz_[a-zA-Z0-9_]+[\s\S]*?)(?:;|\n\n|$)",
                content_str,
                re.IGNORECASE
            )
            if raw_match:
                cand = cls.clean_sql_ast(raw_match.group(1).strip())
                if cls._is_sql_head(cand):
                    synthesized_sql = cand

        if synthesized_sql:
            return NormalizedToolCallResult(
                tool_calls=[{
                    "name": "execute_audit_sql",
                    "args": {"sql": synthesized_sql},
                    "id": "call_normalized_synthesized"
                }],
                synthesized_sql=synthesized_sql,
                is_synthesized=True
            )

        return NormalizedToolCallResult(tool_calls=[], synthesized_sql=None, is_synthesized=False)

    @classmethod
    def _is_sql_head(cls, s: str) -> bool:
        clean = re.sub(r"--[^\n]*", "", s).strip().upper()
        return (clean.startswith("SELECT") or clean.startswith("WITH")) and "FROM" in clean
