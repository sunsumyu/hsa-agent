"""
BFCL 函数定义 -> OpenAI tools schema。

BFCL 的函数定义使用 Python 风格类型 (dict / float / tuple / any)，函数名可能带点号
(例如 `math.factorial`)，而 OpenAI/Anthropic 的工具名只允许 `^[a-zA-Z0-9_-]+$`。
这里做两件事：
1. 递归转换类型到 JSON Schema；
2. 把非法字符替换掉，并返回 {安全名: 原始名} 映射，便于把模型输出还原成 BFCL 原始函数名。
"""

import copy
import re
from typing import Any, Dict, List, Tuple

# 对齐官方 bfcl_eval.constants.type_mappings.GORILLA_TO_OPENAPI
_TYPE_MAP = {
    "integer": "integer",
    "number": "number",
    "float": "number",
    "string": "string",
    "boolean": "boolean",
    "bool": "boolean",
    "array": "array",
    "list": "array",
    "dict": "object",
    "object": "object",
    "tuple": "array",
    "any": "string",
    "byte": "integer",
    "short": "integer",
    "long": "integer",
    "double": "number",
    "char": "string",
    "ArrayList": "array",
    "Array": "array",
    "HashMap": "object",
    "Hashtable": "object",
    "Queue": "array",
    "Stack": "array",
    "Any": "string",
    "String": "string",
    "Bigint": "integer",
}

_UNSAFE_NAME_CHARS = re.compile(r"[^a-zA-Z0-9_-]")


def safe_tool_name(name: str) -> str:
    return _UNSAFE_NAME_CHARS.sub("_", name)


def _convert_schema(node: Any) -> Any:
    if isinstance(node, list):
        return [_convert_schema(x) for x in node]
    if not isinstance(node, dict):
        return node

    out: Dict[str, Any] = {}
    for key, value in node.items():
        if key == "type" and isinstance(value, str):
            out[key] = _TYPE_MAP.get(value, "string")
        elif key == "properties" and isinstance(value, dict):
            out[key] = {k: _convert_schema(v) for k, v in value.items()}
        elif key in ("items", "additionalProperties", "anyOf", "oneOf"):
            out[key] = _convert_schema(value)
        else:
            out[key] = copy.deepcopy(value)

    # array 必须有 items，否则部分网关会直接 400
    if out.get("type") == "array" and "items" not in out:
        out["items"] = {"type": "string"}
    return out


def to_openai_tools(functions: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, str]]:
    """返回 (OpenAI tools 列表, {安全名: BFCL 原始函数名})。"""
    tools: List[Dict[str, Any]] = []
    name_map: Dict[str, str] = {}
    for fn in functions:
        original = fn["name"]
        safe = safe_tool_name(original)
        name_map[safe] = original

        params = _convert_schema(fn.get("parameters") or {"type": "dict", "properties": {}})
        params["type"] = "object"
        params.setdefault("properties", {})

        description = fn.get("description", "")
        if safe != original:
            # 与官方 FC handler 一致：告知模型原始函数名
            description = f"{description} Note that the provided function is in Python 3 syntax."
        tools.append({
            "type": "function",
            "function": {"name": safe, "description": description, "parameters": params},
        })
    return tools, name_map
