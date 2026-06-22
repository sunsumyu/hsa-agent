"""
app/skills/memory_tools.py
==========================
[Phase 3.2] Memory management, structured notes, and embedding tools.

Extracted from tools.py. These @tool functions let the Agent persist
findings, manage working/long-term memory, and access embedding services.
"""

import os
from loguru import logger
from langchain_core.tools import tool

from app.core.memory import memory_hub


@tool
async def manage_memory(
    action: str, 
    content: str = "", 
    query: str = "", 
    key: str = "",
    memory_type: str = "working",
    importance: float = 0.5,
    **kwargs
) -> str:
    """
    [V180.0] 智能记忆管理工具。支持以下操作：
    - add: 添加记忆 (需要 content, memory_type, importance, [key])
    - search: 搜索历史记忆 (需要 query, memory_type)
    - summary: 获取当前记忆中枢状态摘要
    - forget: 执行遗忘清理 (策略可选: importance_based, time_based)
    - consolidate: 强制将工作记忆整合至长期库 (需要 key)
    """
    logger.info(f"🧠 [TOOL] 执行记忆管理操作: {action}")
    
    try:
        if action == "add":
            if key: kwargs["key"] = key
            return await memory_hub.add_memory(content, memory_type, importance, **kwargs)
        elif action == "search":
            results = await memory_hub.query(query, limit=kwargs.get("limit", 5))
            if not results: return f"🔍 未找到与 '{query}' 相关的记忆。"
            return "\n".join([f"- [{r.memory_type}] {str(r.content)[:200]}" for r in results])
        elif action == "summary":
            return memory_hub.get_summary()
        elif action == "forget":
            count = await memory_hub.forget_memories(
                strategy=kwargs.get("strategy", "importance_based"),
                threshold=kwargs.get("threshold", 0.2)
            )
            return f"🧹 已遗忘 {count} 条低价值记忆。"
        elif action == "consolidate":
            if not key: return "❌ consolidate 操作需要指定 key 参数。"
            await memory_hub.consolidate(key, importance_threshold=importance)
            return f"✅ 记忆项 {key} 已成功固化。"
        else:
            return f"❌ 不支持的操作: {action}"
    except Exception as e:
        return f"❌ 记忆操作失败: {str(e)}"

# ──────────────────────────────────────────────────────────
# 📓 结构化外部便签工具 (NoteTool) [V200.0]
# ──────────────────────────────────────────────────────────

# 默认便签文件路径
_NOTE_PATH = "data/audit_notes.md"

@tool
def write_audit_note(category: str, content: str, ttl_days: int = 30) -> str:
    """
    结构化审计便签写入器：记录当前取得的审计阶段性结论、线索、SQL 执行结果或下一步规划。

    参数说明：
    - category: 便签类别，例如 "risk_finding" (风险发现), "sql_evidence" (SQL证据), "todo" (待办事项), "blocker" (阻碍项)。
    - content: 记录的详细文字内容，请尽量客观、结构化、凝练。
    - ttl_days: 便签有效期（天数），默认 30 天。超过有效期的便签会被降权，不再作为强制模板。
    """
    try:
        # 确保 data 文件夹存在
        os.makedirs(os.path.dirname(_NOTE_PATH), exist_ok=True)

        # 检查是否是首次写入
        first_write = not os.path.exists(_NOTE_PATH)

        with open(_NOTE_PATH, "a", encoding="utf-8") as f:
            if first_write:
                f.write("# 🛡️ Argus 智能体审计外部便签簿 (Structured Audit Notes)\n")
                f.write("> 本便签簿由智能体在多轮 ReAct 交互中自主维护，用于跨上下文窗口重建时固化关键状态与证据。\n")
                f.write(">\n")
                f.write("> ⚠️ **时间衰减策略**：便签超过 30 天自动降权 50%，超过 90 天自动降权 80%，历史便签仅供参考，不作为当前查询的强制模板。\n\n")
                f.write("---\n\n")

            import datetime
            time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            expire_date = (datetime.datetime.now() + datetime.timedelta(days=ttl_days)).strftime("%Y-%m-%d")
            f.write(f"## 📌 [{category.upper()}] - {time_str}\n")
            f.write(f"> TTL: {ttl_days}天 | 过期日期: {expire_date}\n\n")
            f.write(f"{content.strip()}\n\n")
            f.write("---\n\n")

        logger.success(f"📓 [NoteTool] 成功将阶段性里程碑 [{category.upper()}] 写入外部便签簿 (TTL: {ttl_days}天)")
        return f"✅ 成功写入外部便签簿 [{category.upper()}]！有效期 {ttl_days} 天，过期后自动降权。"
    except Exception as e:
        logger.error(f"📓 [NoteTool] 写入便签失败: {e}")
        return f"❌ 写入外部便签失败: {e}"

