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
    def fix_shadowing_aliases(cls, sql: str) -> str:
        """
        [AST 级物理语法自愈]
        1. 修复 ClickHouse 聚合别名遮蔽物理列问题 (Code: 184 ILLEGAL_AGGREGATION)：
           当 SELECT 中的聚合别名与 WHERE/PREWHERE 子句中使用的物理列名同名时
           (例如 min(setl_time) AS setl_time ... WHERE setl_time >= ...)，
           ClickHouse 会将 WHERE 中的列解析为别名（即聚合函数），从而抛出非法聚合报错。
           本方法将同名聚合别名自动重命名为 {agg_func}_{col_name}。
        2. 修复 ClickHouse 字面量/非纯列别名遮蔽物理列问题 (查询结果全表匹配/逻辑失效)：
           当 SELECT 中的别名与 WHERE/PREWHERE 子句中使用的物理列名同名，
           且该别名并非原列直接透传 (例如 '999999999999' AS psn_no ... WHERE psn_no = '999999999999')，
           ClickHouse 会在 WHERE 中用别名表达式替代物理列计算，导致条件恒真 (如 '999999999999' = '999999999999')。
           自愈策略：为 WHERE/PREWHERE 中的未限定物理列补齐表限定符 (如 fqz_fymx_test.psn_no)，
           或在无明确表名时将别名安全重命名为 target_{col_name}。
        3. 修复 ClickHouse 中文/非 ASCII 标识符裸别名语法错误 (Code: 62 SYNTAX_ERROR)：
           大模型生成的裸中文别名 (例如 AS 费用明细总笔数) 会导致词法分析器报错。
           自动为其包裹引号转化为安全标识符。
        """
        if not sql:
            return sql
        try:
            from sqlglot import exp
            parsed = sqlglot.parse_one(sql, read="clickhouse")
            if not parsed:
                return sql

            modified = False
            for select_node in parsed.find_all(exp.Select):
                where_node = select_node.args.get("where")
                prewhere_node = select_node.args.get("prewhere")
                if not where_node and not prewhere_node:
                    for expr in select_node.selects:
                        if isinstance(expr, exp.Alias):
                            raw_alias = expr.alias
                            needs_quote = any(ord(c) > 127 for c in raw_alias) or not raw_alias.isidentifier()
                            current_ident = expr.args.get("alias")
                            is_already_quoted = getattr(current_ident, "quoted", False)
                            if needs_quote and not is_already_quoted:
                                expr.set("alias", exp.to_identifier(raw_alias, quoted=True))
                                modified = True
                    continue

                from_node = select_node.args.get("from_") or select_node.args.get("from")
                table_target = None
                if from_node:
                    tbl = from_node.find(exp.Table)
                    if tbl:
                        table_target = tbl.alias or tbl.name

                filter_cols = set()
                for fn in (where_node, prewhere_node):
                    if fn:
                        for col in fn.find_all(exp.Column):
                            filter_cols.add(col.name.lower())

                shadow_cols_to_qualify = set()
                for expr in select_node.selects:
                    if isinstance(expr, exp.Alias):
                        raw_alias = expr.alias
                        alias_name = raw_alias.lower()
                        has_agg = bool(list(expr.find_all(exp.AggFunc)))
                        is_literal = isinstance(expr.this, exp.Literal)
                        is_not_plain_col = not (isinstance(expr.this, exp.Column) and expr.this.name.lower() == alias_name)

                        target_alias = raw_alias
                        if filter_cols and has_agg and (alias_name in filter_cols):
                            agg_node = next(expr.find_all(exp.AggFunc))
                            func_name = agg_node.key.lower() if hasattr(agg_node, "key") else "agg"
                            target_alias = f"{func_name}_{raw_alias}"
                            modified = True
                        elif filter_cols and (alias_name in filter_cols) and (is_literal or is_not_plain_col):
                            if table_target:
                                shadow_cols_to_qualify.add(alias_name)
                            else:
                                target_alias = f"target_{raw_alias}"
                                modified = True

                        needs_quote = any(ord(c) > 127 for c in target_alias) or not target_alias.isidentifier()
                        current_ident = expr.args.get("alias")
                        is_already_quoted = getattr(current_ident, "quoted", False)
                        if needs_quote and not is_already_quoted:
                            expr.set("alias", exp.to_identifier(target_alias, quoted=True))
                            modified = True
                        elif target_alias != raw_alias:
                            expr.set("alias", exp.to_identifier(target_alias))
                            modified = True

                if shadow_cols_to_qualify and table_target:
                    for fn in (where_node, prewhere_node):
                        if fn:
                            for col in fn.find_all(exp.Column):
                                if not col.table and col.name.lower() in shadow_cols_to_qualify:
                                    col.set("table", exp.to_identifier(table_target))
                                    modified = True

            if modified:
                return parsed.sql(dialect="clickhouse")
            return sql
        except Exception:
            return sql

    @classmethod
    def clean_sql_ast(cls, sql: str) -> str:
        """剥离首尾残留的 Markdown 代码块、XML/DSML 闭合标签与 JSON 结构杂质，严格保护 SQL 单引号字面量并修复别名遮蔽"""
        if not sql:
            return ""

        cand = sql.strip()
        # 0. 前置剥除可能包裹的 markdown 代码块标签 (```sql ... ``` 或 ``` ... ```)
        cand = re.sub(r'^```(?:sql)?\s*', '', cand, flags=re.IGNORECASE).strip()
        cand = re.sub(r'\s*```+$', '', cand).strip()
        cand = cand.rstrip(';； \n\r\t')

        # 1. 若已完全符合 ClickHouse 语法，保留原有单引号，只剔除分号空白并自愈别名遮蔽
        try:
            sqlglot.parse_one(cand, read="clickhouse")
            return cls.fix_shadowing_aliases(cand)
        except Exception:
            pass

        # 2. 切除任何 XML / DSML / HTML 结束标签及其后内容 (匹配任意形式的 </...>)
        cand = re.split(r'</[^>]+>', cand)[0].strip()

        # 3. 剥除首尾残留的 markdown 标记
        cand = re.sub(r'^```(?:sql)?\s*', '', cand, flags=re.IGNORECASE).strip()
        cand = re.sub(r'\s*```+$', '', cand).strip()

        # 4. 剥除末尾残留的 JSON 闭合符号与转义杂质 (严禁剥除 SQL 字符串字面量单引号 ')
        cand = re.sub(r'["\}\]\s]+$', '', cand).strip().rstrip(';； \n\r\t')

        # 再次尝试 AST 解析确认
        try:
            sqlglot.parse_one(cand, read="clickhouse")
            return cls.fix_shadowing_aliases(cand)
        except Exception:
            pass

        # 5. 容错修复：如果单引号不成对（奇数个），尝试修复末尾单引号
        if cand.count("'") % 2 == 1:
            if cand.endswith("'"):
                cand_fixed = cand[:-1].strip()
                try:
                    sqlglot.parse_one(cand_fixed, read="clickhouse")
                    return cls.fix_shadowing_aliases(cand_fixed)
                except Exception:
                    pass
            else:
                cand_fixed = cand + "'"
                try:
                    sqlglot.parse_one(cand_fixed, read="clickhouse")
                    return cls.fix_shadowing_aliases(cand_fixed)
                except Exception:
                    pass

        return cls.fix_shadowing_aliases(cand)

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
        try:
            parsed = sqlglot.parse_one(s, read="clickhouse")
            if parsed is None:
                return False
            from sqlglot import exp
            if isinstance(parsed, (exp.Select, exp.Union, exp.Describe)):
                return True
            if hasattr(parsed, "this") and isinstance(parsed.this, (exp.Select, exp.Union, exp.Describe)):
                return True
            return False
        except Exception:
            return False

