import re
import json
from dataclasses import dataclass
from typing import Any, List, Optional
import sqlglot
from loguru import logger

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
    def _normalize_existing_tool_calls(cls, existing_tool_calls: List[dict]) -> NormalizedToolCallResult:
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
                except (json.JSONDecodeError, ValueError, TypeError) as exc:
                    logger.debug(f"[ToolResponseNormalizer] JSON args parse skipped: {exc}")
            if isinstance(args, dict) and "sql" in args:
                clean_s = cls.clean_sql_ast(args["sql"])
                if not first_sql and clean_s:
                    first_sql = clean_s
                tc_clean["args"] = dict(args)
                tc_clean["args"]["sql"] = clean_s
            clean_calls.append(tc_clean)
        return NormalizedToolCallResult(tool_calls=clean_calls, synthesized_sql=first_sql, is_synthesized=False)

    @classmethod
    def _parse_call_syntax_dialect(cls, content_str: str) -> Optional[NormalizedToolCallResult]:
        call_match = re.search(r"<call:(\w+)\s*(\{[\s\S]*?\})>?", content_str)
        if not call_match:
            return None
        tname = cls.TOOL_ALIASES.get(call_match.group(1).strip(), call_match.group(1).strip())
        try:
            args = json.loads(call_match.group(2).strip())
            synthesized_sql = None
            if isinstance(args, dict) and "sql" in args:
                clean_s = cls.clean_sql_ast(args["sql"])
                if cls._is_valid_sql_ast(clean_s):
                    args["sql"] = clean_s
                    synthesized_sql = clean_s
            return NormalizedToolCallResult(
                tool_calls=[{"name": tname, "args": args, "id": "call_syntax_synthesized"}],
                synthesized_sql=synthesized_sql,
                is_synthesized=True,
            )
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.debug(f"[ToolResponseNormalizer] <call:...> dialect parse skipped: {exc}")
            return None

    @classmethod
    def _parse_dsml_invoke_dialect(cls, content_str: str) -> Optional[NormalizedToolCallResult]:
        invokes = list(re.finditer(
            r"<[^>]*?invoke\s+name=[\"']?([^\"'\s>]+)[\"']?[^>]*>([\s\S]*?)(?:</[^>]*?invoke\s*>|$)",
            content_str,
            re.IGNORECASE,
        ))
        if not invokes:
            return None
        synthesized_calls = []
        synthesized_sql = None
        for idx, inv in enumerate(invokes):
            tname = cls.TOOL_ALIASES.get(inv.group(1).strip(), inv.group(1).strip())
            body = inv.group(2)
            params = {
                pm.group(1).strip(): pm.group(2).strip()
                for pm in re.finditer(
                    r"<[^>]*?parameter\s+name=[\"']?([^\"'\s>]+)[\"']?[^>]*>([\s\S]*?)(?:</[^>]*?parameter\s*>|$)",
                    body,
                    re.IGNORECASE,
                )
            }
            if "sql" in params:
                clean_s = cls.clean_sql_ast(params["sql"])
                if cls._is_valid_sql_ast(clean_s):
                    params["sql"] = clean_s
                    synthesized_sql = synthesized_sql or clean_s
            elif tname == "execute_audit_sql" and not params:
                clean_s = cls.clean_sql_ast(body)
                if cls._is_valid_sql_ast(clean_s):
                    params = {"sql": clean_s}
                    synthesized_sql = synthesized_sql or clean_s
            synthesized_calls.append({"name": tname, "args": params, "id": f"call_dsml_synthesized_{idx}"})
        return NormalizedToolCallResult(tool_calls=synthesized_calls, synthesized_sql=synthesized_sql, is_synthesized=True)

    @classmethod
    def _extract_json_or_xml_sql(cls, content_str: str) -> Optional[str]:
        tc_json = re.search(r"<tool_call>\s*(\{[\s\S]*?\})\s*(?:</tool_call>|$)", content_str)
        if tc_json:
            try:
                payload = json.loads(tc_json.group(1).strip())
                args = payload.get("arguments") or payload.get("args") or {}
                if isinstance(args, str):
                    args = json.loads(args)
                if isinstance(args, dict) and "sql" in args:
                    return cls.clean_sql_ast(args["sql"])
            except (json.JSONDecodeError, ValueError, TypeError) as exc:
                logger.debug(f"[ToolResponseNormalizer] <tool_call> JSON parse skipped: {exc}")

        if '"execute_audit_sql"' in content_str or "<tool_call>" in content_str:
            sql_field = re.search(r'"sql"\s*:\s*"((?:[^"\\]|\\.)*)"', content_str)
            if sql_field:
                try:
                    return cls.clean_sql_ast(json.loads('"' + sql_field.group(1) + '"'))
                except (json.JSONDecodeError, ValueError, TypeError) as exc:
                    logger.debug(f"[ToolResponseNormalizer] inline sql JSON string parse skipped: {exc}")

        xml_match = re.search(
            r"(?:<arg_value>|<[^>]*?parameter[^>]*>|<execute_audit_sql>)\s*([\s\S]*?)(?:</[^>]+>|$)",
            content_str,
            re.IGNORECASE,
        )
        if xml_match:
            cand = cls.clean_sql_ast(xml_match.group(1).strip())
            if cls._is_valid_sql_ast(cand):
                return cand
        return None

    @classmethod
    def _extract_block_or_raw_sql(cls, content_str: str) -> Optional[str]:
        for block in re.findall(r"```(?:sql)?\s*([\s\S]*?)\s*```", content_str, re.IGNORECASE):
            cand = cls.clean_sql_ast(block.strip())
            if cls._is_valid_sql_ast(cand):
                return cand

        raw_matches = re.finditer(
            r"\b((?:WITH\b[\s\S]*?\bSELECT\b|SELECT\b)[^;`]{10,1000}\bFROM\s+fqz_[a-zA-Z0-9_]+[^;`]*?)(?:;|\n\s*\n|`|$)",
            content_str,
            re.IGNORECASE,
        )
        for m in raw_matches:
            cand = cls.clean_sql_ast(m.group(1).strip())
            if cls._is_valid_sql_ast(cand):
                return cand
        return None

    @classmethod
    def normalize(cls, raw_content: Any, existing_tool_calls: Optional[List[dict]] = None) -> NormalizedToolCallResult:
        if existing_tool_calls:
            return cls._normalize_existing_tool_calls(existing_tool_calls)

        content_str = str(raw_content) if raw_content is not None else ""
        call_res = cls._parse_call_syntax_dialect(content_str)
        if call_res is not None:
            return call_res

        dsml_res = cls._parse_dsml_invoke_dialect(content_str)
        if dsml_res is not None:
            return dsml_res

        synthesized_sql = cls._extract_json_or_xml_sql(content_str) or cls._extract_block_or_raw_sql(content_str)
        if synthesized_sql and cls._is_valid_sql_ast(synthesized_sql):
            return NormalizedToolCallResult(
                tool_calls=[{"name": "execute_audit_sql", "args": {"sql": synthesized_sql}, "id": "call_normalized_synthesized"}],
                synthesized_sql=synthesized_sql,
                is_synthesized=True,
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

        forbidden_metadata_tables = ("SQLITE_MASTER", "INFORMATION_SCHEMA", "SYSTEM.TABLES", "SYSTEM.COLUMNS", "PG_CATALOG")
        if any(fbt in clean for fbt in forbidden_metadata_tables):
            return False

        try:
            parsed = sqlglot.parse_one(s, read="clickhouse")
            if parsed is None:
                return False
            from sqlglot import exp

            for tbl in parsed.find_all(exp.Table):
                tname = tbl.name or ""
                if any(ord(c) > 127 for c in tname):
                    return False
                if tname.lower() in ("sqlite_master", "sqlite_sequence", "tables", "columns"):
                    return False

            if isinstance(parsed, (exp.Select, exp.Union, exp.Describe)):
                return True
            if hasattr(parsed, "this") and isinstance(parsed.this, (exp.Select, exp.Union, exp.Describe)):
                return True
            return False
        except Exception:
            return False
