"""
app/skills/audit_note_store.py
==============================
外部结构化审计便签存储与时间衰减引擎（Matt Pocock Deep Module）

职责：
- 线程安全的外部便签持久化与追加写入 (RLock)
- TTL 有效期计算与跨窗口时间衰减标记状态机
- 便签清理、分段切分与信封封装
- 为 context_builder, direct_turn_dispatcher, coreference_rewriter, report_synthesizer
  提供收敛统一的磁盘 I/O 门面，彻底杜绝裸写 open("data/audit_notes.md")
"""

from __future__ import annotations

import os
import re
import datetime
import threading
from typing import List, Optional, Tuple
from loguru import logger

DEFAULT_NOTE_PATH = "data/audit_notes.md"


class AuditNoteStore:
    """线程安全的审计便签存储仓储深模块"""

    def __init__(self, default_path: str = DEFAULT_NOTE_PATH):
        self.default_path = default_path
        self._lock = threading.RLock()

    def _resolve_path(self, file_path: Optional[str] = None) -> str:
        """解析便签路径：显式路径 > ContextVar 会话/租户隔离路径 > 全局默认路径"""
        if file_path:
            return file_path
        try:
            from app.core.context import tenant_context, trace_context
            tenant_id = tenant_context.get()
            trace_id = trace_context.get()
        except Exception:
            tenant_id = None
            trace_id = None

        parts = []
        if tenant_id:
            parts.append(re.sub(r"[^a-zA-Z0-9_-]", "_", str(tenant_id)))
        if trace_id:
            parts.append(re.sub(r"[^a-zA-Z0-9_-]", "_", str(trace_id)))

        if not parts:
            return self.default_path

        base_dir = os.path.dirname(self.default_path) or "data"
        return os.path.join(base_dir, "notes", f"{'_'.join(parts)}.md")

    @staticmethod
    def _is_section_expired(sec: str, current_time: datetime.datetime) -> bool:
        """判断单个便签段落是否已超过 TTL 或 30 天默认有效期"""
        expire_match = re.search(r"过期日期:\s*(\d{4}-\d{2}-\d{2})", sec)
        if expire_match:
            try:
                expire_date = datetime.datetime.strptime(expire_match.group(1), "%Y-%m-%d")
                return current_time > expire_date
            except Exception:
                return False

        date_match = re.search(r"\[(\w+)\]\s*-\s*(\d{4}-\d{2}-\d{2})", sec)
        if date_match:
            try:
                note_date = datetime.datetime.strptime(date_match.group(2), "%Y-%m-%d")
                return (current_time - note_date).days > 30
            except Exception:
                return False
        return False

    @staticmethod
    def _extract_category(sec: str) -> str:
        """从便签段落标题中提取类别名称"""
        match = re.search(r"##\s*📌\s*\[([A-Za-z0-9_]+)\]", sec)
        return match.group(1).upper() if match else ""

    @staticmethod
    def _query_overlap_score(sec: str, query: str) -> float:
        """计算便签与查询的中英文混合词/双字片段重叠度"""
        if not query or not query.strip():
            return 0.0
        q_clean = query.lower().strip()
        s_clean = sec.lower()
        q_tokens = set(q_clean.split())
        # 对无空格的中文连续串补充 2-gram，避免中文查询重叠度恒为 0
        cjk_chars = "".join(ch for ch in q_clean if "\u4e00" <= ch <= "\u9fff")
        for i in range(len(cjk_chars) - 1):
            q_tokens.add(cjk_chars[i : i + 2])
        if not q_tokens:
            return 0.0
        hits = sum(1 for tok in q_tokens if tok in s_clean)
        return hits / len(q_tokens)

    def write_note(
        self,
        category: str,
        content: str,
        ttl_days: int = 30,
        file_path: Optional[str] = None,
    ) -> bool:
        """将阶段性审计结论或证据线索写入外部便签文件"""
        target_path = self._resolve_path(file_path)
        with self._lock:
            try:
                dir_name = os.path.dirname(target_path)
                if dir_name:
                    os.makedirs(dir_name, exist_ok=True)

                first_write = not os.path.exists(target_path)

                with open(target_path, "a", encoding="utf-8") as f:
                    if first_write:
                        f.write("# 🛡️ Argus 智能体审计外部便签簿 (Structured Audit Notes)\n")
                        f.write(
                            "> 本便签簿由智能体在多轮 ReAct 交互中自主维护，用于跨上下文窗口重建时固化关键状态与证据。\n"
                        )
                        f.write(">\n")
                        f.write(
                            "> ⚠️ **时间衰减策略**：便签超过 30 天自动降权 50%，超过 90 天自动降权 80%，历史便签仅供参考，不作为当前查询的强制模板。\n\n"
                        )
                        f.write("---\n\n")

                    now_dt = datetime.datetime.now()
                    time_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")
                    expire_date = (now_dt + datetime.timedelta(days=ttl_days)).strftime("%Y-%m-%d")
                    cat_upper = category.upper()
                    f.write(f"## 📌 [{cat_upper}] - {time_str}\n")
                    f.write(f"> TTL: {ttl_days}天 | 过期日期: {expire_date}\n\n")
                    f.write(f"{content.strip()}\n\n")
                    f.write("---\n\n")

                logger.success(f"📓 [NoteStore] 成功写入外部便签簿 [{category.upper()}] (TTL: {ttl_days}天)")
                return True
            except Exception as e:
                logger.error(f"📓 [NoteStore] 写入便签失败: {e}")
                return False

    def append_entry(self, entry: str, file_path: Optional[str] = None) -> bool:
        """直接向便签簿追加一条独立段落（带分隔符与目录保护）"""
        target_path = self._resolve_path(file_path)
        with self._lock:
            try:
                dir_name = os.path.dirname(target_path)
                if dir_name:
                    os.makedirs(dir_name, exist_ok=True)
                with open(target_path, "a", encoding="utf-8") as f:
                    f.write(f"\n---\n{entry.strip()}\n")
                return True
            except Exception as e:
                logger.warning(f"Failed to append note to {target_path}: {e}")
                return False

    def read_recent_notes(self, limit: int = 3, file_path: Optional[str] = None) -> List[str]:
        """按 --- 分隔块提取最近 N 条非空便签段落"""
        target_path = self._resolve_path(file_path)
        with self._lock:
            if not os.path.exists(target_path):
                return []
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if not content:
                    return []
                note_parts = [p.strip() for p in content.split("---") if p.strip()]
                return note_parts[-limit:] if len(note_parts) > limit else note_parts
            except Exception as e:
                logger.warning(f"读取便签失败: {e}")
                return []

    def read_relevant_notes(
        self,
        query: str = "",
        limit: int = 3,
        prioritize_categories: Tuple[str, ...] = ("BLOCKER", "RISK_FINDING"),
        file_path: Optional[str] = None,
        now: Optional[datetime.datetime] = None,
    ) -> List[str]:
        """按高优类别 (BLOCKER/RISK_FINDING) + 查询相关性 + 新近度精选未过期便签"""
        if limit <= 0:
            return []
        target_path = self._resolve_path(file_path)
        with self._lock:
            if not os.path.exists(target_path):
                return []
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                if not content:
                    return []

                current_time = now or datetime.datetime.now()
                priority_set = {c.upper() for c in prioritize_categories}
                raw_parts = [p.strip() for p in content.split("---") if p.strip()]

                # 过滤掉纯文件头说明段与已过期便签
                candidates = []
                for idx, part in enumerate(raw_parts):
                    if part.startswith("# 🛡️ Argus 智能体审计外部便签簿"):
                        continue
                    if self._is_section_expired(part, current_time):
                        continue
                    cat = self._extract_category(part)
                    is_prio = 1 if cat in priority_set else 0
                    overlap = self._query_overlap_score(part, query)
                    # 排序键：高优类别 > 查询重叠度 > 越新越靠前 (idx 越大)
                    candidates.append(((is_prio, overlap, idx), part))

                candidates.sort(key=lambda item: item[0], reverse=True)
                return [part for _, part in candidates[:limit]]
            except Exception as e:
                logger.warning(f"精选相关便签失败: {e}")
                return []

    def read_lines(self, file_path: Optional[str] = None) -> List[str]:
        """读取便签簿中所有有效文本行（排除空行与 --- 分隔线）"""
        target_path = self._resolve_path(file_path)
        with self._lock:
            if not os.path.exists(target_path):
                return []
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    return [
                        line.strip()
                        for line in f.readlines()
                        if line.strip() and not line.startswith("---")
                    ]
            except Exception:
                return []

    def read_raw_text(self, file_path: Optional[str] = None) -> str:
        """直接读取便签簿原始内容"""
        target_path = self._resolve_path(file_path)
        with self._lock:
            if not os.path.exists(target_path):
                return ""
            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                return ""

    def read_notes_with_decay(
        self,
        file_path: Optional[str] = None,
        now: Optional[datetime.datetime] = None,
    ) -> str:
        """读取外部便签内容，并应用基于 TTL 或历史日期的衰减标记"""
        target_path = self._resolve_path(file_path)
        with self._lock:
            if not os.path.exists(target_path):
                return ""

            try:
                with open(target_path, "r", encoding="utf-8") as f:
                    raw_text = f.read()

                current_time = now or datetime.datetime.now()
                raw_sections = raw_text.split("\n---")
                processed_sections = []

                for sec in raw_sections:
                    if not sec.strip():
                        processed_sections.append(sec)
                        continue

                    is_expired = False
                    expire_match = re.search(r"过期日期:\s*(\d{4}-\d{2}-\d{2})", sec)
                    if expire_match:
                        try:
                            expire_date = datetime.datetime.strptime(expire_match.group(1), "%Y-%m-%d")
                            is_expired = current_time > expire_date
                        except Exception:
                            is_expired = False
                    else:
                        date_match = re.search(r"\[(\w+)\]\s*-\s*(\d{4}-\d{2}-\d{2})", sec)
                        if date_match:
                            try:
                                note_date = datetime.datetime.strptime(date_match.group(2), "%Y-%m-%d")
                                age_days = (current_time - note_date).days
                                is_expired = age_days > 30
                            except Exception:
                                is_expired = False

                    if is_expired and "已过期" not in sec:
                        sec_lines = sec.split("\n")
                        new_lines = []
                        inserted = False
                        for line in sec_lines:
                            new_lines.append(line)
                            if line.startswith("## 📌") and not inserted:
                                new_lines.append(
                                    "> ⚠️ **[⏰已过期·仅供参考]** 该便签已超过有效期或已衰减，请结合最新数据库物理事实重新核准。\n"
                                )
                                inserted = True
                        processed_sections.append("\n".join(new_lines))
                    else:
                        processed_sections.append(sec)

                return "\n---".join(processed_sections)
            except Exception as e:
                logger.error(f"📓 [NoteStore] 读取便签失败: {e}")
                return ""

    def clear_notes(self, file_path: Optional[str] = None) -> bool:
        """物理清空外部便签簿"""
        target_path = self._resolve_path(file_path)
        with self._lock:
            try:
                if os.path.exists(target_path):
                    os.remove(target_path)
                logger.info(f"📓 [NoteStore] 已清空便签簿: {target_path}")
                return True
            except Exception as e:
                logger.error(f"📓 [NoteStore] 清空便签失败: {e}")
                return False

    def format_notes_envelope(self, content: str) -> str:
        """为便签内容包裹标准 XML 隔离标签"""
        if not content.strip():
            return ""
        return f"<external_audit_notes>\n{content.strip()}\n</external_audit_notes>"


# 全局单例与向后兼容导出
audit_note_store = AuditNoteStore()

write_note = audit_note_store.write_note
append_entry = audit_note_store.append_entry
read_recent_notes = audit_note_store.read_recent_notes
read_relevant_notes = audit_note_store.read_relevant_notes
read_lines = audit_note_store.read_lines
read_raw_text = audit_note_store.read_raw_text
read_notes_with_decay = audit_note_store.read_notes_with_decay
clear_notes = audit_note_store.clear_notes
format_notes_envelope = audit_note_store.format_notes_envelope
