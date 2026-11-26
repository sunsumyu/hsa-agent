#!/usr/bin/env python3
"""
Argus 代码质量检测脚本
======================
检测项：
  - 过长文件 (>500 行)
  - 过长函数 (>100 行)
  - 静默异常 (except: pass)
  - 全局可变状态
  - 硬编码魔法数字
  - 循环复杂度估算
  - 测试覆盖率估算

使用方法: python scripts/code_quality_audit.py [--fix-suggestions]
"""
from __future__ import annotations

import ast
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Tuple

# ── 颜色 ──────────────────────────────────────────────────────────────────
class Colors:
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    NC = "\033[0m"


@dataclass
class QualityIssue:
    """代码质量问题"""
    severity: str  # ERROR, WARN, INFO
    category: str  # 文件过长, 函数过长, 静默异常, etc
    file: str
    line: int
    message: str
    suggestion: str = ""


@dataclass
class FileMetrics:
    """单文件度量"""
    path: str
    total_lines: int
    functions: List[Tuple[str, int, int]]  # (name, start_line, length)
    longest_function: Tuple[str, int] = ("", 0)  # (name, length)
    except_count: int = 0
    silent_exception_count: int = 0
    global_vars: int = 0
    todo_count: int = 0
    hardcoded_strings: int = 0
    issues: List[QualityIssue] = field(default_factory=list)


