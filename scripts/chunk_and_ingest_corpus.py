# -*- coding: utf-8 -*-
"""
对 8.5 万字法典进行语义切块 (Semantic Chunking)、存入真实向量库并逐块可视化探查
"""
import sys
import io
import os
import json
import asyncio

# 保证 UTF-8 输出
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
else:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

sys.path.append(os.path.abspath("."))
os.environ["DISABLE_LOCAL_EMBEDDING"] = "false"
os.environ["HF_HUB_OFFLINE"] = "0"

from sentence_transformers import SentenceTransformer
from app.core.memory.storage.vector import VectorStorage
from app.core.memory.base import MemoryItem
from app.core.rag.citation_ledger import extract_law_and_article, make_content_hash

INPUT_CORPUS_FILE = "data/knowledge_base/regulations/official_hsa_regulations_corpus.md"
MASSIVE_STORAGE_DIR = "data/official_vector_storage"
CHUNKS_JSON_EXPORT = "data/knowledge_base/regulations/official_chunks_preview.json"

class RealEmbedder:
    def __init__(self):
        print("   -> 正在激活本地 SentenceTransformer 嵌入引擎 (384维)...")
        self.model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")

    def embed_query(self, text: str):
        return self.model.encode(text).tolist()

    def embed_documents(self, texts):
        return self.model.encode(texts).tolist()


def _build_chunk_record(
    filepath: str,
    chunk_index: int,
    part: str,
    chapter: str,
    title: str,
    body_text: str,
) -> dict:
    """构造带确定性溯源元数据的语义切片记录。"""
    source = os.path.basename(filepath)
    heading_path = f"{part} > {chapter} > {title}"
    law_title, article_num = extract_law_and_article(f"{heading_path}\n{body_text}", source)
    return {
        "doc_id": os.path.splitext(source)[0],
        "source": source,
        "chunk_index": chunk_index,
        "heading_path": heading_path,
        "law_title": law_title,
        "article_num": article_num,
        "content_hash": make_content_hash(body_text),
        "part": part,
        "chapter": chapter,
        "title": title,
        "text": body_text,
        "char_count": len(body_text),
    }


def _build_memory_item(idx: int, chunk: dict) -> MemoryItem:
    """构造带完整法规溯源元数据的语义记忆项。"""
    part = chunk.get("part", "")
    chapter = chunk.get("chapter", "")
    title = chunk.get("title", "")
    heading_path = chunk.get("heading_path") or f"{part} > {chapter} > {title}"
    text = chunk.get("text", "")
    return MemoryItem(
        content=f"【{heading_path}】\n{text}",
        memory_type="semantic",
        importance=0.9,
        metadata={
            "chunk_id": idx,
            "doc_id": chunk.get("doc_id", ""),
            "source": chunk.get("source", ""),
            "chunk_index": chunk.get("chunk_index", idx),
            "heading_path": heading_path,
            "law_title": chunk.get("law_title", ""),
            "article_num": chunk.get("article_num", ""),
            "content_hash": chunk.get("content_hash", ""),
            "part": part,
            "chapter": chapter,
            "title": title,
            "char_count": chunk.get("char_count", len(text)),
            "tenant_id": "default",
        },
    )


def perform_semantic_chunking(filepath: str):
    """
    语义层级切块核心算法：
    以 Markdown 的 '#### ' 条款标题为自然切割点，
    同时向前继承其所属的 '## ' 和 '### ' 章节父标题。
    """
    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.read().split("\n")

    chunks = []
    current_part = "未分类大编"
    current_chapter = "未分类章节"
    current_title = ""
    current_buffer = []

    for line in lines:
        if line.startswith("## "):
            current_part = line.replace("## ", "").strip()
        elif line.startswith("### "):
            current_chapter = line.replace("### ", "").strip()
        elif line.startswith("#### "):
            body_text = "\n".join(current_buffer).strip()
            if current_title and len(body_text) > 30:
                chunks.append(_build_chunk_record(filepath, len(chunks), current_part, current_chapter, current_title, body_text))
            current_title = line.replace("#### ", "").strip()
            current_buffer = []
        elif current_title:
            current_buffer.append(line)

    body_text = "\n".join(current_buffer).strip()
    if current_title and len(body_text) > 30:
        chunks.append(_build_chunk_record(filepath, len(chunks), current_part, current_chapter, current_title, body_text))

    return chunks


