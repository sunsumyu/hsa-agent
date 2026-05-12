"""
app/protocol_filter.py
======================
[V4.6.0] 协议拦截器 + 数据脱敏，从 main.py 提取为独立模块。

- ProtocolInterceptor: 流式状态机，吞噬 [[[...]]] / ⟦...⟧ 标签，防止内部协议泄露给前端
- sanitize(): 物理级数据脱敏，屏蔽表名、字段名、SQL 关键字等技术底噪
"""

import re
from typing import List
from loguru import logger


class ProtocolInterceptor:
    """流式状态机拦截器：逐字符处理流式片段，吞噬内部协议标签。"""

    # 允许泄露给前端的安全标签白名单
    ALLOWED_TAGS = ("STATUS", "AUDIT_REPORT_V2", "END_REPORT")

    def __init__(self, max_buffer_size: int = 1024 * 1024 * 2):
        self.buffer = ""
        self.is_inside_tag = False
        self.max_buffer_size = max_buffer_size  # [V90.6] 2MB 熔断阈值（审计报告可能很大）

    def process_chunk(self, chunk: str) -> List[str]:
        """
        处理流式片段，返回需要 yield 给前端的文本片段。
        所有 ⟦...⟧ 或 [[[...]]] 结构均由拦截器物理吞噬。
        """
        if not chunk:
            return []

        results = []
        for char in chunk:
            self.buffer += char

            # 状态切换检测：进入标签
            if not self.is_inside_tag and self.buffer.endswith("[[["):
                tag_start_idx = len(self.buffer) - 3
                text_before = self.buffer[:tag_start_idx]
                if text_before:
                    results.append(text_before)

                self.buffer = "[[["
                self.is_inside_tag = True
                continue

            # 状态切换检测：退出标签
            if self.is_inside_tag and self.buffer.endswith("]]]"):
                # [V15.5] 只有特定标签允许泄露给前端，其余全部内部消化
                if any(tag in self.buffer for tag in self.ALLOWED_TAGS):
                    results.append(self.buffer)

                self.buffer = ""
                self.is_inside_tag = False
                continue

            # 熔断保护：防止模型产生幻觉导致 buffer 过大
            if len(self.buffer) > self.max_buffer_size:
                # [V90.6] 智能清罐：如果是合法标签的超长内容，释放给前端而不是丢弃
                if self.is_inside_tag and any(tag in self.buffer[:512] for tag in self.ALLOWED_TAGS):
                    logger.warning(f"⚠️ [协议软熔断] 合法标签内容过大 ({len(self.buffer)} 字节)，强制释放并续流。")
                    results.append(self.buffer + "]]]")  # 主动闭合标签
                else:
                    logger.error(f"!!! [协议熔断] 拦截器缓冲区溢出 ({len(self.buffer)} 字节)，可能发生逻辑死循环。强制清罐。")
                    results.append("\n[系统警告]: 核心审计引擎推演异常过载，已进行物理熔断。")
                self.buffer = ""
                self.is_inside_tag = False

        # 如果当前不在标签内，且 buffer 中积压了文本，则安全输出
        if not self.is_inside_tag and self.buffer:
            if not self.buffer.startswith("["):
                results.append(self.buffer)
                self.buffer = ""
            elif len(self.buffer) > 3 and not self.buffer.startswith("[[["):
                results.append(self.buffer)
                self.buffer = ""

        return results

    def flush(self) -> str:
        """最后时刻强制清出 buffer 中的剩余普通文本"""
        if not self.is_inside_tag:
            res = self.buffer
            self.buffer = ""
            return res
        return ""


# ──────────────────────────────────────────────────────────────
# 脱敏正则模式 (编译一次，复用)
# ──────────────────────────────────────────────────────────────

_LEAK_PATTERNS = [
    # [V15.5] 豁免名单：允许 AUDIT_REPORT_V2 和 END_REPORT 通过拦截器
    r'\[\[\[(?!AUDIT_REPORT_V2|END_REPORT|STATUS|MOVE|LOGIC|SCHEMA|SQL|RESOURCE|THOUGHT|CHECKPOINT|VERSION).*?\]\]\]',
    r'⟦.*?⟧',
    r'<thought>.*?</thought>',
    r'<thinking>.*?</thinking>',
    # [V16.2] UI 标签白名单保护：严禁过滤以下核心渲染组件标签
    r'<(?!StatGrid|ViolationCard|Stat|/StatGrid|/ViolationCard|/Stat)[a-zA-Z0-9_\s="/]+>',
    r'\[thought\].*?\[/thought\]',
    r'\[[a-zA-Z0-9_]+\] Result:.*',  # 拦截 "[execute_sql] Result:..."
    r'<\[.*?\][rtw]?>',  # 拦截类似图像中出现的标签格式 <[维度]r>
    r'Wait, (I should|let me).*?',  # 拦截模型"OS自言自语"
    r'I will now.*?',  # 拦截模型工具调用意图
    r'Tables involved:.*?',
    r'\[FastRoute\][^\n]*',  # [V90.1] 内部路由决策标记不应泄露到最终报告
    r'\[CONT(?:INUE)?\][^\n]*',  # 内部流转指令
    r'\[GraphRoute\][^\n]*',  # 图路由内部标记
]

_MASK_PATTERNS = [
    r'\bfqz_[a-zA-Z0-9_]+\b',
    r'\bt_audit_[a-zA-Z0-9_]+\b',
    r'\bmedins_[a-zA-Z0-9_]+\b',
    r'\b[a-z]{2,}_[a-z_]{2,}\b',  # 下划线代码字段
    r'\bpsn_(no|id|name)\b',
    r'\bsetl_id\b',
]

_SQL_KEYWORD_PATTERN = r'\b(SELECT|FROM|WHERE|INSERT|UPDATE|DELETE|JOIN|GROUP BY|ORDER BY|LIMIT|OFFSET)\b'

# 预编译正则
_COMPILED_LEAK = [re.compile(p, re.DOTALL | re.IGNORECASE) for p in _LEAK_PATTERNS]
_COMPILED_MASK = [re.compile(p, re.IGNORECASE) for p in _MASK_PATTERNS]
_COMPILED_SQL = re.compile(_SQL_KEYWORD_PATTERN, re.IGNORECASE)


def sanitize(text: str) -> str:
    """[V15.5 终极强固脱敏锁] 物理级数据脱敏与技术底噪拦截"""
    if not text:
        return ""

    # [V15.5] 容灾：自动将模型误生成的 || 转换为标准换行
    text = text.replace("||", "\n")

    # 1. 拦截所有类似工具调用产生的中间文本格式与特定回声
    for p in _COMPILED_LEAK:
        text = p.sub('', text)

    # 2. 深度数据脱敏：屏蔽物理表名与技术标识符
    for p in _COMPILED_MASK:
        text = p.sub('【业务稽核维度】', text)

    # 3. 拦截 SQL 关键字
    text = _COMPILED_SQL.sub('[审计逻辑]', text)

    # [V15.5] 严禁使用全局 strip()，否则会抹除 markdown 的换行符流
    return text