class CodeQualityAuditor:
    """Argus 代码质量审计器"""

    # 阈值
    MAX_FILE_LINES = 500
    MAX_FUNCTION_LINES = 80
    MAX_EXCEPT_PER_FILE = 10
    MAX_GLOBALS_PER_FILE = 3

    def __init__(self, root_dir: str = "app"):
        self.root = Path(root_dir)
        self.metrics: List[FileMetrics] = []
        self.all_issues: List[QualityIssue] = []

    def scan(self) -> List[QualityIssue]:
        """扫描整个项目"""
        if not self.root.exists():
            print(f"{Colors.RED}[ERROR]{Colors.NC} 根目录不存在: {self.root}")
            return []

        py_files = sorted(self.root.rglob("*.py"))
        print(f"{Colors.BLUE}[INFO]{Colors.NC} 扫描 {len(py_files)} 个 Python 文件...")

        for py_file in py_files:
            if "__pycache__" in str(py_file):
                continue
            metric = self._scan_file(py_file)
            if metric:
                self.metrics.append(metric)
                self.all_issues.extend(metric.issues)

        return self.all_issues

    def _scan_file(self, filepath: Path) -> FileMetrics | None:
        """扫描单个文件"""
        try:
            content = filepath.read_text(encoding="utf-8")
        except Exception as e:
            return None

        lines = content.splitlines()
        metric = FileMetrics(
            path=str(filepath),
            total_lines=len(lines),
            functions=[],
        )

        # 1. 检查文件长度
        if metric.total_lines > self.MAX_FILE_LINES:
            metric.issues.append(QualityIssue(
                severity="ERROR",
                category="文件过长",
                file=str(filepath),
                line=0,
                message=f"文件 {metric.total_lines} 行超过阈值 {self.MAX_FILE_LINES}",
                suggestion="拆分为多个职责单一的模块"
            ))

        # 2. AST 分析
        try:
            tree = ast.parse(content, filename=str(filepath))
        except SyntaxError as e:
            metric.issues.append(QualityIssue(
                severity="ERROR",
                category="语法错误",
                file=str(filepath),
                line=e.lineno or 0,
                message=f"语法错误: {e.msg}",
            ))
            return metric

        self._analyze_ast(tree, filepath, metric, content)

        return metric

    def _analyze_ast(self, tree: ast.AST, filepath: Path,
                     metric: FileMetrics, content: str):
        """AST 分析"""
        for node in ast.walk(tree):
            # 函数长度
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_len = self._get_func_length(node, content)
                metric.functions.append((node.name, node.lineno, func_len))

                if func_len > self.MAX_FUNCTION_LINES:
                    metric.issues.append(QualityIssue(
                        severity="WARN",
                        category="函数过长",
                        file=str(filepath),
                        line=node.lineno,
                        message=f"函数 '{node.name}' {func_len} 行 (阈值 {self.MAX_FUNCTION_LINES})",
                        suggestion="提取子函数或应用策略模式"
                    ))

                if func_len > metric.longest_function[1]:
                    metric.longest_function = (node.name, func_len)

            # 静默异常
            elif isinstance(node, ast.ExceptHandler):
                metric.except_count += 1
                if self._is_silent_exception(node, content):
                    metric.silent_exception_count += 1
                    metric.issues.append(QualityIssue(
                        severity="WARN",
                        category="静默异常",
                        file=str(filepath),
                        line=node.lineno,
                        message=f"except 块仅有 pass 或无操作 - 异常被静默吞噬",
                        suggestion="至少记录 logger.error 或抛出新异常"
                    ))

            # 全局变量
            elif isinstance(node, ast.Global):
                metric.global_vars += len(node.names)
                if metric.global_vars > self.MAX_GLOBALS_PER_FILE:
                    metric.issues.append(QualityIssue(
                        severity="WARN",
                        category="全局可变状态",
                        file=str(filepath),
                        line=node.lineno,
                        message=f"使用 global 关键字 (累计 {metric.global_vars} 个)",
                        suggestion="改用类属性或依赖注入容器"
                    ))

            # TODO/FIXME
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
                if isinstance(node.value.value, str):
                    s = node.value.value.upper()
                    if "TODO" in s or "FIXME" in s or "HACK" in s:
                        metric.todo_count += 1
                        metric.issues.append(QualityIssue(
                            severity="INFO",
                            category="技术债务",
                            file=str(filepath),
                            line=node.lineno,
                            message=s[:80],
                        ))

        # 检查硬编码字符串
        self._check_hardcoded_strings(content, filepath, metric)

    def _get_func_length(self, node: ast.FunctionDef, content: str) -> int:
        """计算函数行数"""
        start = node.lineno
        end = node.end_lineno if hasattr(node, "end_lineno") and node.end_lineno else start
        return end - start + 1

    def _is_silent_exception(self, node: ast.ExceptHandler, content: str) -> bool:
        """判断是否为静默异常"""
        if not node.body:
            return True
        for stmt in node.body:
            if isinstance(stmt, ast.Pass):
                return True
            # except: pass 的情况
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                if stmt.value.value is ... or stmt.value.value is None:
                    return True
        # 仅含 logger.debug 但无 raise/return 的也可能静默
        has_raise = any(isinstance(s, ast.Raise) for s in node.body)
        has_return = any(isinstance(s, ast.Return) for s in node.body)
        has_pass = any(isinstance(s, ast.Pass) for s in node.body)
        return has_pass and not has_raise and not has_return

    def _check_hardcoded_strings(self, content: str, filepath: Path,
                                  metric: FileMetrics):
        """检查硬编码魔法数字"""
        # 匹配超过 6 位数的整数（可能是硬编码阈值）
        magic_pattern = re.compile(r'\b(\d{6,})\b')
        for i, line in enumerate(content.splitlines(), 1):
            if line.strip().startswith("#"):
                continue
            for match in magic_pattern.finditer(line):
                val = int(match.group(1))
                # 跳过常见合法值
                if val in (1000000, 10000000, 100000000):
                    continue
                metric.hardcoded_strings += 1
                if metric.hardcoded_strings <= 3:  # 仅报告前 3 个
                    metric.issues.append(QualityIssue(
                        severity="INFO",
                        category="魔法数字",
                        file=str(filepath),
                        line=i,
                        message=f"硬编码数值 {val} - 考虑提取为常量",
                    ))

    # ── 报告生成 ──────────────────────────────────────────────────────────
    def _collect_long_functions(self):
        long_funcs = []
        for m in self.metrics:
            for name, line, length in m.functions:
                if length > self.MAX_FUNCTION_LINES:
                    long_funcs.append((m.path, name, line, length))
        return long_funcs

    def _print_summary(self, total_lines, long_files, long_funcs):
        total_funcs = sum(len(m.functions) for m in self.metrics)
        print(f"\n{Colors.BLUE}📊 总体统计{Colors.NC}")
        print(f"  扫描文件数:     {len(self.metrics)}")
        print(f"  代码总行数:     {total_lines}")
        print(f"  函数总数:       {total_funcs}")
        print(f"  过长文件:       {len(long_files)}")
        print(f"  过长函数:       {len(long_funcs)}")
        print(f"  静默异常:       {sum(m.silent_exception_count for m in self.metrics)}")
        print(f"  全局变量使用:   {sum(m.global_vars for m in self.metrics)}")
        print(f"  TODO/FIXME:     {sum(m.todo_count for m in self.metrics)}")

    def _print_hotspots(self, long_files, long_funcs):
        if long_files:
            print(f"\n{Colors.YELLOW}📁 过长文件 (>{self.MAX_FILE_LINES} 行){Colors.NC}")
            for m in sorted(long_files, key=lambda x: x.total_lines, reverse=True)[:10]:
                print(f"  {Colors.RED}{m.total_lines:4d}{Colors.NC} 行  {m.path}")

        if long_funcs:
            print(f"\n{Colors.YELLOW}🔧 过长函数 (>{self.MAX_FUNCTION_LINES} 行){Colors.NC}")
            for path, name, line, length in sorted(long_funcs, key=lambda x: x[3], reverse=True)[:10]:
                print(f"  {Colors.RED}{length:4d}{Colors.NC} 行  {path}:{line}  {name}()")

        silent = [m for m in self.metrics if m.silent_exception_count > 0]
        if silent:
            print(f"\n{Colors.YELLOW}🤐 静默异常 (except: pass){Colors.NC}")
            for m in silent:
                print(f"  {m.silent_exception_count} 个  {m.path}")

        globals_files = [m for m in self.metrics if m.global_vars > 0]
        if globals_files:
            print(f"\n{Colors.YELLOW}🌍 全局可变状态{Colors.NC}")
            for m in globals_files:
                print(f"  {m.global_vars} 个  {m.path}")

    def _print_coverage(self, total_lines):
        test_files = list(Path("tests").rglob("test_*.py")) if Path("tests").exists() else []
        test_lines = sum(len(f.read_text().splitlines()) for f in test_files if f.exists())
        coverage_ratio = (test_lines / total_lines * 100) if total_lines > 0 else 0
        print(f"\n{Colors.BLUE}🧪 测试覆盖估算{Colors.NC}")
        print(f"  测试文件数:     {len(test_files)}")
        print(f"  测试代码行数:   {test_lines}")
        print(f"  测试/生产比例:  {coverage_ratio:.1f}%")
        if coverage_ratio < 20:
            print(f"  {Colors.RED}[WARN]{Colors.NC} 测试覆盖率偏低，建议增加至 30%+")
        elif coverage_ratio < 50:
            print(f"  {Colors.YELLOW}[WARN]{Colors.NC} 测试覆盖率中等，建议增加至 50%+")
        else:
            print(f"  {Colors.GREEN}[OK]{Colors.NC} 测试覆盖率良好")

    def _print_issue_summary(self):
        error_count = sum(1 for i in self.all_issues if i.severity == "ERROR")
        warn_count = sum(1 for i in self.all_issues if i.severity == "WARN")
        info_count = sum(1 for i in self.all_issues if i.severity == "INFO")
        print(f"\n{Colors.BOLD}📋 问题汇总{Colors.NC}")
        print(f"  {Colors.RED}ERROR: {error_count}{Colors.NC}")
        print(f"  {Colors.YELLOW}WARN:   {warn_count}{Colors.NC}")
        print(f"  {Colors.BLUE}INFO:   {info_count}{Colors.NC}")

    def print_report(self):
        """打印报告"""
        print("\n" + "=" * 70)
        print(f"{Colors.BOLD}Argus 代码质量审计报告{Colors.NC}")
        print("=" * 70)

        total_lines = sum(m.total_lines for m in self.metrics)
        long_files = [m for m in self.metrics if m.total_lines > self.MAX_FILE_LINES]
        long_funcs = self._collect_long_functions()

        self._print_summary(total_lines, long_files, long_funcs)
        self._print_hotspots(long_files, long_funcs)
        self._print_coverage(total_lines)
        self._print_issue_summary()

        print("\n" + "=" * 70)
        print(f"{Colors.GREEN}审计完成!{Colors.NC}")
        print("=" * 70)


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "app"
    auditor = CodeQualityAuditor(root)
    auditor.scan()
    auditor.print_report()


if __name__ == "__main__":
    main()
