from langchain_core.prompts import ChatPromptTemplate
from app.model_manager import model_manager
from loguru import logger

# 压缩专职指令：业务脱水与事实锚定 (V4.1.1)
COMPRESSOR_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """你是一个专业的内控审计专家。你的任务是优化当前的审计线索。
请将 Findings 压缩成精炼摘要，但必须遵守“业务数据豁免”原则。

[数据豁免原则 - 必须 100% 保留]
1. **具体名单**：任何涉及病患ID、医院名称、违规机构的列表。
2. **结算数据**：具体的金额（￥）、报销次数、就医频次。
3. **政策依据**：法律法规的具体名称。

[清理清单 - 必须删除]
1. 所有的 SQL 沙箱拦截报错、语法错误、字段不存在的报错过程。
2. 重复的数据库表结构定义。

[逻辑要求]
- **严禁过度概括**：如果发现了 3 个违规病患，请列出这 3 个 ID，不要合并为“发现了若干病患”。
- **保留结果，删除碎碎念**：只保留查询返回的表格结果，删除 Agent 关于“我接下来执行...”的无意义思考。

输出语言：中文。输出必须保留以上豁免清单里的所有硬证据。
"""),
    ("human", "待压缩的线索列表：\n{findings}")
])

def compress_findings_to_summary(findings_list):
    """
    调用廉价、快速模型执行线索摘要。
    findings_list: List[str]
    返回: 压缩后的字符串
    """
    if not findings_list:
        return "尚无发现。"
    
    findings_raw = "\n".join([f"- {i+1}. {f}" for i, f in enumerate(findings_list)])
    
    # 我们固定选择性价比最高的 Flash 模型处理摘要任务
    try:
        llm, _ = model_manager.get_adaptive_llm(model_id="qwen-long", require_tools=False)
        response = llm.invoke(COMPRESSOR_PROMPT.format_messages(findings=findings_raw))
        # 兼容性修复：处理可能返回的列表内容
        content = response.content
        if isinstance(content, list):
            content = " ".join([str(item) for item in content])
        summary = content.strip()
        logger.info(f"!!! [线索压缩引擎] 万字线索已成功提纯 (长度: {len(summary)}) !!!")
        return summary
    except Exception as e:
        logger.error(f"证据压缩失败: {e}")
        # 保底处理：如果压缩失败，则返回原始列表的截断版
        return findings_raw[:2000] + "\n...[由于技术原因，部分线索执行了物理截断]..."