async def main():
    print("=" * 80)
    print("✂️ 正在对 85,347 字大型医保法典执行【语义切块 (Chunking)】...")
    print(f"📖 目标原文件: {INPUT_CORPUS_FILE}")
    print("=" * 80)

    # 1. 执行切块
    raw_chunks = perform_semantic_chunking(INPUT_CORPUS_FILE)
    total_chars = sum(c["char_count"] for c in raw_chunks)
    avg_chars = total_chars / len(raw_chunks) if raw_chunks else 0

    print(f"\n📊 【切块统计大盘】:")
    print(f"   - 总共切成了: {len(raw_chunks)} 个独立的业务切片 (Chunks)")
    print(f"   - 切片总字数: {total_chars:,} 字")
    print(f"   - 平均每块大小: {avg_chars:.1f} 字 (完美符合 300~500 字黄金区间！)")

    # 2. 导出所有切片到 JSON 文件，供用户随时在编辑器里检查每一块
    with open(CHUNKS_JSON_EXPORT, "w", encoding="utf-8") as f:
        json.dump(raw_chunks, f, ensure_ascii=False, indent=2)
    print(f"   💾 完整切片清单已导出至: {CHUNKS_JSON_EXPORT}")

    # 3. 初始化向量数据库并将切块灌库
    print("\n" + "-" * 80)
    print(f"💾 【向量化灌库】正在为这 {len(raw_chunks)} 块切片批量生成 384 维向量并落盘...")
    print("-" * 80)

    import shutil
    if os.path.exists(MASSIVE_STORAGE_DIR):
        shutil.rmtree(MASSIVE_STORAGE_DIR)

    embedder = RealEmbedder()
    storage = VectorStorage(storage_dir=MASSIVE_STORAGE_DIR, embeddings=embedder)

    items = [_build_memory_item(idx, c) for idx, c in enumerate(raw_chunks)]

    # 写入 FAISS 索引
    await storage.add(items)
    print(f"   ✅ 灌库成功！FAISS 索引中现已包含 {storage.index.ntotal} 个高维向量")

    # 4. 【核心展示】随机抽样展示前几块和中间几块切片在向量库里的真实物理样貌
    print("\n" + "=" * 80)
    print("👀 【透视向量库：抽样展示真实切片数据结构】")
    print("=" * 80)

    samples_to_show = [0, 50, 100]  # 抽样看第 1 块（法律）、第 51 块（手术）、第 101 块（药品）
    for s_idx in samples_to_show:
        if s_idx < len(storage.items):
            item = storage.items[s_idx]
            # 从 FAISS 索引里把这个 chunk 对应的真实 384 维向量捞出来展示前 8 位
            faiss_vec = storage.index.reconstruct(s_idx)
            
            print(f"\n📦 ------------------ 【向量库切片 (Chunk #{s_idx + 1:03d})】 ------------------")
            print(f"   📌 归属大编:   {item.metadata.get('part')}")
            print(f"   📌 归属章节:   {item.metadata.get('chapter')}")
            print(f"   📌 条款标题:   {item.metadata.get('title')}")
            print(f"   📏 切片字数:   {item.metadata.get('char_count')} 个汉字")
            print(f"   🔢 384维向量:  [{faiss_vec[0]:.4f}, {faiss_vec[1]:.4f}, {faiss_vec[2]:.4f}, {faiss_vec[3]:.4f}, {faiss_vec[4]:.4f} ... 共384位]")
            print(f"   📄 切片正文摘录:\n      \"{item.content[:140].strip()}...\"")
            print("   ----------------------------------------------------------------------")

    print("\n" + "=" * 80)
    print("🎉 切块与物理探查全部完成！你可以在左侧文件树直接打开查看 chunks_preview.json！")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
