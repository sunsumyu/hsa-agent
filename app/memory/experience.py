import json
import os
from typing import List, Optional, Dict, Any
from loguru import logger
from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS

# 使用相对导入避免循环依赖
def get_embeddings():
    from app.tools import get_embeddings
    return get_embeddings()

INDEX_PATH = "data/experience/faiss_index"
POOL_FILE = "data/experience/pool.json"

class ExperienceManager:
    """[V47.0] 语义经验库：存储审计 SQL 的成功经验，支持向量检索"""
    
    def __init__(self):
        os.makedirs(os.path.dirname(POOL_FILE), exist_ok=True)
        self._vector_store = None

    def _load_pool(self) -> List[dict]:
        if not os.path.exists(POOL_FILE):
            return []
        try:
            with open(POOL_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[经验库] 加载失败: {e}")
            return []

    def _get_vector_store(self):
        if self._vector_store is None:
            if os.path.exists(INDEX_PATH):
                self._vector_store = FAISS.load_local(
                    INDEX_PATH, get_embeddings(), allow_dangerous_deserialization=True
                )
            else:
                # 初始化空库
                pool = self._load_pool()
                if pool:
                    docs = [Document(page_content=e["intent"], metadata=e) for e in pool]
                    self._vector_store = FAISS.from_documents(docs, get_embeddings())
                    self._vector_store.save_local(INDEX_PATH)
                else:
                    return None
        return self._vector_store

    def save_audit_experience(self, tasks: List[str], sql: str):
        """[固化] 将成功的审计意图与 SQL 沉淀为长期语义经验"""
        task_str = " ".join(tasks)
        if not task_str or not sql: return
        
        pool = self._load_pool()
        # 避免完全重复的意图
        if any(e["intent"] == task_str for e in pool): return

        entry = {
            "intent": task_str,
            "golden_sql": sql,
            "ts": os.path.getmtime(POOL_FILE) if os.path.exists(POOL_FILE) else 0
        }
        pool.append(entry)
        
        # 保持池大小
        if len(pool) > 200: pool = pool[-200:]
        
        try:
            with open(POOL_FILE, 'w', encoding='utf-8') as f:
                json.dump(pool, f, ensure_ascii=False, indent=2)
            
            # 更新向量库
            doc = Document(page_content=task_str, metadata=entry)
            vs = self._get_vector_store()
            if vs:
                vs.add_documents([doc])
            else:
                vs = FAISS.from_documents([doc], get_embeddings())
            vs.save_local(INDEX_PATH)
            self._vector_store = vs
            
            logger.success(f">>> [经验固化] 已将审计意图转化为长程语义知识: {task_str[:40]}...")
        except Exception as e:
            logger.error(f"[经验库] 固化失败: {e}")

    def get_relevant_experience(self, tasks: List[str], k: int = 1) -> str:
        """[检索] 语义级找回历史成功案例 (Golden Examples)"""
        task_str = " ".join(tasks)
        vs = self._get_vector_store()
        if not vs or not task_str: return ""
        
        try:
            results = vs.similarity_search(task_str, k=k)
            if not results: return ""
            
            formatted = []
            for res in results:
                meta = res.metadata
                formatted.append(
                    f"### 参考历史成功案例 (Semantic Match):\n"
                    f"意图: {meta['intent']}\n"
                    f"SQL: \n```sql\n{meta['golden_sql']}\n```"
                )
            return "\n\n".join(formatted)
        except Exception as e:
            logger.error(f"[经验库] 检索失败: {e}")
            return ""

experience_manager = ExperienceManager()
