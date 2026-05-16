import asyncio
import os
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import re

# 将项目根目录添加到路径
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.memory import memory_hub
from app.core.context import tenant_context

async def ingest_regulations():
    file_path = r"e:\chain\fqz-hsa-frontend\data\knowledge_base\regulations\medical_insurance_regulation_2021.md"
    if not os.path.exists(file_path):
        print(f"❌ 文件未找到: {file_path}")
        return

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 按条目分割 (匹配 "第X条")
    articles = re.split(r'\n(第[一二三四五六七八九十百]+条)', content)
    
    # 重新组合标题和内容
    processed_articles = []
    for i in range(1, len(articles), 2):
        title = articles[i]
        body = articles[i+1].strip() if i+1 < len(articles) else ""
        full_text = f"{title} {body}"
        processed_articles.append(full_text)

    print(f"📦 发现 {len(processed_articles)} 条监管条款，准备导入...")

    # 设置全局租户上下文 (模拟系统管理员导入全局知识)
    tenant_context.set("SYSTEM_GLOBAL")

    for article in processed_articles:
        # 提取关键信息用于元数据
        article_num = re.search(r'第([一二三四五六七八九十百]+)条', article)
        metadata = {
            "source": "medical_insurance_regulation_2021",
            "category": "regulation",
            "article_num": article_num.group(1) if article_num else "unknown"
        }
        
        await memory_hub.add_memory(
            content=article,
            memory_type="semantic",
            importance=1.0,  # 监管文件重要性最高
            **metadata
        )

    print(f"✅ 成功导入 {len(processed_articles)} 条监管条款至语义记忆库。")
    
    # 输出统计信息
    stats = memory_hub.get_stats()
    print(f"📊 当前记忆库状态: {stats}")

if __name__ == "__main__":
    asyncio.run(ingest_regulations())
