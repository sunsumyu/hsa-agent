"""
app/core/memory/markdown_chunker.py
===================================
Markdown 标题感知分割、Token 校准与分块引擎（Deep Module）

职责：
- 标题层级状态栈维护与语义段落切分
- CJK 混合文本 Token 精准加权估算 (汉字1.5, 英文0.4)
- 滑动重叠窗口 Token 智能分块
- 向量嵌入前 Markdown 噪声清理
"""

from __future__ import annotations

import re
from typing import List, Dict, Any


def approx_token_len(text: str) -> int:
    """
    CJK-Aware Token 估算器。
    针对中英混合文本进行物理校准 (汉字1.5, 英文0.4)。
    """
    if not text:
        return 0
    zh_count = len([c for c in text if "\u4e00" <= c <= "\u9fff"])
    en_count = len(text) - zh_count
    return int(zh_count * 1.5 + en_count * 0.4)


def preprocess_markdown_for_embedding(text: str) -> str:
    """
    嵌入预处理：清理 Markdown 噪点以提升向量检索质量。
    """
    if not text:
        return ""
    # 移除图片链接 ![alt](url)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    # 移除常规链接 [text](url) -> text
    text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
    # 移除 HTML 标签
    text = re.sub(r"<.*?>", "", text)
    # 移除过多的星号/粗体符号
    text = text.replace("***", "").replace("**", "").replace("__", "")
    # 归一化空白符
    text = re.sub(r"\s+", " ", text).strip()
    return text


def split_paragraphs_with_headings(text: str) -> List[Dict[str, Any]]:
    """
    标题层次感知分割：
    利用 Markdown 的 # 层级结构保持语义上下文路径完整性。
    """
    if not text:
        return []

    lines = text.splitlines()
    heading_stack: List[str] = []
    paragraphs: List[Dict[str, Any]] = []
    buf: List[str] = []
    char_pos = 0

    def flush_buf(end_pos: int):
        if not buf:
            return
        content = "\n".join(buf).strip()
        if not content:
            return
        paragraphs.append({
            "content": content,
            "heading_path": " > ".join(heading_stack) if heading_stack else "ROOT",
            "start": max(0, end_pos - len(content)),
            "end": end_pos,
        })

    for ln in lines:
        if ln.strip().startswith("#"):
            flush_buf(char_pos)
            level = len(ln) - len(ln.lstrip("#"))
            title = ln.lstrip("#").strip()

            if level <= len(heading_stack):
                heading_stack = heading_stack[: level - 1]
            heading_stack.append(title)

            char_pos += len(ln) + 1
            buf = []
            continue

        if ln.strip() == "":
            flush_buf(char_pos)
            buf = []
        else:
            buf.append(ln)
        char_pos += len(ln) + 1

    flush_buf(char_pos)
    return paragraphs if paragraphs else [{"content": text, "heading_path": "ROOT", "start": 0, "end": len(text)}]


def chunk_paragraphs(
    paragraphs: List[Dict[str, Any]],
    chunk_tokens: int = 500,
    overlap_tokens: int = 50,
) -> List[Dict[str, Any]]:
    """
    智能 Token 分块：
    在保持标题路径的前提下，执行带重叠窗口的物理分块。
    """
    chunks: List[Dict[str, Any]] = []
    cur_batch: List[Dict[str, Any]] = []
    cur_tokens = 0

    for p in paragraphs:
        p_tokens = approx_token_len(p.get("content", ""))

        if cur_tokens + p_tokens <= chunk_tokens or not cur_batch:
            cur_batch.append(p)
            cur_tokens += p_tokens
        else:
            combined_content = "\n\n".join(x["content"] for x in cur_batch)
            last_heading = next(
                (x["heading_path"] for x in reversed(cur_batch) if x.get("heading_path")),
                "ROOT"
            )

            chunks.append({
                "content": combined_content,
                "heading_path": last_heading,
                "tokens": cur_tokens,
            })

            # 处理重叠
            if overlap_tokens > 0:
                kept = []
                kept_tokens = 0
                for x in reversed(cur_batch):
                    t = approx_token_len(x.get("content", ""))
                    if kept_tokens + t > overlap_tokens:
                        break
                    kept.append(x)
                    kept_tokens += t
                cur_batch = list(reversed(kept))
                cur_tokens = kept_tokens
            else:
                cur_batch = [p]
                cur_tokens = p_tokens

    if cur_batch:
        chunks.append({
            "content": "\n\n".join(x["content"] for x in cur_batch),
            "heading_path": cur_batch[-1].get("heading_path", "ROOT"),
            "tokens": cur_tokens,
        })

    return chunks
