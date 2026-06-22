"""
scripts/ingest_expert_regulations.py
====================================
[V4.6] 专家知识库全量入库脚本
支持自动扫描、MD5 去重、多模态解析与标题感知索引。
"""

import os
import asyncio
import hashlib
import json
from datetime import datetime
from loguru import logger
from app.core.rag.tool import rag_tool
from app.core.memory.rag_utils import approx_token_len

# 配置
KB_ROOT = "data/knowledge_base"
STATE_FILE = "data/ingest_state.json"
SUPPORTED_EXTS = {'.pdf', '.docx', '.doc', '.xlsx', '.md', '.txt', '.csv', '.html', '.htm'}

def get_file_hash(path: str) -> str:
    """计算文件 MD5 指纹"""
    hasher = hashlib.md5()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_state(state: dict):
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2, ensure_ascii=False)

async def main():
    logger.info("🎬 [Ingest] 开始专家知识库全量同步流程...")
    state = load_state()
    
    if not os.path.exists(KB_ROOT):
        os.makedirs(KB_ROOT)
        logger.warning(f"目录 {KB_ROOT} 为空，请将法律法规文件放入该目录。")
        return

    stats = {"processed": 0, "skipped": 0, "failed": 0, "total_tokens": 0}

    # 递归扫描
    for root, dirs, files in os.walk(KB_ROOT):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext not in SUPPORTED_EXTS: continue
            
            full_path = os.path.join(root, file)
            f_hash = get_file_hash(full_path)
            
            # 1. 指纹校验 (去重)
            if state.get(full_path) == f_hash:
                # logger.debug(f"⏭️  [Skip] 文件未变化: {file}")
                stats["skipped"] += 1
                continue
            
            logger.info(f"🚚 [Process] 正在索引文档: {file} ...")
            
            # 2. 调用 RAGTool 执行结构化索引
            try:
                # 确定知识类型 (根据子目录名)
                kb_type = os.path.basename(root) if root != KB_ROOT else "general"
                
                res = await rag_tool.add_document(full_path, importance=0.9)
                
                if res["status"] == "SUCCESS":
                    state[full_path] = f_hash
                    stats["processed"] += 1
                    stats["total_tokens"] += res.get("approx_tokens", 0)
                    # 及时保存状态，支持断点续传
                    save_state(state)
                else:
                    logger.error(f"❌ [Failed] {file}: {res['message']}")
                    stats["failed"] += 1
                    
            except Exception as e:
                logger.error(f"💥 [Error] 处理 {file} 时崩溃: {e}")
                stats["failed"] += 1

    # 汇总报告
    logger.success(f"""
    ========================================
    🎉 知识库同步完成！
    - 成功索引: {stats['processed']} 个文件
    - 跳过重复: {stats['skipped']} 个文件
    - 失败数量: {stats['failed']} 个文件
    - 预计算力消耗: {stats['total_tokens']} Tokens
    - 状态记录: {STATE_FILE}
    ========================================
    """)

if __name__ == "__main__":
    asyncio.run(main())
