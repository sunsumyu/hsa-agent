"""
app/core/context/funnel_intent_rewriter.py
============================================
[Matt Pocock Deep Module] 语义漏斗第一层：意图重写与 JSON Payload 抽取器
专职负责：
1. 从 LLM 输出中安全解析 JSON，剥离 <think> 思考链与 Markdown 语法糖
2. 构造意图重写 Prompt 并调用 LLM
3. 发生异常时的防御性降级实体提取
"""

import json
import re
from typing import Dict, Any, Optional
from loguru import logger

from app.core.llm_provider import llm_provider


def extract_json_payload(text: str) -> Optional[Dict[str, Any]]:
    """从 LLM 输出中安全解析 JSON，剥离 <think> 思考链与 Markdown 语法糖"""
    if not text:
        return None
    # 1. 剥离 <think>...</think>
    clean_text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    
    # 2. 尝试从 markdown 代码块提取
    code_block = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', clean_text, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1).strip())
        except Exception:
            pass

    # 3. 尝试提取完整大括号块
    brace_match = re.search(r'\{.*\}', clean_text, re.DOTALL)
    if brace_match:
        try:
            return json.loads(brace_match.group(0).strip())
        except Exception:
            pass

    # 4. 尝试直接解析
    try:
        return json.loads(clean_text)
    except Exception:
        return None


class FunnelIntentRewriter:
    """意图重写深模块"""

    async def rewrite_intent(self, query: str, config: Any = None) -> Dict[str, Any]:
        """【漏斗第一层】Query Rewrite：将业务口语转换为结构化审计意图实体"""
        logger.info(f"🔮 [Funnel] 正在重写审计意图: '{query}'")
        
        prompt = [
            ("system", """你是一位精通医疗保险审计与数据科学的专家。
请将用户口语化的核查诉求翻译为结构化的审计分析参数。你的输出必须是 STRICT JSON 格式，包含以下字段：
1. rewritten_question: 专业规范的审计学术语描述。⚠️ 特别注意：必须精确保留原始问题中的特定数量、频次或金额阈值描述（例如将“五六个病号”保留并翻译为“不少于5名患者”或“5至6名患者”，千万不要模糊化为“多名患者”），以防止审计阈值在后续阶段丢失。
2. hospital_levels: 识别到的机构级别描述（如 "一级医院", "社区诊所", "民营医院" 等），无则为空数组。
3. disease_keywords: 提取到的疾病核心词或症状核心词（如 "感冒", "发烧", "透析", "高血压" 等），无则为空数组。
4. financial_metric: 可能的结算字段类别，只能在 ["medfee_sumamt", "fund_pay_sumamt", "det_item_fee_sumamt", "none"] 中选择。
5. statistical_strategy: 针对异常金额或频次的统计核查策略，必须在 ["DYNAMIC_QUANTILE_95", "DYNAMIC_QUANTILE_99", "AVERAGE_OUTLIER", "HARD_THRESHOLD", "NONE"] 中选择一种。

请务必只返回 JSON，禁止返回任何 markdown 标记或解释性文字。"""),
            ("human", f"用户核查提问：{query}")
        ]
        
        try:
            response = await llm_provider.chat(
                role="planner_light",
                messages=prompt,
                config=config,
                max_tokens=800
            )
            content = str(response.content).strip()
            result = extract_json_payload(content)
            if not result:
                raise ValueError(f"无法从模型输出中解析合法 JSON: {content[:200]}")
            logger.info(f"✅ [Funnel] 意图重写成功: {result}")
            return result
        except Exception as e:
            logger.error(f"❌ [Funnel] 意图重写失败: {e}，启用降级实体提取")
            # 降级兜底提取
            return {
                "rewritten_question": query,
                "hospital_levels": ["社区诊所", "乡镇卫生院"] if "诊所" in query or "卫生院" in query else [],
                "disease_keywords": ["感冒"] if "感冒" in query or "发烧" in query else ["透析"] if "透析" in query else [],
                "financial_metric": "medfee_sumamt",
                "statistical_strategy": "DYNAMIC_QUANTILE_95" if "大额" in query or "大价钱" in query or "千" in query else "NONE"
            }


funnel_intent_rewriter = FunnelIntentRewriter()
