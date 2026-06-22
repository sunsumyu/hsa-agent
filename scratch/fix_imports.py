"""
fix_imports.py
==============
一次性修复整个项目中所有过时/错误的 Python 导入路径。
修复规则完全对齐 app/__init__.py (DEPRECATED_MAPPINGS) 和
app/core/__init__.py (CORE_DEPRECATED_MAPPINGS) 中的权威定义。
"""
import os
import re
from pathlib import Path

# ──────────────────────────────────────────────────────────────────────────────
# 权威替换规则表（更具体的规则必须排在前面，防止部分匹配导致的误替换）
# 格式: (旧路径字符串, 新路径字符串)
# ──────────────────────────────────────────────────────────────────────────────
REPLACEMENTS = [
    # ── [优先级1] app.core.<module> 的子包偏置修复（最具体，必须最先处理）──
    ("app.core.schema_registry",    "app.core.registry.schema_registry"),
    ("app.core.skill_protocol",     "app.core.registry.skill_protocol"),
    ("app.core.prompt_registry",    "app.core.registry.prompt_registry"),
    ("app.core.rule_registry",      "app.core.registry.rule_registry"),
    ("app.core.context_builder",    "app.core.context.context_builder"),
    ("app.core.context_selector",   "app.core.context.context_selector"),
    ("app.core.funnel",             "app.core.context.funnel"),
    ("app.core.gates",              "app.core.context.gates"),
    # Note: app.core.message is ambiguous; only fix if it's flat (2-level after core)
    ("app.core.security",           "app.skills.security"),   # security 在 skills 下！

    # ── [优先级2] app.infra.<module> 中写错包的修复 ──
    ("app.infra.schema_registry",   "app.core.registry.schema_registry"),  # 被误放到 infra

    # ── [优先级3] app.<module> 扁平旧路径 → 正确的分层路径 ──
    # Infrastructure
    ("app.db_conn",                 "app.infra.db_conn"),
    ("app.neo4j_manager",           "app.infra.neo4j_manager"),
    ("app.model_manager",           "app.infra.model_manager"),
    ("app.usage_tracker",           "app.infra.usage_tracker"),
    ("app.redis_client",            "app.infra.redis_client"),
    ("app.endpoint_pool_manager",   "app.infra.endpoint_pool_manager"),
    ("app.quota_fetcher",           "app.infra.quota_fetcher"),

    # Skills
    ("app.security",                "app.skills.security"),
    ("app.audit_rules",             "app.skills.audit_rules"),
    ("app.anomaly_algorithms",      "app.skills.anomaly_algorithms"),
    ("app.conflict_detector",       "app.skills.conflict_detector"),
    ("app.fast_router",             "app.skills.fast_router"),
    ("app.protocol_filter",         "app.skills.protocol_filter"),
    ("app.sql_validator",           "app.skills.sql_validator"),
    ("app.schema_injector",         "app.skills.schema_injector"),
    ("app.schema_manager",          "app.skills.schema_manager"),
    ("app.semantic_layer",          "app.skills.semantic_layer"),
    ("app.federated_query",         "app.skills.federated_query"),
    ("app.sql_execution",           "app.skills.sql_execution"),
    ("app.medical_schema",          "app.skills.medical_schema"),

    # API
    ("app.perf_monitor",            "app.api.perf_monitor"),
    ("app.chat_stream",             "app.api.chat_stream"),
    ("app.monitor_server",          "app.api.monitor_server"),
    ("app.monitor_stream",          "app.api.monitor_stream"),

    # Core Orchestration
    ("app.agent_graph",             "app.core.agent_graph"),
    ("app.observability",           "app.core.observability"),
    ("app.prompts",                 "app.core.prompts"),
    ("app.schemas",                 "app.core.schemas"),
    ("app.structured_tracer",       "app.core.structured_tracer"),
    ("app.booster",                 "app.core.booster"),
    ("app.logging_config",          "app.core.logging_config"),

    # Agents
    ("app.agent",                   "app.agents.agent"),
    ("app.coder_agent",             "app.agents.coder_agent"),
    ("app.consolidator_agent",      "app.agents.consolidator_agent"),
    ("app.expert_bridge",           "app.agents.expert_bridge"),
    ("app.planner_agent",           "app.agents.planner_agent"),
    ("app.reflection_agent",        "app.agents.reflection_agent"),

    # Memory
    ("app.experience",              "app.memory.experience"),
    ("app.history",                 "app.memory.history"),
    ("app.compressor",              "app.memory.compressor"),
    ("app.entity_extractor",        "app.memory.entity_extractor"),
    ("app.message_sanitizer",       "app.memory.message_sanitizer"),
    ("app.semantic_memory",         "app.memory.semantic_memory"),

    # Reporting
    ("app.report_renderer",         "app.reporting.report_renderer"),
    ("app.rich_reporter",           "app.reporting.rich_reporter"),
    ("app.llm_judge",               "app.reporting.llm_judge"),
]

# ──────────────────────────────────────────────────────────────────────────────
# 扫描目录配置
# ──────────────────────────────────────────────────────────────────────────────
SCAN_DIRS = [
    "app",
    "scratch",
    "scripts",
    "tests",
]

# 永远不修改的文件（黑名单）
SKIP_FILES = {
    "app/__init__.py",          # 这就是权威映射字典本身
    "app/core/__init__.py",     # core 的兼容层本身
    "scratch/fix_imports.py",   # 本脚本自身
}


def fix_file(filepath: Path, root: Path) -> tuple[int, list[str]]:
    """修复单个文件中的所有过时导入，返回 (修改行数, 变更日志)"""
    rel = str(filepath.relative_to(root)).replace("\\", "/")
    if rel in SKIP_FILES:
        return 0, []

    try:
        original = filepath.read_text(encoding="utf-8")
    except Exception:
        return 0, []

    content = original
    changes = []

    for old, new in REPLACEMENTS:
        # 匹配完整的模块路径字符串（不能是更长的路径的前缀）
        # 使用 \b 单词边界 + 负向前瞻确保不误伤更长的包路径
        pattern = re.compile(
            r'(?<!["\w.])' + re.escape(old) + r'(?![.\w])'
        )
        if pattern.search(content):
            new_content = pattern.sub(new, content)
            if new_content != content:
                count = len(pattern.findall(content))
                changes.append(f"  [{count}x] {old!r} → {new!r}")
                content = new_content

    if content != original:
        filepath.write_text(content, encoding="utf-8")
        return len(changes), changes

    return 0, []


def main():
    root = Path(__file__).parent.parent  # hsa-agent/
    print(f"[SCAN] Root: {root}")
    print("=" * 72)

    total_files_changed = 0
    total_changes = 0

    for scan_dir in SCAN_DIRS:
        scan_path = root / scan_dir
        if not scan_path.exists():
            continue
        for py_file in sorted(scan_path.rglob("*.py")):
            n, log = fix_file(py_file, root)
            if n > 0:
                total_files_changed += 1
                total_changes += n
                rel = str(py_file.relative_to(root)).replace("\\", "/")
                print(f"\n[FIXED] {rel}")
                for line in log:
                    print(line)

    print("\n" + "=" * 72)
    print(f"📊 修复完成！共修改 {total_files_changed} 个文件，应用 {total_changes} 处导入路径修正。")

if __name__ == "__main__":
    main()
