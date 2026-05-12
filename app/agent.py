import os
import sys
import warnings
import pydantic
from loguru import logger

# [DEPRECATED] 此模块已被 agent_graph.py 完全取代，仅保留供旧版测试脚本兼容。
# 新代码应使用: from app.agent_graph import get_graph_executor
warnings.warn(
    "app.agent is deprecated. Use app.agent_graph.get_graph_executor instead.",
    DeprecationWarning,
    stacklevel=2,
)

# [核心补丁] 修复 2026 年 LangChain 0.3+ 移除 pydantic_v1 导致的所有旧版模型驱动崩溃
# 将 Pydantic v2 内置的 v1 兼容层直接映射回命名空间
try:
    import langchain_core
    # 动态创建并注入模块
    if "langchain_core.pydantic_v1" not in sys.modules:
        sys.modules["langchain_core.pydantic_v1"] = pydantic.v1
        logger.info("已成功建立 Pydantic v1 运行时补丁，全量异构算力已并网。")
except Exception as e:
    logger.warning(f"兼容补丁注入失败: {e}")

import json
import faiss
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
try:
    from langchain_classic.agents import AgentExecutor, create_openai_tools_agent
except ImportError:
    AgentExecutor = None
    create_openai_tools_agent = None
    logger.warning("langchain_classic 未安装，agent.py 旧版 AgentExecutor 不可用。请迁移至 agent_graph.py。")
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage
from langchain_community.vectorstores import FAISS
from langchain_community.docstore.in_memory import InMemoryDocstore
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.tools import execute_audit_sql, list_tables, get_table_schema, calculator, search_expert_knowledge
from app.model_manager import model_manager

load_dotenv()

# 延迟加载资源缓存
_llm = None
_embeddings = None
_prompt = None

def get_llm():
    global _llm
    if _llm is None:
        _llm = model_manager.get_adaptive_llm(require_tools=True)[0]
    return _llm

def get_embeddings():
    from app.tools import get_embeddings
    return get_embeddings()

def build_vector_store(force_rebuild=False):
    from app.tools import build_vector_store
    return build_vector_store(force_rebuild)

# 初始化向量库 - 延迟加载
_vector_store = None

def get_vector_store():
    # 为了兼容旧版调用，从 tools 转发
    from app.tools import get_vector_store
    return get_vector_store()

EXPERT_SYSTEM_PROMPT = """你是一名医保审计专家。你已经内化了所有的稽核表 Schema 和核心政策规则。
你的任务是：由用户提问，你直接输出深度审计报告。

## 执行指令：
1. 你的思考过程必须包裹在 ⟦THOUGHT⟧ 标签中。
2. 你的 SQL 执行建议必须包裹在 ⟦REASONING⟧ 标签中，并使用正确的 ClickHouse 或 MySQL 语法。
3. 最终回复给用户的必须是结构清晰、数据精准的“审计风险卡片”。

## 极其重要的输出规则：
- **卡片排版**：强制使用 [### 🚩 风险特征] 的层级结构。
- **数据一致**：涉案金额、机构名称必须与 SQL 执行结果 100% 对应。
- **安全红线**：禁止在最终卡片中输出任何物理表名或 SQL 代码。
"""

