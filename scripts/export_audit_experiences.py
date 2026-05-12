import os
import sys
from loguru import logger

# 确保环境正确
sys.path.append(os.getcwd())
# HF_HOME: use .env or system default

from app.semantic_memory import cognitive_memory_manager
from langchain_community.vectorstores import FAISS

def export_experiences():
    logger.info("🔍 正在从本地语义记忆库导出审计经验...")
    
    storage_path = "data/memory_v2/semantic"
    if not os.path.exists(os.path.join(storage_path, "index.faiss")):
        logger.warning("⚠️ 未发现本地审计经验库，可能尚未沉淀任何经验。")
        return

    try:
        # 初始化组件以确保加载模型
        cognitive_memory_manager._init_components()
        embeddings = cognitive_memory_manager._local_engine
        
        # 加载向量库
        vector_store = FAISS.load_local(storage_path, embeddings, allow_dangerous_deserialization=True)
        
        # 提取所有文档
        # 注意：FAISS 本身不直接支持 'list all'，但我们可以通过检索一个空字符串或通用词来获取
        # 或者直接访问 vector_store.docstore._dict (如果是 InMemoryDocstore)
        all_docs = list(vector_store.docstore._dict.values())
        
        export_content = [
            "# 📚 HSA 医疗审计经验库 (Cognitive Export)",
            f"**导出时间**: {os.popen('date /t').read().strip()}",
            f"**总案例数**: {len(all_docs)}",
            "\n---\n"
        ]
        
        for idx, doc in enumerate(all_docs):
            topic = doc.metadata.get("topic", "未命名主题")
            export_content.append(f"### 案例 {idx+1}: {topic}")
            export_content.append(f"**审计逻辑/SQL模板**:\n```sql\n{doc.page_content}\n```")
            export_content.append(f"**元数据**: `{doc.metadata}`")
            export_content.append("\n---\n")
            
        export_file = "data/audit_experience_export.md"
        with open(export_file, "w", encoding="utf-8") as f:
            f.write("\n".join(export_content))
            
        logger.success(f"✅ 审计经验导出成功！文件路径: {export_file}")
        print(f"\n--- EXPORT START ---\n" + "\n".join(export_content) + "\n--- EXPORT END ---")

    except Exception as e:
        logger.error(f"导出失败: {e}")

if __name__ == "__main__":
    export_experiences()
