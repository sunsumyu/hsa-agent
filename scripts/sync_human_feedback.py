import os
import sys
import re
from loguru import logger

# 环境初始化
sys.path.append(os.getcwd())
# HF_HOME: use .env or system default

from app.memory.semantic_memory import cognitive_memory_manager
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

def sync_human_feedback():
    logger.info("♻️ 正在启动人工纠偏同步程序...")
    
    export_file = "data/audit_experience_export.md"
    if not os.path.exists(export_file):
        logger.error("❌ 未找到导出文件，请先运行导出脚本。")
        return

    # 1. 解析 Markdown 中的经验项
    with open(export_file, "r", encoding="utf-8") as f:
        content = f.read()

    # 正则提取案例块
    cases = re.findall(r"### 案例 \d+: (.*?)\n\*\*审计逻辑/SQL模板\*\*:\n```sql\n(.*?)\n```\n\*\*元数据\*\*: `(.*?)`", content, re.DOTALL)
    
    if not cases:
        logger.warning("⚠️ 未能解析到任何有效的经验条目，请检查文件格式。")
        return

    new_documents = []
    for topic, sql_logic, metadata_str in cases:
        try:
            metadata = eval(metadata_str)  # 简单解析元数据字典
            doc = Document(page_content=sql_logic.strip(), metadata={"topic": topic.strip(), **metadata})
            new_documents.append(doc)
            logger.info(f"📍 准备同步经验: {topic}")
        except Exception as e:
            logger.error(f"解析条目出错: {e}")

    # 2. 重建/更新本地向量索引
    if new_documents:
        try:
            cognitive_memory_manager._init_components()
            embeddings = cognitive_memory_manager._local_engine
            
            # 为了保证纠偏的彻底性，我们采用“全量覆盖”模式：将人工确认过的 MD 作为唯一真理来源
            vector_store = FAISS.from_documents(new_documents, embeddings)
            vector_store.save_local("data/memory_v2/semantic")
            
            logger.success(f"✅ 人工纠偏同步完成！共同步 {len(new_documents)} 条专家经验。")
            logger.info("🚀 智能体现在已具备最新的专家逻辑。")
        except Exception as e:
            logger.error(f"同步至向量库失败: {e}")

if __name__ == "__main__":
    sync_human_feedback()
