import os
import sys
import json
from typing import List
from loguru import logger

# 确保 app 目录在路径中
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.tools import _split_paragraphs_with_headings, _chunk_paragraphs, get_embeddings
from langchain_community.vectorstores import FAISS

try:
    from markitdown import MarkItDown
    MARKITDOWN_AVAILABLE = True
except ImportError:
    MARKITDOWN_AVAILABLE = False
    logger.warning("未检测到 markitdown 库，PDF/Word 转换功能将受限。请运行: pip install markitdown")

class KnowledgeIngestor:
    """[V47.0] 工业级知识摄取工具：支持多格式解析与结构化分块"""
    
    def __init__(self, index_path: str = "data/faiss_index"):
        self.index_path = index_path
        self.embeddings = get_embeddings()
        self.md_converter = MarkItDown() if MARKITDOWN_AVAILABLE else None

    def convert_to_markdown(self, file_path: str) -> str:
        """将任意文件转换为 Markdown"""
        if not MARKITDOWN_AVAILABLE:
            if file_path.endswith(".md") or file_path.endswith(".txt"):
                with open(file_path, 'r', encoding='utf-8') as f:
                    return f.read()
            return ""
        
        try:
            logger.info(f"正在解析文件: {file_path}")
            result = self.md_converter.convert(file_path)
            return result.text_content
        except Exception as e:
            logger.error(f"解析失败 {file_path}: {e}")
            return ""

    def ingest_directory(self, docs_dir: str):
        """批量摄取目录下的所有文档"""
        if not os.path.exists(docs_dir):
            logger.error(f"目录不存在: {docs_dir}")
            return

        all_chunks = []
        for root, _, files in os.walk(docs_dir):
            for file in files:
                file_path = os.path.join(root, file)
                # 支持的格式
                if file.endswith(('.pdf', '.docx', '.pptx', '.xlsx', '.md', '.txt')):
                    md_content = self.convert_to_markdown(file_path)
                    if not md_content:
                        continue
                    
                    # 使用架构师级分块逻辑
                    paras = _split_paragraphs_with_headings(md_content)
                    chunks = _chunk_paragraphs(paras, chunk_tokens=600, overlap_tokens=100)
                    
                    for c in chunks:
                        # 注入源文件元数据
                        c_content = f"来源: {file}\n{c['content']}"
                        all_chunks.append(c_content)
        
        if not all_chunks:
            logger.warning("未找到有效知识片段。")
            return

        logger.info(f"已生成 {len(all_chunks)} 个结构化知识片段，正在构建向量库...")
        
        # 构建并持久化
        vector_store = FAISS.from_texts(all_chunks, self.embeddings)
        vector_store.save_local(self.index_path)
        logger.success(f">>> [认知摄取完成] 知识库已持久化至: {self.index_path}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="HSA 医保审计知识摄取工具")
    parser.add_argument("--dir", type=str, required=True, help="文档所在目录")
    parser.add_argument("--out", type=str, default="data/faiss_index", help="向量库保存路径")
    
    args = parser.parse_args()
    
    ingestor = KnowledgeIngestor(index_path=args.out)
    ingestor.ingest_directory(args.dir)
