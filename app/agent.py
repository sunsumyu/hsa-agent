import os
import json
import faiss
from loguru import logger
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_classic.agents import AgentExecutor, create_openai_tools_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_community.vectorstores import FAISS
from langchain_community.docstore.in_memory import InMemoryDocstore
from app.tools import execute_audit_sql, list_tables
from app.model_manager import model_manager

load_dotenv()

# 初始化高可用 LLM 集群 - 支持几十个模型的自动化动态切换
llm = model_manager.get_adaptive_llm(require_tools=True)

# 初始化 Embedding - 使用百炼云端模型 (text-embedding-v3)
embeddings = OpenAIEmbeddings(
    model=os.getenv("EMBEDDING_MODEL", "text-embedding-v3"),
    api_key=os.getenv("BAILIAN_API_KEY"),
    base_url=os.getenv("BAILIAN_BASE_URL"),
    check_embedding_ctx_length=False,
    chunk_size=10
)

def build_vector_store():
    """从 Java 目录加载政策及表结构知识库并构建向量库。"""
    try:
        project_root = os.getenv("PROJECT_ROOT", "e:/chain/fqz-hsa-manage")
        kb_files = [
            f"{project_root}/hsa-agent/src/main/resources/medical_policies.json",
            f"{project_root}/hsa-agent/src/main/resources/audit_rules_kb.json",
            f"{project_root}/hsa-agent/src/main/resources/database_tables_kb.json",
            f"{project_root}/hsa-agent/src/main/resources/clickhouse_audit_guide.md"
        ]
        
        texts = []
        for kb_file in kb_files:
            if os.path.exists(kb_file):
                logger.info(f"正在加载知识文件: {kb_file}")
                with open(kb_file, 'r', encoding='utf-8') as f:
                    if kb_file.endswith(".json"):
                        data = json.load(f)
                        for item in data:
                            # 兼容不同类型的 JSON 知识格式
                            content = item.get("policyContent") or item.get("ruleContent") or item.get("content") or ""
                            if content:
                                texts.append(content)
                    elif kb_file.endswith(".md"):
                        # 直接读取 Markdown 内容
                        texts.append(f.read())
        
        if texts:
            logger.info(f"正在构建向量库，共加载 {len(texts)} 条知识条目...")
            vector_store = FAISS.from_texts(texts, embeddings)
            return vector_store
        else:
            logger.warning("知识库未发现有效数据。")
            return None
    except Exception as e:
        logger.error(f"构建向量库失败: {e}")
        return None

# 初始化向量库
vector_store = build_vector_store()

# 定义 Agent 的 Prompt
prompt = ChatPromptTemplate.from_messages([
    ("system", """你是一名专业的智能稽核助手。你的任务是基于医疗数据和政策条文，为用户提供最终的稽核分析报告。

## [机密-仅供内部SQL构造] 核心库Schema:
以下表名和字段名属于系统内部机密。你在面向用户的回复中绝对禁止提及任何表名(如fqz_开头的名称)、字段名(如medfee_sumamt)、SQL语句或数据库术语。违反此规则等同于数据泄露。
1. 结算主表 fqz_all_yy_yd_1: fixmedins_name(机构名), medfee_sumamt(总金额), setl_time(结算时间), admdvs(医保区划)
2. 住院明细表 fqz_ptzy_hosp: fixmedins_code(机构代码), fixmedins_name(机构名), ipt_days_hj(住院天数), medfee_sumamt(总金额), setl_rq(结算日期)
[注意] 物理表不含 diag_name 或 psn_no。如果查询这些字段报错，请立即调用 get_table_schema 重新核实。
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
4. **数据安全红线（最高优先级）**：
   - 回复中严禁出现任何表名（fqz_开头的标识符）、字段名（英文下划线标识符如medfee_sumamt）、SQL代码片段。
   - 用业务语言代替技术语言。例如：说"住院记录"而非表名，说"医疗费用"而非字段名。
   - 用户只需要看到稽核卡片结果，不需要知道你查了什么表或执行了什么SQL。
   - 禁止说"我将查询xxx表"、"从xxx表中获取"等透露内部实现的文字。
5. **输出协议一致性 (Audit-Card-V1)**：
   - 不论查询的时间跨度（1个月或1年），禁止输出大段综述。
   - 必须将结果拆分为 3-5 个独立的"风险卡片"。
   - 每个卡片强制使用以下格式（Markdown）：
     ### 🚩 [卡片名称：机构名 + 风险特征简述]
     - **涉及机构**: xxx
     - **具体表现**: xxx
     - **涉案金额**: 累计金额/单笔金额
     - **政策依据**: xxx
     - **稽核建议**: xxx
     ---
6. **静默执行**：不要对用户说"我正在查询"、"让我分析"之类的过程描述。直接输出稽核卡片，没有数据时才告知用户。"""),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

# 工具列表
tools = [execute_audit_sql, list_tables]

# 添加政策检索工具
from langchain_core.tools import tool
@tool
def search_policies(query: str) -> str:
    """检索并返回与医疗审计、医保报销或违规处罚相关的政策条文。"""
    if not vector_store:
        return "错误: 向量库未初始化。"
    
    docs = vector_store.similarity_search(query, k=3)
    return "\n\n".join([doc.page_content for doc in docs])

tools.append(search_policies)

# 导出动态构建函数，支持根据前端 model_id 实时切换算力
def get_executor(model_id: str = None):
    # 通过管理器获取对应的（且带回退能力的）LLM
    # 如果 model_id 为 None，则按注册表优先级自动选择
    dynamic_llm, resolved_id = model_manager.get_adaptive_llm(model_id=model_id, require_tools=True)
    
    # 构建动态 Agent
    dynamic_agent = create_openai_tools_agent(dynamic_llm, tools, prompt)
    return AgentExecutor(agent=dynamic_agent, tools=tools, verbose=True), resolved_id
