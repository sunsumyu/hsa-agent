"""
app/core/utils.py
=================
[V163.0] 鲁棒性解析器 (Robust Parser)

为工业级 Agent 提供高鲁棒性的参数解析与容错自愈能力。
"""

import re
import json
from typing import Dict, Any, Union
from loguru import logger

def smart_parse_tool_params(raw_input: Any) -> Dict[str, Any]:
    """
    智能参数解析：将 LLM 产生的各种“不规范”输出转换为标准字典。
    支持 JSON, Markdown-JSON, 以及 key=value 格式。
    """
    if isinstance(raw_input, dict):
        return raw_input
    
    text = str(raw_input).strip()
    
    # 1. 尝试标准 JSON 解析
    try:
        # 处理可能被 Markdown 代码块包裹的情况
        json_str = text
        if "```json" in text:
            match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
            if match: json_str = match.group(1)
        elif "```" in text:
            match = re.search(r"```\s*(.*?)\s*```", text, re.DOTALL)
            if match: json_str = match.group(1)
            
        return json.loads(json_str)
    except Exception:
        pass
    
    # 2. 尝试 Key-Value 格式解析
    # 格式: sql=SELECT... , db_type=clickhouse
    # 注意：这里使用更简单的分割逻辑，防止复杂的 SQL 语句破坏正则
    if "=" in text and ("," in text or len(text) < 500):
        try:
            pairs = {}
            for part in text.split(","):
                if "=" in part:
                    k, v = part.split("=", 1)
                    pairs[k.strip()] = v.strip()
            if pairs:
                logger.warning(f"🔧 [RobustParser] 检测到 KV 格式参数，正在执行降级解析")
                return pairs
        except:
            pass
        
    # 3. 兜底逻辑：针对 SQL 执行器的特殊处理
    if "SELECT" in text.upper() and "FROM" in text.upper():
        return {"sql": text}
        
    return {"input": text, "raw": text}
