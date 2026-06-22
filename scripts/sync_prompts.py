import os
import sys
from dotenv import load_dotenv
from langfuse import Langfuse
from loguru import logger

# 物理环境载入 (V40.0)
sys.path.append(os.getcwd())
load_dotenv()

from app.prompts import (
    PLANNER_PROMPT, 
    CODER_PROMPT, 
    ANALYST_PROMPT, 
    REPORTER_PROMPT, 
    AUDITOR_PROMPT
)

def sync_all_prompts():
    """将本地 Prompt 资产全量同步至 Langfuse 云端"""
    pk = os.getenv("LANGFUSE_PUBLIC_KEY")
    sk = os.getenv("LANGFUSE_SECRET_KEY")
    host = os.getenv("LANGFUSE_HOST", "https://us.cloud.langfuse.com")
    
    if not pk or not sk:
        logger.error("未找到 Langfuse 凭证，请检查 .env 文件！")
        return

    langfuse = Langfuse(public_key=pk, secret_key=sk, host=host)
    
    # 待同步清单 (映射名 -> 本地对象)
    prompt_map = {
        "planner-audit-v1": PLANNER_PROMPT,
        "coder-sql-expert-v1": CODER_PROMPT,
        "analyst-numeric-v1": ANALYST_PROMPT,
        "reporter-formal-v1": REPORTER_PROMPT,
        "auditor-chief-v1": AUDITOR_PROMPT
    }

    logger.info(">>> 正在启动物理同步...")
    
    for cloud_name, local_prompt in prompt_map.items():
        try:
            # 提取 System Message 作为 Prompt 内容
            # 注意：Langfuse 管理的是 Template 文本，不含变量插槽定义
            content = ""
            for msg in local_prompt.messages:
                if hasattr(msg, "prompt") and hasattr(msg.prompt, "template"):
                    content = msg.prompt.template
                    break
            
            if not content:
                logger.warning(f"跳过 {cloud_name}: 未能提取到有效的模板文本")
                continue

            # 物理创建/更新至 Langfuse
            langfuse.create_prompt(
                name=cloud_name,
                prompt=content,
                labels=["production"]
            )
            logger.info(f"✅ 同步成功: {cloud_name}")
            
        except Exception as e:
            logger.error(f"❌ 同步失败 {cloud_name}: {e}")

    logger.info(">>> 物理同步任务已完成！请刷新 Langfuse Prompts 页面查看结果。")

if __name__ == "__main__":
    sync_all_prompts()
