"""
app/skills/safe_math_evaluator.py
=================================
安全数学表达式 AST 求值引擎（Deep Module）

职责：
- 严格限制数学表达式输入，防止恶意代码执行与 eval 逃逸攻击
- 基于 Python AST 解析白名单运算符与数值常量
"""

from __future__ import annotations

import ast
import operator
import re
from typing import Dict, Any, Union

_SAFE_EXPR_RE = re.compile(r"^[\d\s\.\+\-\*\/\(\)\%]+$")

_CALC_ALLOWED_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}

# Pow 指数绝对值上限：超过即拒绝，杜绝 9**9**9**9 这类超大整数运算耗尽 CPU/内存 (DoS)。
# 64 已足够覆盖常规业务计算（如复利、面积换算），同时把结果位数约束在极小范围内。
_MAX_POW_EXPONENT = 64


def is_safe_math_expr(expr: str) -> bool:
    """
    检查数学表达式是否只包含安全字符。
    """
    if not expr or not isinstance(expr, str):
        return False
    return bool(_SAFE_EXPR_RE.match(expr.strip()))


def safe_eval_math_expression(expr: str) -> float:
    """
    安全的数学表达式求值器。
    只允许数字和基本算术运算符，禁止任何名称访问、属性访问或函数调用。
    """
    if not expr or not isinstance(expr, str):
        raise ValueError("表达式不能为空")

    clean_expr = expr.strip()
    try:
        tree = ast.parse(clean_expr, mode="eval")
    except SyntaxError as e:
        raise ValueError(f"非法表达式语法: {clean_expr}") from e

    def _eval(node: ast.AST) -> Union[int, float]:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        elif isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ValueError(f"不允许的类型: {type(node.value)}")
        elif isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in _CALC_ALLOWED_OPS:
                raise ValueError(f"不允许的操作符: {op_type}")
            left = _eval(node.left)
            right = _eval(node.right)
            # Pow 防护：先校验指数绝对值再计算，防止超大整数运算导致 DoS
            if op_type is ast.Pow and abs(right) > _MAX_POW_EXPONENT:
                raise ValueError(
                    f"指数过大: {right} (安全上限 ±{_MAX_POW_EXPONENT})"
                )
            try:
                return _CALC_ALLOWED_OPS[op_type](left, right)
            except ZeroDivisionError as e:
                raise ValueError("除数不能为零") from e
        elif isinstance(node, ast.UnaryOp):
            op_type = type(node.op)
            if op_type not in _CALC_ALLOWED_OPS:
                raise ValueError(f"不允许的单目操作符: {op_type}")
            return _CALC_ALLOWED_OPS[op_type](_eval(node.operand))
        else:
            raise ValueError(f"不允许的表达式节点类型: {type(node).__name__}")

    res = _eval(tree)
    return float(res)
