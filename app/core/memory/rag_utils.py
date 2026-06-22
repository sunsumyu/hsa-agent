"""
app/core/memory/rag_utils.py
===========================
[V4.6] 企业级 RAG 核心算法库
支持标题路径感知分割与 CJK Token 精准估算
"""

import re
import os
from typing import List, Dict, Any, Optional

def split_paragraphs_with_headings(text: str) -> List[Dict[str, Any]]:
    """
    [V4.6] 标题层次感知分割
    利用 Markdown 的 # 层级结构保持语义完整性。
    """
    lines = text.splitlines()
    heading_stack: List[str] = []
    paragraphs: List[Dict[str, Any]] = []
    buf: List[str] = []
    char_pos = 0
    
    def flush_buf(end_pos: int):
        if not buf: return
        content = "\n".join(buf).strip()
        if not content: return
        paragraphs.append({
            "content": content,
            "heading_path": " > ".join(heading_stack) if heading_stack else "ROOT",
            "start": max(0, end_pos - len(content)),
            "end": end_pos,
        })
    
    for ln in lines:
        if ln.strip().startswith("#"):
            flush_buf(char_pos)
            # 计算标题级别
            level = len(ln) - len(ln.lstrip('#'))
            title = ln.lstrip('#').strip()
            
            # 更新标题栈
            if level <= len(heading_stack):
                heading_stack = heading_stack[:level-1]
            heading_stack.append(title)
            
            char_pos += len(ln) + 1
            buf = [] # 标题本身不计入内容段落，仅作为路径
            continue
        
        if ln.strip() == "":
            flush_buf(char_pos)
            buf = []
        else:
            buf.append(ln)
        char_pos += len(ln) + 1
    
    flush_buf(char_pos)
    return paragraphs if paragraphs else [{"content": text, "heading_path": "ROOT", "start": 0, "end": len(text)}]

def chunk_paragraphs(paragraphs: List[Dict[str, Any]], chunk_tokens: int = 500, overlap_tokens: int = 50) -> List[Dict[str, Any]]:
    """
    [V4.6] 智能 Token 分块
    在保持标题路径的前提下，执行带重叠的物理分块。
    """
    chunks: List[Dict[str, Any]] = []
    cur_batch: List[Dict[str, Any]] = []
    cur_tokens = 0
    
    for p in paragraphs:
        p_tokens = approx_token_len(p["content"])
        
        if cur_tokens + p_tokens <= chunk_tokens or not cur_batch:
            cur_batch.append(p)
            cur_tokens += p_tokens
        else:
            # 封装当前块
            combined_content = "\n\n".join(x["content"] for x in cur_batch)
            last_heading = next((x["heading_path"] for x in reversed(cur_batch) if x.get("heading_path")), "ROOT")
            
            chunks.append({
                "content": combined_content,
                "heading_path": last_heading,
                "tokens": cur_tokens
            })
            
            # 处理重叠 (保持最后 N 个词)
            if overlap_tokens > 0:
                kept = []
                kept_tokens = 0
                for x in reversed(cur_batch):
                    t = approx_token_len(x["content"])
                    if kept_tokens + t > overlap_tokens: break
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
            "tokens": cur_tokens
        })
        
    return chunks

def preprocess_markdown_for_embedding(text: str) -> str:
    """
    [V4.6] 嵌入预处理：清理 Markdown 噪点以提升向量质量
    """
    if not text: return ""
    # 移除图片链接 ![alt](url)
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    # 移除常规链接 [text](url) -> text
    text = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', text)
    # 移除 HTML 标签
    text = re.sub(r'<.*?>', '', text)
    # 移除过多的星号/粗体符号
    text = text.replace('***', '').replace('**', '').replace('__', '')
    # 归一化空白符
    text = re.sub(r'\s+', ' ', text).strip()
    return text

async def generate_mqe_queries(query: str, n: int = 3) -> List[str]:
    """
    [V4.6] MQE：生成多样化的审计查询扩展
    """
    from app.core.llm_provider import llm_provider
    try:
        prompt = [
            ("system", "你是一位医保审计专家。请针对用户的原始查询，生成 {n} 个语义等价但表述不同的专业审计查询。要求：使用中文，简短专业，涵盖可能的业务别名。"),
            ("human", f"原始查询：{query}")
        ]
        # 使用轻量级模型以节省算力
        response = await llm_provider.chat(role="planner_light", messages=prompt)
        text = str(response.content)
        lines = [re.sub(r'^\d+\.\s*', '', ln.strip("- \t")) for ln in text.splitlines()]
        return [ln for ln in lines if ln][:n]
    except Exception as e:
        logger.warning(f"MQE 扩展失败: {e}")
        return []

async def generate_hyde_document(query: str) -> Optional[str]:
    """
    [V4.6] HyDE：生成假设性审计证据段落
    """
    from app.core.llm_provider import llm_provider
    try:
        prompt = [
            ("system", "根据用户提出的审计问题，先写一段可能的违规事实描述或政策条文原文（不要包含分析过程），用于向量检索。"),
            ("human", f"问题：{query}\n请直接输出一段客观、包含关键术语的专业段落。")
        ]
        response = await llm_provider.chat(role="coder_light", messages=prompt)
        return str(response.content)
    except Exception as e:
        logger.warning(f"HyDE 生成失败: {e}")
        return None

def approx_token_len(text: str) -> int:
    """
    [V4.6] CJK-Aware Token 估算器
    针对中英混合文本进行物理校准 (汉字1.5, 英文0.4)
    """
    if not text: return 0
    zh_count = len([c for c in text if '\u4e00' <= c <= '\u9fff'])
    en_count = len(text) - zh_count
    return int(zh_count * 1.5 + en_count * 0.4)
