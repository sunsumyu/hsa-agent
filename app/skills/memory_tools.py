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
def write_audit_note(category: str, content: str) -> str:
    """
    结构化审计便签写入器：记录当前取得的审计阶段性结论、线索、SQL 执行结果或下一步规划。
    
    参数说明：
    - category: 便签类别，例如 "risk_finding" (风险发现), "sql_evidence" (SQL证据), "todo" (待办事项), "blocker" (阻碍项)。
    - content: 记录的详细文字内容，请尽量客观、结构化、凝练。
    """
    try:
        # 确保 data 文件夹存在
        os.makedirs(os.path.dirname(_NOTE_PATH), exist_ok=True)
        
        # 检查是否是首次写入
        first_write = not os.path.exists(_NOTE_PATH)
        
        with open(_NOTE_PATH, "a", encoding="utf-8") as f:
            if first_write:
                f.write("# 🛡️ Argus 智能体审计外部便签簿 (Structured Audit Notes)\n")
                f.write("> 本便签簿由智能体在多轮 ReAct 交互中自主维护，用于跨上下文窗口重建时固化关键状态与证据。\n\n")
            
            import datetime
            time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"## 📌 [{category.upper()}] - {time_str}\n")
            f.write(f"{content.strip()}\n\n")
            f.write("---\n\n")
            
        logger.success(f"📓 [NoteTool] 成功将阶段性里程碑 [{category.upper()}] 写入外部便签簿")
        return f"✅ 成功写入外部便签簿 [{category.upper()}]！"
    except Exception as e:
        logger.error(f"📓 [NoteTool] 写入便签失败: {e}")
        return f"❌ 写入外部便签失败: {e}"

@tool
def read_all_audit_notes() -> str:
    """
    审计外部便签读取器：一键拉回完整的跨窗口审计线索与全部便签内容。
    【使用场景】：当上下文重置、窗口切换或进入总结渲染阶段时调用，一键拉回之前固化的全部核查线索。
    """
    try:
        if not os.path.exists(_NOTE_PATH):
            return "📓 外部便签簿目前为空。在取得阶段性结论或构建出核心 SQL 后，请先调用 write_audit_note 进行固化。"
        
        with open(_NOTE_PATH, "r", encoding="utf-8") as f:
            content = f.read()
            
        logger.info("📓 [NoteTool] 成功读取全部外部审计便签")
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
