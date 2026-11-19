import re
import json
from dataclasses import dataclass
from typing import Any, List, Optional
import sqlglot

from app.core.protocol.clickhouse_healer import ClickHouseDialectHealer

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
    def fix_shadowing_aliases(cls, sql: str) -> str:
        """[Seam 接缝委托] 委托给专门的 ClickHouseDialectHealer 深模块治理 AST"""
        return ClickHouseDialectHealer.heal(sql)

    @classmethod
    def clean_sql_ast(cls, sql: str) -> str:
        """[Seam 接缝委托] 委托给 ClickHouseDialectHealer 消除语法杂质与别名遮蔽"""
        return ClickHouseDialectHealer.heal(sql)

    TOOL_ALIASES = {
        "write_audit_notes": "write_audit_note",
        "read_audit_note": "read_all_audit_notes",
        "read_audit_notes": "read_all_audit_notes",
    }

    @classmethod
    def normalize(cls, raw_content: Any, existing_tool_calls: Optional[List[dict]] = None) -> NormalizedToolCallResult:
        # 若已有原生合法的 tool_calls，对其名称进行别名归一化，并清洗 SQL 参数脏标记
        if existing_tool_calls:
            first_sql = None
            clean_calls = []
            for tc in existing_tool_calls:
                tc_clean = dict(tc)
                tc_name = tc_clean.get("name")
                if tc_name in cls.TOOL_ALIASES:
                    tc_clean["name"] = cls.TOOL_ALIASES[tc_name]

                args = tc_clean.get("args") or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        pass
                if isinstance(args, dict) and "sql" in args:
                    clean_s = cls.clean_sql_ast(args["sql"])
                    if not first_sql and clean_s:
                        first_sql = clean_s
                    tc_clean["args"] = dict(args)
                    tc_clean["args"]["sql"] = clean_s
                clean_calls.append(tc_clean)
            return NormalizedToolCallResult(tool_calls=clean_calls, synthesized_sql=first_sql, is_synthesized=False)

        content_str = str(raw_content) if raw_content is not None else ""
        synthesized_sql = None

        # 方言 0.1: <call:tool_name{json_args}> (Claude / Custom Tool Calling 格式)
        call_match = re.search(r"<call:(\w+)\s*(\{[\s\S]*?\})>?", content_str)
        if call_match:
            tname = call_match.group(1).strip()
            tname = cls.TOOL_ALIASES.get(tname, tname)
            try:
                args = json.loads(call_match.group(2).strip())
                if isinstance(args, dict) and "sql" in args:
                    clean_s = cls.clean_sql_ast(args["sql"])
                    if cls._is_valid_sql_ast(clean_s):
                        args["sql"] = clean_s
                        synthesized_sql = clean_s
                return NormalizedToolCallResult(
                    tool_calls=[{
                        "name": tname,
                        "args": args,
                        "id": "call_syntax_synthesized"
                    }],
                    synthesized_sql=synthesized_sql,
                    is_synthesized=True
                )
            except Exception:
                pass

        # 方言 0: 工业级 DSML / XML invoke 结构解析 (如 <｜｜DSML｜｜ invoke name="...">...)
        invokes = list(re.finditer(
            r"<[^>]*?invoke\s+name=[\"']?([^\"'\s>]+)[\"']?[^>]*>([\s\S]*?)(?:</[^>]*?invoke\s*>|$)",
            content_str,
            re.IGNORECASE
        ))
        if invokes:
            synthesized_calls = []
            for idx, inv in enumerate(invokes):
                tname = inv.group(1).strip()
                tname = cls.TOOL_ALIASES.get(tname, tname)
                body = inv.group(2)
                params = {}
                for pm in re.finditer(
                    r"<[^>]*?parameter\s+name=[\"']?([^\"'\s>]+)[\"']?[^>]*>([\s\S]*?)(?:</[^>]*?parameter\s*>|$)",
                    body,
                    re.IGNORECASE
                ):
                    params[pm.group(1).strip()] = pm.group(2).strip()

                if "sql" in params:
                    clean_s = cls.clean_sql_ast(params["sql"])
                    if cls._is_valid_sql_ast(clean_s):
                        params["sql"] = clean_s
                        if not synthesized_sql:
                            synthesized_sql = clean_s
                elif tname == "execute_audit_sql" and not params:
                    clean_s = cls.clean_sql_ast(body)
                    if cls._is_valid_sql_ast(clean_s):
                        params = {"sql": clean_s}
                        if not synthesized_sql:
                            synthesized_sql = clean_s

                synthesized_calls.append({
                    "name": tname,
                    "args": params,
                    "id": f"call_dsml_synthesized_{idx}"
                })

            if synthesized_calls:
                return NormalizedToolCallResult(
                    tool_calls=synthesized_calls,
                    synthesized_sql=synthesized_sql,
                    is_synthesized=True
                )

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
                if cls._is_valid_sql_ast(cand):
                    synthesized_sql = cand

        # 方言 4: Markdown 代码块 (```sql ... ```)
        if not synthesized_sql:
            code_blocks = re.findall(r"```(?:sql)?\s*([\s\S]*?)\s*```", content_str, re.IGNORECASE)
            for block in code_blocks:
                cand = cls.clean_sql_ast(block.strip())
                if cls._is_valid_sql_ast(cand):
                    synthesized_sql = cand
                    break

        # 方言 5: 裸 SQL 抽取 (包含 WITH CTE 与 SELECT)
        if not synthesized_sql:
            raw_matches = re.finditer(
                r"\b((?:WITH\b[\s\S]*?\bSELECT\b|SELECT\b)[^;`]{10,1000}\bFROM\s+fqz_[a-zA-Z0-9_]+[^;`]*?)(?:;|\n\s*\n|`|$)",
                content_str,
                re.IGNORECASE
            )
            for m in raw_matches:
                cand = cls.clean_sql_ast(m.group(1).strip())
                if cls._is_valid_sql_ast(cand):
                    synthesized_sql = cand
                    break

        if synthesized_sql and cls._is_valid_sql_ast(synthesized_sql):
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
        if (clean.startswith("SELECT") or clean.startswith("WITH")) and "FROM" in clean:
            return True
        if clean.startswith("DESCRIBE") or clean.startswith("DESC ") or clean.startswith("SHOW "):
            return True
        return False

    @classmethod
    def _is_valid_sql_ast(cls, s: str) -> bool:
        """严格 AST 校验：确认候选文本确实为有效的 ClickHouse SQL 查询，防止自然语言段落被误合成工具调用"""
        if not s or not cls._is_sql_head(s):
            return False
        clean = re.sub(r"--[^\n]*", "", s).strip().upper()
        if clean.startswith("DESCRIBE") or clean.startswith("DESC ") or clean.startswith("SHOW "):
            return True

        # [确定性接缝安全网] 拦截系统元数据表与臆造系统表，严禁自愈合成为审计工具调用
        forbidden_metadata_tables = ("SQLITE_MASTER", "INFORMATION_SCHEMA", "SYSTEM.TABLES", "SYSTEM.COLUMNS", "PG_CATALOG")
        if any(fbt in clean for fbt in forbidden_metadata_tables):
            return False

        try:
            parsed = sqlglot.parse_one(s, read="clickhouse")
            if parsed is None:
                return False
            from sqlglot import exp
            
            # 提取所有 Table 节点进行表名合法性校验
            tables = list(parsed.find_all(exp.Table))
            if tables:
                for tbl in tables:
                    tname = tbl.name or ""
                    # 1. 严禁中文表名（如《定点医药机构宏观月度费用统计报表》），此类多为大模型客服回复中的伪代码示例
                    if any(ord(c) > 127 for c in tname):
                        return False
                    # 2. 严禁 sqlite_master 等系统表
                    if tname.lower() in ("sqlite_master", "sqlite_sequence", "tables", "columns"):
                        return False

            if isinstance(parsed, (exp.Select, exp.Union, exp.Describe)):
                return True
            if hasattr(parsed, "this") and isinstance(parsed.this, (exp.Select, exp.Union, exp.Describe)):
                return True
            return False
        except Exception:
            return False