@tool
def read_all_audit_notes() -> str:
    """
    审计外部便签读取器：一键拉回完整的跨窗口审计线索与全部便签内容。
    【使用场景】：当上下文重置、窗口切换或进入总结渲染阶段时调用，一键拉回之前固化的全部核查线索。
    【时间衰减】：超过 TTL 的便签会被标记为 [已过期·仅供参考]，不会作为当前查询的强制模板。
    """
    try:
        if not os.path.exists(_NOTE_PATH):
            return "📓 外部便签簿目前为空。在取得阶段性结论或构建出核心 SQL 后，请先调用 write_audit_note 进行固化。"

        with open(_NOTE_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        # 时间衰减：标记过期便签
        import datetime
        import re
        now = datetime.datetime.now()
        lines = content.split("\n")
        processed_lines = []
        current_section_expired = False

        for line in lines:
            # 检查过期日期标记
            expire_match = re.search(r"过期日期:\s*(\d{4}-\d{2}-\d{2})", line)
            if expire_match:
                try:
                    expire_date = datetime.datetime.strptime(expire_match.group(1), "%Y-%m-%d")
                    if now > expire_date:
                        current_section_expired = True
                    else:
                        current_section_expired = False
                except Exception:
                    current_section_expired = False

            # 检查旧格式的日期标记（无 TTL 的历史便签）
            date_match = re.search(r"\[(\w+)\]\s*-\s*(\d{4}-\d{2}-\d{2})", line)
            if date_match and "过期日期" not in line:
                try:
                    note_date = datetime.datetime.strptime(date_match.group(2), "%Y-%m-%d")
                    days_old = (now - note_date).days
                    if days_old > 90:
                        current_section_expired = True
                    elif days_old > 30:
                        current_section_expired = True  # 30天以上也标记
                    else:
                        current_section_expired = False
                except Exception:
                    current_section_expired = False

            # 在标题行添加过期标记
            if current_section_expired and line.startswith("## 📌"):
                line = line.replace("## 📌", "## 📌 [⏰已过期·仅供参考]")

            # 分隔线重置状态
            if line.strip() == "---":
                current_section_expired = False

            processed_lines.append(line)

        content = "\n".join(processed_lines)
        logger.info("📓 [NoteTool] 成功读取全部外部审计便签（已应用时间衰减）")
        return f"<external_audit_notes>\n{content.strip()}\n</external_audit_notes>"
    except Exception as e:
        logger.error(f"📓 [NoteTool] 读取便签失败: {e}")
        return f"❌ 读取外部便签失败: {e}"

@tool
def clear_audit_notes() -> str:
    """
    清空外部审计便签：当当前任务彻底结束或开启全新会话时，清空外部便签簿。
    """
    try:
        if os.path.exists(_NOTE_PATH):
            os.remove(_NOTE_PATH)
        logger.info("📓 [NoteTool] 外部便签簿已彻底清空重置")
        return "✅ 外部审计便签簿已成功清空重置！"
    except Exception as e:
        logger.error(f"📓 [NoteTool] 清空便签失败: {e}")
        return f"❌ 清空外部便签失败: {e}"

def get_embeddings():
    from app.core.memory.embedding import embedding_engine