def get_prompt(expert_mode=False, schema_info=""):
    global _prompt
    
    system_content = EXPERT_SYSTEM_PROMPT if expert_mode else """你是一名专业的智能稽核助手。你的任务是基于医疗数据和政策条文，为用户提供最终的稽核分析报告。
        
        ## [机密-仅供内部SQL构造] 核心库Schema:
        {schema_info}
        
        ## 极其重要的输出规则（违规将导致数据无法正常显示）：
        1. **排版格式**：禁止输出任何横向宽表格（即不使用 | ---- | 语法）。
        2. **垂直卡片流**：每一个高风险案例必须以“Markdown 标题 + 列表”的样式纵向排版。请严格按以下模板输出每个案例：
        
           ### 🚩 [风险等级] 案例名称 (或案例 ID)
           - **涉及机构**: [机构名称]
           - **具体表现**: [异常行为简述]
           - **涉案金额**: [金额]
           - **政策依据**: [具体的政策条款名称]
           - **稽核建议**: [下一步处理建议]
           ---
        
        3. **思考隔离**：你必须将所有的逻辑分析过程包裹在 `<thought>` 和 `</thought>` 标签内。
        4. **数据安全与事实锚点 (Factual Anchor)**：
           - **具体表现** 字段必须且仅能依据 `execute_audit_sql` 返回的真实观测数据编写。严禁捏造任何 SQL 结果中未出现的医院、金额或日期。
           - **政策依据** 字段必须通过 `search_expert_knowledge` 获取。你可以将政策逻辑应用到事实数据上，但严禁将政策里的“示例金额”误导为“实发金额”。
           - 回复中严禁出现任何表名（fqz_开头的标识符），字段名（英文下划线标识符如medfee_sumamt）、SQL代码片段。
           - 用业务语言代替技术语言。例如：说"住院记录"而非表名，说"医疗费用"而非字段名。
        5. **输出协议一致性 (Audit-Card-V1)**：
           - 不论查询的时间跨度（1个月或1年），禁止输出大段综述。
           - 必须将结果拆分为 3-5 个独立的"风险卡片"。
           - 每个卡片强制使用以下格式（Markdown）：
             ### 🚩 [卡片名称：机构名 + 风险特征简述]
             - **涉及机构**: [必须与 SQL 结果中的医院名 100% 对应]
             - **具体表现**: [描述 SQL 查出的异常事实，例如：同一人同日结算两次]
             - **涉案金额**: [必须与 SQL 结果中累计的金额 100% 对应]
             - **政策依据**: [具体的政策条款名称或逻辑来源]
             - **稽核建议**: [针对该异常行为的专业建议]
             ---
        6. **静默执行**：不要对用户说"我正在查询"、"让我分析"之类的过程描述。直接输出稽核卡片，没有数据时才告知用户。
        7. **专家知识库优先**：在处理复杂的 SQL 需求或违规判定时，必须优先调用 `search_expert_knowledge` 检索现有的稽核逻辑和政策依据。
        8. **确定性计算红线 (Calculation Redline)**：
           - **严禁心算**：禁止在回复中直接写出未经工具计算的金额累加、平均值或百分比。
           - **优先 SQL 聚合**：金额汇总、均值计算应尽可能在 SQL 层面完成（如 `SUM(medfee_sumamt)`）。
           - **强制工具计算**：对于跨 SQL 结果的数值汇总、费用占比计算，必须调用 `calculator` 工具，并可通过其控制精度（默认2位）。
           - **输出一致性**：最终回复中的金额必须与工具（SQL 或 calculator）返回的结果 100% 对应。"""

    return ChatPromptTemplate.from_messages([
        ("system", system_content),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

# 获取工具列表
def get_tools():
    return [execute_audit_sql, list_tables, get_table_schema, calculator, search_expert_knowledge]

# search_expert_knowledge 已通过 app.tools 导入

# search_expert_knowledge 已在下方定义

# 导出动态构建函数，支持根据前端 model_id 实时切换算力
def get_executor(model_id: str = None):
    # [V33.6 架构归一化] 切换至 hardened AgentGraph
    from app.agent_graph import AgentGraph
    
    config = None
    if model_id:
        config = model_manager.providers.get(model_id)
        
    # 构建 Graph 实例
    graph_instance = AgentGraph(model_id=model_id)
    hardened_app = graph_instance.compile()
    
    # 模拟 AgentExecutor 的接口以实现零偏差迁移
    class GraphExecutorWrapper:
        def __init__(self, app, model_id):
            self.app = app
            self.model_id = model_id
            
        async def ainvoke(self, inputs: dict, config: dict = None):
            # 将 ainvokes 的参数映射到 Graph 的 State
            # Graph 期望 { "messages": [...], "findings": [], ... }
            human_msg = inputs.get("input", "")
            chat_history = inputs.get("chat_history", [])
            
            # 合并历史消息
            initial_state = {
                "messages": chat_history + [HumanMessage(content=human_msg)],
                "tasks": [],
                "sql_query": "",
                "raw_data": "",
                "audit_findings": [],
                "structured_report": None,
                "metadata": {"user_id": "audit_system"},
                "session_id": "api_session",
                "error_log": "",
                "retry_count": 0
            }
            
            # 设置递归限制
            run_config = config or {"recursion_limit": 50}
            if "recursion_limit" not in run_config:
                run_config["recursion_limit"] = 50
                
            final_state = await self.app.ainvoke(initial_state, run_config)
            
            # 提取最后一条消息作为 output
            msgs = final_state.get("messages", [])
            output = ""
            if msgs:
                output = msgs[-1].content
                
            return {
                "output": output,
                "intermediate_steps": [] # Graph 不再暴露中间步骤以保护隐私
            }

    executor = GraphExecutorWrapper(hardened_app, model_id)
    return executor, model_id or "default"
