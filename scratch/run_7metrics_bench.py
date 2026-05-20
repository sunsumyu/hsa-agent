# -*- coding: utf-8 -*-
"""
HSA 7-Dimension Agent Benchmark  [VERBOSE MODE]
================================================
每个节点的完整 Prompt + 完整 Response 全部打印到控制台。
"""
import os, sys, asyncio, json, time, subprocess
from datetime import datetime
from loguru import logger
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langchain_core.outputs import LLMResult
from typing import Any, List, Union

# [V58.0] Visual Enhancement
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.theme import Theme
from rich.text import Text
from rich.live import Live
from rich.status import Status

console = Console(theme=Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "bold red",
    "success": "bold green",
    "role": "bold magenta"
}))

sys.path.append(os.getcwd())
os.environ["PYTHONIOENCODING"] = "utf-8"

# [V58.3] 环境配置由 app.core.config 统一接管，此处不再硬编码
from app.core.config import settings

if sys.platform == "win32":
    # 强制 Windows 终端输出 UTF-8，防止 UnicodeEncodeError (GBK)
    import io
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

from app.core.agent_graph import workflow, _record_usage_with_budget
from app.infra.model_manager import model_manager
from app.infra.usage_tracker import usage_tracker
from app.core.observability import init_observability, shutdown_observability

# ── LangChain Callback: 每次 LLM 调用前后完整打印 ────────────────────
SEP  = "=" * 72
SEP2 = "-" * 72
SEP3 = "~" * 72

class VerboseLLMCallback(BaseCallbackHandler):
    """拦截 LangChain 的每次 LLM 调用，使用 Rich 美化输出。"""

    def _render_content(self, content: Any) -> str:
        if isinstance(content, str):
            # 尝试检测是否为 SQL
            if "SELECT" in content.upper() and "FROM" in content.upper():
                return Syntax(content, "sql", theme="monokai", word_wrap=True)
            return content
        return str(content)

    def on_chat_model_start(self, serialized: dict, messages: List[List[BaseMessage]], **kwargs):
        model = serialized.get("name", serialized.get("id", ["?"])[-1])
        console.rule(f"[bold blue]LLM INVOKE: {model}[/]", style="blue")
        
        for turn in messages:
            for msg in turn:
                role = type(msg).__name__.replace("Message", "")
                color = "magenta" if role == "System" else "green" if role == "Human" else "cyan"
                
                content = getattr(msg, "content", str(msg))
                # 如果内容是 SQL，使用 Syntax 高亮
                if isinstance(content, str) and ("SELECT" in content.upper() or "INSERT" in content.upper()):
                    display = Syntax(content, "sql", theme="monokai", word_wrap=True)
                else:
                    display = content

                console.print(Panel(
                    display, 
                    title=f"[bold {color}]{role}[/]", 
                    border_style=color,
                    padding=(0, 1)
                ))

    def on_llm_end(self, response: LLMResult, **kwargs):
        for gen_list in response.generations:
            for gen in gen_list:
                text = getattr(gen, "text", None) or getattr(getattr(gen, "message", None), "content", str(gen))
                console.print(Panel(
                    text, 
                    title="[bold yellow]LLM RESPONSE[/]", 
                    border_style="yellow",
                    padding=(0, 1)
                ))
        console.print("\n")

    def on_llm_error(self, error: Union[Exception, KeyboardInterrupt], **kwargs):
        console.print(Panel(str(error), title="[bold red]LLM ERROR[/]", border_style="red"))

# 全局回调实例（注入到每次 workflow.ainvoke 的 config 中）
VERBOSE_CB = VerboseLLMCallback()


# ── Token Predictions ─────────────────────────────────────────────────
PREDICTED = {
    "planner_light": {"in": 1800, "out": 700},
    "planner_heavy": {"in": 2200, "out": 900},
    "sqlexec":       {"in": 1200, "out": 600},
    "reporter":      {"in": 2000, "out": 1000},
    "judge":         {"in": 1100, "out": 400},
}

# ── Test Cases ────────────────────────────────────────────────────────
# TEST_CASES = [
#     {
#         "id": "QA-01", "tag": "Repeat Billing",      "diff": "*   ",
#         "prompt": "核查 2024 年是否存在同一天、同一患者、在同一医院多次收取的结算费用？",
#         "pred_tokens": 9000,
#     },
#     {
#         "id": "QA-03", "tag": "Gender Conflict",     "diff": "**  ",
#         "prompt": "对全市结算数据进行性别冲突检查：找出男性患者产生妇科或产科费用的异常明细。",
#         "pred_tokens": 10500,
#     },
#     {
#         "id": "QA-06", "tag": "Dual Hospitalization","diff": "*** ",
#         "prompt": "核查是否存在同一患者在同一天内，在两家不同医院【同时住院】的情况？",
#         "pred_tokens": 13000,
#     },
#     {
#         "id": "QA-11", "tag": "Fraud Network",        "diff": "****",
#         "prompt": "核查中心医院是否存在与职工共用联系方式（尾号8888）且报销额度异常偏高的患者群？",
#         "pred_tokens": 15000,
#     },
# ]

# TEST_CASES = [
#     {
#         "id": "QA-NEW-01", "tag": "Decomp Hospital",   "diff": "*** ",
#         "prompt": "对2024年全市住院患者进行核查，是否存在在同一家医院出院后15天内再次入院的“分解住院”可疑行为？",
#         "pred_tokens": 12000,
#     },
#     {
#         "id": "QA-NEW-02", "tag": "Cross Store Spend",  "diff": "*** ",
#         "prompt": "核查2024年度是否存在同一患者跨5家及以上定点药店进行购药，且基金支付总额超过5000元的异常消费行为？",
#         "pred_tokens": 11000,
#     },
#     {
#         "id": "QA-NEW-03", "tag": "High Freq Drug",     "diff": "**  ",
#         "prompt": "针对定点药店购药场景，核查2024年是否存在单人累计在同一药店购药频次达到10次及以上的“高频购药”异常明细？",
#         "pred_tokens": 10500,
#     },
#     {
#         "id": "QA-NEW-04", "tag": "Ghost Bed Hospital", "diff": "****",
#         "prompt": "核查2024年度是否存在住院天数异常长（如超过14天）但医疗总费用极低的可疑“挂床住院”或虚假住院案例？",
#         "pred_tokens": 13500,
#     },
#     {
#         "id": "QA-NEW-05", "tag": "Overlapping Hosp",   "diff": "****",
#         "prompt": "核查2024年是否存在同一参保人，在完全相同的时间段内在两家不同的定点医疗机构【同时挂账住院】的违规行为？",
#         "pred_tokens": 14000,
#     },
# ]

# ── Test Cases ────────────────────────────────────────────────────────
# TEST_CASES = [
#     {
#         "id": "QA-CUST-01", "tag": "Contradictory Account Deductions", "diff": "**  ",
#         "prompt": "是否存在患者在单次住院期间，个人账户扣款出现了多次自相矛盾的记录？",
#         "pred_tokens": 11000,
#     },
#     {
#         "id": "QA-CUST-02", "tag": "Outpatient Dialysis Abuse", "diff": "*** ",
#         "prompt": "帮我核查是否存在城乡居民在民营综合医院进行违规报销门诊透析的情形。",
#         "pred_tokens": 12000,
#     },
#     {
#         "id": "QA-CUST-03", "tag": "Contradictory Hospitalization Days", "diff": "**  ",
#         "prompt": "是否存在患者在单次住院期间，住院总天数出现了多次自相矛盾的记录？",
#         "pred_tokens": 11000,
#     },
#     {
#         "id": "QA-CUST-04", "tag": "Stent Compensation Exceeded", "diff": "****",
#         "prompt": "核实一下去年机关事业退休人员在冠状动脉支架项目上的定额补偿是否超标。",
#         "pred_tokens": 13000,
#     },
#     {
#         "id": "QA-CUST-05", "tag": "Outpatient Dialysis Abuse 2", "diff": "*** ",
#         "prompt": "帮我核查是否存在城乡居民在民营综合医院进行违规报销门诊透析的情形。",
#         "pred_tokens": 12000,
#     },
# ]


# TEST_CASES = [
#     {
#         "id": "QA-CUST-01", 
#         "tag": "Contradictory Account Deductions", 
#         "diff": "**  ",
#         "prompt": "核对一下结算明细，有没有同一次住院的单据里，个人账户实际扣款金额跟总费用流水对不上的矛盾记录？",
#         "pred_tokens": 11000,
#     },
#     {
#         "id": "QA-CUST-02", 
#         "tag": "Outpatient Dialysis Abuse", 
#         "diff": "*** ",
#         "prompt": "跑一下民营综合医院的数据，重点排查有没有城乡居民违规刷门诊血液透析报销的单子。",
#         "pred_tokens": 12000,
#     },
#     {
#         "id": "QA-CUST-03", 
#         "tag": "Contradictory Hospitalization Days", 
#         "diff": "**  ",
#         "prompt": "查一下底表，有没有哪次住院根据入院和出院日期算出来的天数，跟医院实际上传的结算天数严重不符的情况？",
#         "pred_tokens": 11000,
#     },
#     {
#         "id": "QA-CUST-04", 
#         "tag": "Stent Compensation Exceeded", 
#         "diff": "****",
#         "prompt": "调取一下去年的数据，核实机关事业退休人员做冠脉支架手术时，医保基金的定额补偿有没有突破最高支付限额。",
#         "pred_tokens": 13000,
#     },
#     {
#         "id": "QA-CUST-05", 
#         "tag": "Outpatient Dialysis Abuse 2", 
#         "diff": "*** ",
#         "prompt": "把民营医院门诊特慢病结算拉出来看看，尤其是城乡居民医保门诊透析这块，排查下有没有超频次或者挂靠报销的嫌疑。",
#         "pred_tokens": 12000,
#     },
# ]


# TEST_CASES = [
#     {
#         "id": "QA-CUST-01", 
#         "tag": "Deceased Patient Billing", 
#         "diff": "*** ",
#         "prompt": "查一下死亡人员的数据交叉比对，看看有没有人在民政那边已经宣告死亡注销户口了，但医保系统里还在源源不断地产生刷卡或者住院费用的。",
#         "pred_tokens": 12000,
#     },
#     {
#         "id": "QA-CUST-02", 
#         "tag": "Gender Diagnosis Conflict", 
#         "diff": "**  ",
#         "prompt": "把全市参保人的结算单扫一遍，专门挑那些登记是男性，但是诊断或者收费明细里却开出了子宫彩超或者保胎药这种明显违反常识的记录。",
#         "pred_tokens": 11000,
#     },
#     {
#         "id": "QA-CUST-03", 
#         "tag": "Decomposed Hospitalization", 
#         "diff": "****",
#         "prompt": "排查一下二级医院的住院情况，有没有同一个病号因为同一个毛病，出院还没过半个月又被重新办入院手续的？这种分解住院骗统筹基金的要重点揪出来。",
#         "pred_tokens": 14000,
#     },
#     {
#         "id": "QA-CUST-04", 
#         "tag": "Chronic Disease Over-prescription", 
#         "diff": "*** ",
#         "prompt": "把门诊慢特病的药店结算数据拉出来，重点看高血压和糖尿病，有没有单次开药量直接超过90天最大用药上限的？这种很大可能是药贩子在倒药。",
#         "pred_tokens": 12000,
#     },
#     {
#         "id": "QA-CUST-05", 
#         "tag": "Abnormal Outpatient Billing", 
#         "diff": "**  ",
#         "prompt": "筛一下乡镇卫生院和社区诊所的数据，像普通感冒发烧这种小病，单次门诊报销如果直接奔着七八百甚至上千去了，肯定有串换项目或者搭车开药的问题，把超标明细全列出来。",
#         "pred_tokens": 11000,
#     },
# ]

# TEST_CASES = [
#     {
#         "id": "QA-CUST-06", 
#         "tag": "Concurrent Location Conflict", 
#         "diff": "*** ",
#         "prompt": "查一下有没有这种物理分身的单子：患者在A医院处于‘在院’状态（还没办理出院），但医保卡却同一时间跑到几十公里外的B药店或者C诊所刷卡买药了？这种典型的‘挂床住院’或者‘出借医保卡’的情况必须严查。",
#         "pred_tokens": 12500,
#     },
#     {
#         "id": "QA-CUST-07", 
#         "tag": "Age-Diagnosis Mismatch", 
#         "diff": "**  ",
#         "prompt": "跑个数据，把那种参保人年龄和报销病种完全反人类的记录挑出来。比如不到五岁的儿童报销了‘老年性白内障’或者‘阿尔茨海默症’，这种绝对是医院为了多骗统筹基金瞎填疾病代码、高套病种的。",
#         "pred_tokens": 11000,
#     },
#     {
#         "id": "QA-CUST-08", 
#         "tag": "Absurd Daily Billing", 
#         "diff": "*** ",
#         "prompt": "查下住院的收费明细表，有没有单日计费数量极其离谱的？比如系统里显示一天收了3次以上的‘一级护理费’，或者一天给同一个人拔了8颗以上的牙。把这种明显分解计费和虚构数量的清单导出来。",
#         "pred_tokens": 11500,
#     },
#     {
#         "id": "QA-CUST-09", 
#         "tag": "Targeted Doctor Farming", 
#         "diff": "****",
#         "prompt": "重点筛查门诊统筹，有没有哪个参保人在半年内，跑了同一家基层定点机构超过50次，而且每次都是在系统里挂同一个医生的号开特慢病药？这种‘死盯一个大夫薅羊毛’的极有可能存在医患串通套保取药。",
#         "pred_tokens": 14000,
#     },
#     {
#         "id": "QA-CUST-10", 
#         "tag": "Prescription-Pharmacy Collusion Ring", 
#         "diff": "*****",
#         "prompt": "帮我挖一个深度的‘回流药’利益链团伙（这个关联极其复杂）：去查在任意连续30天的滑动窗口内，有没有超过5个不同的参保人（互相之间预留了相同的手机号或家庭地址），他们都在同一家医院的同一个医生那里开出了高价慢病药，然后这批人竟然无一例外地都跑到同一家特定的院外定点药店去刷卡结算，并且药店结算时间跟医院开处方的时间相隔不到24小时？把这种‘指定医生开单-团伙集中拿药-特定药店洗钱’的闭环网络给我全盘抓出来。",
#         "pred_tokens": 18000,
#     },
# ]

# TEST_CASES = [
#     {
#         "id": "QA-CUST-06", 
#         "tag": "Duplicate Consultation Fees", 
#         "diff": "*   ", # 简单：单表同日去重与频次校验
#         "prompt": "给我扫一下基层门诊的流水，看看有没有哪个大夫给同一个病号，在一天之内竟然收了两次甚至三次‘一般诊疗费’的？这种拿基础挂号费疯狂重复计费的薅羊毛单子直接列个明细给我。",
#         "pred_tokens": 8000,
#     },
#     {
#         "id": "QA-CUST-07", 
#         "tag": "ICU Patient Pharmacy Billing", 
#         "diff": "*** ", # 中等：跨表时空与物理状态冲突
#         "prompt": "把重症监护病房的数据和外面的药店数据做个交叉比对。去查查那些明明在系统里显示正躺在ICU里插管抢救的重病号，同一天居然还在外面的定点药店刷医保卡买了大额的慢性病药或者中药饮片？人都下不了床怎么去买的药，这种拿卡套现的直接锁死。",
#         "pred_tokens": 12000,
#     },
#     {
#         "id": "QA-CUST-08", 
#         "tag": "Rehab Sliding Window Evasion", 
#         "diff": "****", # 困难：跨机构滑动时间窗口聚合
#         "prompt": "盯一下中医针灸和康复理疗这块。有些诊所为了躲系统‘单次疗程不超过15天’的报警，教唆病号每按满14天就换一家新店接着刷。你给我写个滚动算时间的逻辑，把那种连续半年内，像打游击一样跨了三四家不同诊所，累计理疗天数加起来超过100天的‘职业理疗客’全挖出来。",
#         "pred_tokens": 15000,
#     },
#     {
#         "id": "QA-CUST-09", 
#         "tag": "Prescription Outflow Collusion Ring", 
#         "diff": "*****", # 极难：高基数统计学基线 + 复杂机构利益链图谱
#         "prompt": "来个有难度的，查一下处方外送背后的黑色利益链。去全省特慢病结算数据里跑个网络出来：看有没有某家公立大医院的某个特定科室，他们开出来的天价特药处方，有超过80%最后都流向了外面同一家不起眼的私人小药房结算？而且这家小药房全年的医保基金流水，竟然有一大半都是靠这一个科室的处方撑起来的。把这种‘指定医生开单-勾结特定药店洗钱’的高度绑定团伙给我揪出来。",
#         "pred_tokens": 18000,
#     },
# ]


# TEST_CASES = [
#     {
#         "id": "QA-CUST-11", 
#         "tag": "False Anesthesia Billing", 
#         "diff": "****", # 困难：强业务逻辑冲突与隐含时序
#         "prompt": "查一下手术室和麻醉科的流水。有没有哪家医院给病人收了‘全身麻醉’或者‘椎管内麻醉’的钱，但是这人在同一天的费用明细里，连一丁点像丙泊酚、七氟烷或者罗哌卡因这种必备的麻醉药费都没产生的？光收高价操作费不耗药，这种虚构麻醉服务的造假单子全给我拉出来。",
#         "pred_tokens": 14500,
#     },
#     {
#         "id": "QA-CUST-12", 
#         "tag": "Dialysis Phantom Billing Ring", 
#         "diff": "*****", # 极难：动态基线 + 图谱聚类 + 物理极限违背
#         "prompt": "盯紧那些民营综合医院的血透室，帮我抓个大案子：先算算他们这几家医院平时一天最多能接多少个透析病人。然后你去跑按月结算的数据，看有没有哪家医院在某个月里，它报销的‘血液透析’总人次，竟然远远超过了他们机器满负荷连轴转24小时能做出来的物理极限？顺便查一下，在这个超限的月份里，是不是有一批外地户口的特病患者突然集体‘空降’到这家医院集中刷卡？这绝对是成建制的买病人挂空床骗保。",
#         "pred_tokens": 18500,
#     },
# ]


# TEST_CASES = [
#     {
#         "id": "QA-CUST-13", 
#         "tag": "Cross-Institution Medication Hoarding", 
#         "diff": "****", # 困难：跨机构滑动时间窗与剂量冲突
#         "prompt": "去查查跨院重复开药的漏子。给我设个滚动的时间窗，专门抓那种前脚刚在A医院开了足足30天用量的某种高价靶向药或者慢病药，结果连一个星期都没过，这人又跑到B医院或者外面的大药房，把一模一样的药又开了一个月的量。这种明显是跨机构囤药倒卖，拿医保统筹池当提款机呢，把这批人全给我筛出来。",
#         "pred_tokens": 15000,
#     },
#     {
#         "id": "QA-CUST-14", 
#         "tag": "Bundled vs Unbundled Double Dipping", 
#         "diff": "****", # 困难：医疗服务目录的层级包含与互斥逻辑
#         "prompt": "扫一下重症监护室（ICU）和抢救室的明细清单，找那种‘双头吃’的乱收费硬伤。比如医院明明已经按天收了高昂的‘重症监护综合费’或者打包的抢救费，按国家医保目录规定，这块已经包含了基础的吸痰、指尖测血糖、特级护理这些常规动作。结果你再去他当天的流水里看，他又把这些应该免费包含的小项目单独拆出来，一天继续计费个十几次甚至几十次。这种把打包收费和单项收费混着报的，全给我扒出来。",
#         "pred_tokens": 14500,
#     },
#     {
#         "id": "QA-CUST-15", 
#         "tag": "Surgeon Physical Limit Violation", 
#         "diff": "*****", # 极难：医生维度的时序聚合与物理极限
#         "prompt": "给我深挖一下外科系统的主刀大夫考勤和手术记录。你用系统里国家规定的手术基准时长去算，把同一个大夫在同一天内作为‘第一主刀’的所有三四级大手术的基准时长全加起来。去看看有没有那种一天24小时不吃不喝连轴转，做出来的手术总时长居然超过了30个小时的？这要不是主刀医生会分身术，要不就是科室在疯狂虚记手术台次、或者让没有资质的规培生代刀骗高额手术费，直接按重大欺诈线索给我提取。",
#         "pred_tokens": 17500,
#     },
#     {
#         "id": "QA-CUST-16", 
#         "tag": "DRG Revolving Door Admission", 
#         "diff": "*****", # 极难：DRG/DIP博弈下的复杂序列状态匹配
#         "prompt": "盯紧DRG付费改革后那些搞‘假出院’的医院。你去查那种卡着病种付费最高额度办理出院的重病号，这人出院还没满48小时，立马又在同一家医院或者同一个医疗集团下的分院重新办了入院，而且看的主诊断连变都没变。最绝的是，你对比下这两段住院期间的医嘱和耗材明细，比如呼吸机使用记录或者高压氧舱根本就没断过。这绝对是医院为了躲避单次住院超支扣款，强行把一次连贯的治疗切成两次来赚两次病种钱的，给我打个极高风险的标签。",
#         "pred_tokens": 18500,
#     },
#     {
#         "id": "QA-CUST-17", 
#         "tag": "Household Card Sharing Ring", 
#         "diff": "*****", # 极难：弱连通分量(WCC)实体聚类 + 家族图谱
#         "prompt": "搞个复杂的团伙图谱分析。你把药店的高血压、糖尿病这种好倒卖的特慢病结算数据拉出来，先别看单个人，你去查‘家庭’。看看有没有那种三个甚至五个不同的医保账号，他们留在系统里的紧急联系人手机号或者家庭住址高度相似或者是同一个，然后在过去的连续三个月里，这全家人就像商量好了一样，排队去同一家药店把慢病药的额度全部刷到顶？这根本不是一家人全得病了，这是药贩子收了一家子的卡在集中套现倒药，把这种家族式的套保关系网给我画出来。",
#         "pred_tokens": 19000,
#     },
# ]

# TEST_CASES = [
#     {
#         "id": "QA-CUST-18", 
#         "tag": "Pharmacy Inventory Discrepancy", 
#         "diff": "****", # 困难：跨库对比与进销存倒挂
#         "prompt": "去核查一下定点大药房的进销存数据。你把医保结算系统里某款贵重药的卖出数量，跟药店从正规医药公司进货入库的数量做个比对。要是发现哪家店医保卖出去的药，居然比他们采购进来的还要多，这种‘无中生有’的负库存绝对有问题。要不就是拿医保卡串换卖了大米食用油，要不就是从药贩子手里收的非法回流药，直接把库存倒挂的明细给我拉出来。",
#         "pred_tokens": 15500,
#     },
#     {
#         "id": "QA-CUST-19", 
#         "tag": "Ghost Doctor Prescription", 
#         "diff": "*** ", # 中等：人员状态与业务行为冲突
#         "prompt": "给我扫一遍医生的考勤排班和HIS接诊记录。挑那种明明在人事系统里登记了休产假、出国进修，甚至已经离职退休的大夫，结果他的工号在同一时间段里，还天天在门诊系统里源源不断地开出大额处方、甚至主刀做手术的。这种幽灵医生要不就是科室里有人盗用账号违规代签，要不就是纯粹虚构诊疗记录骗保。",
#         "pred_tokens": 13000,
#     },
#     {
#         "id": "QA-CUST-20", 
#         "tag": "DRG Upcoding Without Evidence", 
#         "diff": "*****", # 极难：DRG高套与临床路径(诊疗手段)交叉互斥
#         "prompt": "盯一下今年呼吸科和心内科的病案首页。看看有没有那种本来只是普通心绞痛或者轻微感冒的病人，医院为了硬凑高级别的DRG分组多拿钱，出院主诊断全给夸大写成‘心力衰竭’或者‘重症肺炎伴呼吸衰竭’。你重点用收费明细去做交叉校验：如果他主诊断写了重症心衰，结果整个住院期间连一丁点强心利尿的抢救药都没开过，也没有上过呼吸机，这种光写重病不给重治的，直接按恶意高套病种抓典型。",
#         "pred_tokens": 18500,
#     },
#     {
#         "id": "QA-CUST-21", 
#         "tag": "Excessive Cross-Hospital Testing", 
#         "diff": "****", # 困难：跨机构短时间内医疗行为重复
#         "prompt": "跑个跨院大型检查的数据。现在卫健委明文要求同级医院检查结果互认，你给我查查，有没有哪个病号在一家三甲医院刚做完一套上千块的增强CT或者核磁共振，出院连三天都没过，跑到另一家三甲医院，原封不动又被开了一模一样的大型检查？这种极其浪费统筹基金的重复检查，要么是医生为了科室创收，要么就是拿病号当刷单工具，把这些重复开单的记录列出来。",
#         "pred_tokens": 14500,
#     },
#     {
#         "id": "QA-CUST-22", 
#         "tag": "Malicious Patient Transfer before Cap", 
#         "diff": "*****", # 极难：费用临界点探测与转院逻辑链路
#         "prompt": "查一下重症和肿瘤病人的转院记录。去挖那种情况：病号在A医院住院，眼看着总费用刚好快要逼近DRG单次支付的盈亏临界点了，突然就极其突兀地被办了转院或者出院，然后当天或者第二天就推到了同城的B医院接着住院治疗。把这种一到费用红线就恶意推诿重病号、故意分解住院费用的操作，按转院时间差和前一次费用的报销占比给我精准定位出来。",
#         "pred_tokens": 18000,
#     },
# ]

TEST_CASES = [
    {
        "id": "QA-CUST-23", 
        "tag": "Therapist Time Overlap / Cloning", 
        "diff": "****", # 困难：同一医务人员的微观时间线重叠计算
        "prompt": "查一下理疗科和康复科的执行大夫。你去按每一分钟去排一下他们做一对一手法治疗的单子，看看有没有哪个大夫练了分身术，在同一时间段里，系统上竟然显示他同时在给五六个病号做必须要医生亲自上手推拿的项目？这种纯粹就是护士拿着卡乱刷、甚至连病号都没来直接挂空床的虚假理疗。",
        "pred_tokens": 14500,
    },
    {
        "id": "QA-CUST-24", 
        "tag": "Service Without Mandatory Consumables", 
        "diff": "****", # 困难：医疗服务与高值耗材的强制伴生逻辑互斥
        "prompt": "去扫一遍血透和骨科大手术的单子，查那种干活不用工具的灵异事件。比如医院收了高昂的血液透析治疗费，但是你在他当天的耗材明细里，连个透析器或者透析管路都找不到；或者骨科收了脊柱内固定手术费，却没看见用任何钛钉钛板的。这就叫只收手工费不走耗材，要么是串换项目套现，要么就是彻头彻尾的虚构手术，把这种自相矛盾的单子全抓出来。",
        "pred_tokens": 15000,
    },
    {
        "id": "QA-CUST-25", 
        "tag": "Biological Limit / Impossible Dental History", 
        "diff": "*****", # 极难：跨周期的生物学常识追踪与历史状态冲突
        "prompt": "把口腔科的医保结算拉出来，尤其是拔牙和根管治疗的。写个逻辑去追溯每个病号的历史看牙记录。正常人一共也就二三十颗牙，你给我找找有没有哪个狠人，在过去两三年里跨了不同的牙科诊所，累计被拔了四五十颗牙的？或者更离谱的，他去年在一家诊所已经拔了左下的大牙，今年在另一家诊所又把同一颗牙给拔了一次的。这种骗医保不仅造假，连基本的生理常识都不要了。",
        "pred_tokens": 18500,
    },
    {
        "id": "QA-CUST-26", 
        "tag": "Automated Batch Billing / Time-Series Anomalies", 
        "diff": "*****", # 极难：微秒级时间戳分布探测与机器行为识别
        "prompt": "查查乡镇卫生院和村卫生室的门诊统筹刷单。你去把每天的结算流水按时间戳精细排个序，看有没有这种极端诡异的现象：连续十几个不同的病号，他们不仅开出来的药或者理疗项目一模一样，而且相互之间结算的时间精准地只隔了三五秒钟，就像是用机器脚本在批量扫码一样。这绝对是村医大半夜把全村的医保卡收集起来，放在刷卡机上集中流水线套现的团伙作案。",
        "pred_tokens": 19000,
    },
]

# ── Judge Prompt ──────────────────────────────────────────────────────
JUDGE_PROMPT = """You are a senior healthcare insurance audit judge with 20 years of experience in medical fraud detection.
Score the following audit report on 7 dimensions (0-10 each, total 70).
Use the detailed rubrics below — do NOT give blanket high scores for zero-findings reports without evidence of thorough scanning.

SCORING RUBRICS:

1. Success (0-10): Was the task fully completed?
   - 10: SQL executed, full report delivered, all task elements addressed including any "draw the graph" requirement
   - 7-9: SQL executed, report delivered, minor gaps
   - 4-6: SQL executed but report is incomplete or one major task element missing
   - 0-3: SQL failed to execute, or report is empty/placeholder

2. Recall (0-10): Were all suspicious violations found? No omissions?
   - 10: Zero-findings reports MUST include: (a) total scan record count, (b) time range covered, (c) ICD-10 code coverage list, (d) 3-tier sensitivity analysis (original/+20%/+50% threshold relaxation)
   - 10: Non-zero findings must cover all logical violation patterns described in the task
   - 7-9: Zero-findings with partial scan boundary proof OR non-zero findings with minor pattern gaps
   - 4-6: Zero-findings with NO scan boundary proof, or only superficial pattern coverage
   - 0-3: Zero-findings with no justification, or obvious logical violations missed

3. Precision (0-10): Are flagged violations accurate? No false positives?
   - 10: All flagged violations have concrete data evidence, no speculation
   - 7-9: Mostly accurate, 1-2 borderline cases
   - 4-6: Some findings lack data backing or use hallucinated data
   - 0-3: Major false positives or fabricated findings

4. Faithfulness (0-10): Is the conclusion grounded in actual data? No hallucination?
   - 10: Every claim traceable to actual SQL output; no invented statistics
   - 7-9: Mostly faithful, minor extrapolations
   - 4-6: Some claims not supported by shown data
   - 0-3: Significant hallucination or contradiction with shown data

5. Relevance (0-10): Does the report directly answer the original question?
   - 10: Answers all aspects of original question PLUS provides actionable next steps (specific, not generic)
   - 7-9: Answers main question but lacks actionable specifics
   - 4-6: Partially answers, misses key aspects of original question
   - 0-3: Fails to address the core audit question

6. Professionalism (0-10): Compliant with healthcare insurance regulations?
   - 10: Cites specific regulatory documents (e.g., 医保发〔2021〕48号, 国卫医发〔2022〕18号) with article numbers; uses correct ICD-10 codes; proper DRG terminology
   - 7-9: Uses correct professional terminology but lacks specific policy citations
   - 4-6: Generally professional but with terminology errors or missing policy basis
   - 0-3: Non-professional language, incorrect regulatory references, or fabricated policies

7. Interpretability (0-10): Is the report clear with solid evidence chains?
   - 10: Contains visual aids (Mermaid graphs for network tasks, ASCII timeline for surgery tasks, comparison tables for double-billing tasks) PLUS clear evidence chains PLUS calculation examples
   - 7-9: Clear evidence chains but lacks visual aids for tasks that explicitly required them (e.g., "画出来")
   - 4-6: Some evidence chains but largely text-only with no visual proof
   - 0-3: Opaque logic, no evidence chains, hard to follow

CRITICAL DEDUCTIONS:
- If original task said "画出来" (draw it) and report has NO Mermaid/graph visualization: Interpretability MAX = 6, Success MAX = 7
- If zero-findings report has NO scan boundary proof (total record count, time range, code coverage): Recall MAX = 5
- If report cites no specific policy document numbers for DRG/ICD/surgery-grade tasks: Professionalism MAX = 7

Return STRICT JSON (no extra text):
{"scores": {"success": 0, "recall": 0, "precision": 0, "faithfulness": 0, "relevance": 0, "professionalism": 0, "interpretability": 0}, "total": 0, "advice": "..."}
"""

# ── Print Helpers ─────────────────────────────────────────────────────
SEP  = "=" * 72
SEP2 = "-" * 72
SEP3 = "~" * 72

def print_block(title: str, content: str, sep: str = SEP2):
    """把一段内容用明显的边框打印出来"""
    print(f"\n{sep}")
    print(f"  {title}")
    print(sep)
    # 每行加缩进
    for line in content.splitlines():
        print(f"  {line}")
    print(sep)
    sys.stdout.flush()

# ── Physical Token + Content Interceptor ─────────────────────────────
class PhysicalTokenTracker:
    """
    拦截 _record_usage_with_budget：
      1. 打印完整 Prompt（每个 message 逐条输出）
      2. 打印完整 Response
      3. 统计 Token 并与预测对比
    """
    def __init__(self):
        self.case_stats   = {}
        self._current     = None
        self._original_fn = None

    def set_case(self, cid):
        self._current        = cid
        self.case_stats[cid] = {}

    def patch(self):
        import app.core.agent_graph as ag
        self._original_fn = ag._record_usage_with_budget
        ref = self

        def intercepted(role, response, model_id, prompt=""):
            resp_text = str(getattr(response, "content", ""))
            prompt_str = str(prompt)

            # [V58.5] 采用 Rich 协议重构终端回显，解决数据原始堆叠问题
            console.rule(f"[bold yellow]NODE: {role.upper()}[/] | [bold cyan]MODEL: {model_id}[/]", style="yellow")
            
            # ── 1. 结构化打印 Prompt ──
            if hasattr(prompt, "__iter__") and not isinstance(prompt, str):
                for i, msg in enumerate(prompt):
                    msg_type = type(msg).__name__.replace("Message", "")
                    color = "magenta" if msg_type == "System" else "green" if msg_type == "Human" else "cyan"
                    content = getattr(msg, "content", str(msg))
                    
                    # 针对 SQL 自动高亮
                    if isinstance(content, str) and ("SELECT" in content.upper() or "INSERT" in content.upper()):
                        display = Syntax(content, "sql", theme="monokai", word_wrap=True)
                    elif isinstance(content, str) and content.startswith("#"):
                        from rich.markdown import Markdown
                        display = Markdown(content)
                    else:
                        display = str(content)

                    console.print(Panel(
                        display,
                        title=f"[{color}]Msg-{i+1} | {msg_type}[/]",
                        border_style=color,
                        padding=(0, 1)
                    ))
            else:
                console.print(Panel(prompt_str, title="[dim]Raw Prompt[/]", border_style="dim"))

            # ── 2. 结构化打印 Response ──
            if resp_text:
                # 针对 JSON 或报告格式进行美化处理
                if resp_text.strip().startswith("{"):
                    try:
                        formatted_json = json.dumps(json.loads(resp_text), indent=2, ensure_ascii=False)
                        display_resp = Syntax(formatted_json, "json", theme="monokai")
                    except: display_resp = resp_text
                else:
                    display_resp = resp_text

                console.print(Panel(
                    display_resp, 
                    title="[bold yellow]RESPONSE (full)[/]", 
                    border_style="yellow",
                    padding=(0, 1)
                ))

            # ── 3. Token 统计 Table ──
            in_t  = usage_tracker._estimate_tokens(prompt_str)
            out_t = usage_tracker._estimate_tokens(resp_text)
            p_in  = PREDICTED.get(role, {}).get("in", "?")
            p_out = PREDICTED.get(role, {}).get("out", "?")
            
            table = Table(title="[bold]Token Consumption Metrics[/]", box=None, show_header=True, header_style="bold blue")
            table.add_column("Type", style="cyan")
            table.add_column("Actual", justify="right", style="green")
            table.add_column("Predicted", justify="right", style="dim")
            table.add_row("Input (Prompt)", str(in_t), str(p_in))
            table.add_row("Output (Gen)", str(out_t), str(p_out))
            console.print(table)
            console.rule(style="dim")

            cid = ref._current or "_"
            if cid not in ref.case_stats:
                ref.case_stats[cid] = {}
            s = ref.case_stats[cid]
            if role not in s:
                s[role] = {"in": 0, "out": 0, "calls": 0}
            s[role]["in"]    += in_t
            s[role]["out"]   += out_t
            s[role]["calls"] += 1

            sys.stdout.flush()
            ref._original_fn(role, response, model_id, prompt)

        ag._record_usage_with_budget = intercepted

    def total(self, cid):
        return sum(v["in"] + v["out"] for v in self.case_stats.get(cid, {}).values())

tracker = PhysicalTokenTracker()
tracker.patch()

# ── Run One Case ──────────────────────────────────────────────────────
async def run_one(case: dict, judge_llm) -> dict:
    cid, prompt, pred = case["id"], case["prompt"], case["pred_tokens"]

    print(f"\n{SEP}")
    print(f"  START CASE [{cid}]  {case['tag']}  diff:{case['diff']}")
    print(f"  QUESTION: {prompt}")
    print(f"  PREDICTED TOKENS: {pred:,}")
    print(SEP)

    tracker.set_case(cid)
    t0 = time.time()
    report_text = "(no report)"
    agent_ok    = False

    try:
        inputs = {"messages": [("user", prompt)],
                  "session_id": f"BENCH_{cid}_{int(t0)}"}
        state    = await workflow.ainvoke(inputs, config={
            "recursion_limit": 15,
            "callbacks": [VERBOSE_CB],
        })

        agent_ok = True
        msgs = state.get("messages", [])
        if msgs:
            last = msgs[-1]
            report_text = last[1] if isinstance(last, tuple) else getattr(last, "content", str(last))
    except Exception as ex:
        report_text = f"(Agent error: {ex})"
        logger.error(f"[{cid}] Agent error: {ex}")

    agent_t = time.time() - t0

    # ── 打印最终报告 ─────────────────────────────────────────────────
    print_block(f"FINAL REPORT from Agent [{cid}]", report_text, sep=SEP)

    # ── Judge ──────────────────────────────────────────────────────
    judge_input = f"{JUDGE_PROMPT}\n\nAudit Task: {prompt}\n\nGenerated Report:\n{report_text}"

    print(f"\n{SEP3}")
    print(f"  JUDGE PHASE - [{cid}]")
    print(SEP3)

    # 打印 Judge 的完整输入
    print_block("JUDGE PROMPT (full input to Judge LLM)", judge_input, sep=SEP2)

    tj0      = time.time()
    eval_res = {"total": "N/A", "scores": {}, "advice": "parse error"}

    try:
        # [V73.1] 修复 BUG：必须 await 异步函数才能解包
        judge_llm, j_model = await model_manager.get_llm_by_role("planner_heavy")
        res     = await judge_llm.ainvoke(judge_input)
        content = str(res.content)

        # 打印 Judge 原始输出
        print_block("JUDGE RAW RESPONSE", content, sep=SEP2)

        # 解析 JSON
        js = content
        if "```json" in content:
            js = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            js = content.split("```")[1].split("```")[0]
        else:
            s, e = content.find("{"), content.rfind("}")
            if s != -1 and e != -1:
                js = content[s:e+1]
        
        # [V55.0] 健壮 JSON 解析：LLM 常在 advice 字段内输出未转义的双引号
        try:
            eval_res = json.loads(js.strip())
        except json.JSONDecodeError:
            # 尝试修复：提取 scores 和 total，advice 用正则单独抓
            import re as _re
            scores_match = _re.search(r'"scores"\s*:\s*(\{[^}]+\})', js)
            total_match  = _re.search(r'"total"\s*:\s*(\d+)', js)
            advice_match = _re.search(r'"advice"\s*:\s*"(.+)"?\s*\}$', js, _re.DOTALL)
            if scores_match and total_match:
                scores_data = json.loads(scores_match.group(1))
                total_val   = int(total_match.group(1))
                advice_text = advice_match.group(1).replace('"', "'") if advice_match else "parse recovered"
                eval_res = {"scores": scores_data, "total": total_val, "advice": advice_text}
                logger.info(f"[{cid}] Judge JSON recovered: total={total_val}")
            else:
                raise

        j_in  = usage_tracker._estimate_tokens(judge_input)
        j_out = usage_tracker._estimate_tokens(content)
        tracker.case_stats[cid]["judge"] = {"in": j_in, "out": j_out, "calls": 1}
        print(f"\n  [JUDGE TOKEN] in:{j_in}(pred:{PREDICTED['judge']['in']}) "
              f"out:{j_out}(pred:{PREDICTED['judge']['out']})")
    except Exception as ex:
        logger.error(f"[{cid}] Judge parse error: {ex}")

    judge_t = time.time() - tj0
    actual  = tracker.total(cid)
    dev_pct = (actual - pred) / pred * 100

    # ── Case Score Summary ──────────────────────────────────────────
    sc   = eval_res.get("scores", {})
    dims = ["success","recall","precision","faithfulness","relevance","professionalism","interpretability"]

    print(f"\n{SEP}")
    print(f"  CASE RESULT SUMMARY [{cid}]")
    print(SEP)
    labels = ["Success","Recall ","Precision","Faithful","Relevance","Profess.","Interpret"]
    for lab, dim in zip(labels, dims):
        v   = sc.get(dim, 0)
        bar = "#" * int(v) + "-" * (10 - int(v))
        print(f"  {lab:<10}: [{bar}] {v}/10")
    print(f"  {'-'*52}")
    print(f"  Total      : {eval_res.get('total','N/A')} / 70")
    print(f"  Advice     : {str(eval_res.get('advice',''))[:250]}")
    print(f"  Tokens     : predicted={pred:,}  actual={actual:,}  deviation={dev_pct:+.1f}%")
    print(f"  Time       : agent={agent_t:.1f}s  judge={judge_t:.1f}s")
    print(SEP)
    sys.stdout.flush()

    return {
        "id": cid, "tag": case["tag"], "diff": case["diff"],
        "agent_ok": agent_ok, "scores": sc,
        "total_score": eval_res.get("total", "N/A"),
        "advice": eval_res.get("advice", ""),
        "predicted": pred, "actual": actual, "deviation_pct": dev_pct,
        "agent_t": agent_t, "judge_t": judge_t,
        "roles": tracker.case_stats.get(cid, {}),
    }

# ── Summary ───────────────────────────────────────────────────────────
def print_summary(results: list):
    dims   = ["success","recall","precision","faithfulness","relevance","professionalism","interpretability"]
    dim_zh = ["Success","Recall","Precision","Faithful","Relevance","Profess.","Interpret"]
    n_ok   = sum(1 for r in results if r["agent_ok"])

    console.print("\n")
    console.print(Panel.fit(
        f"[bold blue]HSA 7-DIMENSION BENCHMARK FINAL SUMMARY[/]\n[cyan]Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}[/]",
        border_style="blue"
    ))

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Case", width=8)
    table.add_column("Tag", width=20)
    table.add_column("Diff", width=6)
    for zh in dim_zh:
        table.add_column(zh, justify="right")
    table.add_column("Total", justify="right", style="bold yellow")
    table.add_column("Actual/Pred", justify="right", no_wrap=True, width=18)

    tot_pre = tot_act = 0
    dim_sum = {d: 0 for d in dims}

    for r in results:
        sc  = r["scores"]
        row_data = [r["id"], r["tag"], r["diff"]]
        
        for d in dims:
            val = sc.get(d, 0)
            color = "green" if val >= 7 else "yellow" if val >= 5 else "red"
            row_data.append(f"[{color}]{val}[/]")
            
        total = r["total_score"]
        total_color = "bright_green" if (isinstance(total, int) and total >= 50) else "white"
        row_data.append(f"[{total_color}]{total}[/]")
        
        tok_ratio = r['actual'] / r['predicted']
        tok_color = "red" if tok_ratio > 1.2 else "green"
        row_data.append(f"[{tok_color}]{r['actual']:,}[/]/{r['predicted']:,}")
        
        table.add_row(*[str(x) for x in row_data])
        
        tot_pre += r["predicted"]
        tot_act += r["actual"]
        for d in dims:
            dim_sum[d] += sc.get(d, 0)

    console.print(table)

    # 汇总统计
    n = max(len(results), 1)
    console.print(f"\n[bold]Agent Success: [green]{n_ok}[/] / {len(results)}[/]")
    
    # 维度平均分图表
    console.print("\n[bold]Dimension Averages:[/]")
    for d, zh in zip(dims, dim_zh):
        avg_v = dim_sum[d] / n
        bar_len = int(avg_v * 2)
        bar = "█" * bar_len + "░" * (20 - bar_len)
        color = "green" if avg_v >= 7 else "yellow" if avg_v >= 5 else "red"
        console.print(f"  {zh:<14}: [{color}]{bar}[/] {avg_v:>4.1f}/10")

    # 改进建议
    console.print("\n[bold yellow]Improvement Suggestions:[/]")
    for r in results:
        if r.get("advice"):
            console.print(f"  • [bold]{r['id']}[/]: {r['advice']}")

    console.print("\n" + "="*72 + "\n")

# ── Main ──────────────────────────────────────────────────────────────
async def main():
    print(f"\n{SEP}")
    print(f"  HSA Medical Audit Agent - 7-Dimension Benchmark [VERBOSE]")
    print(f"  Time  : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Cases : {len(TEST_CASES)}")
    print(f"  Est.  : {sum(c['pred_tokens'] for c in TEST_CASES):,} tokens")
    print(f"  NOTE  : Full Prompt + Response printed for every node call")
    print(SEP)

    # [V73.0] 裁判模型已移至 run_one 内部动态获取，实现故障秒切
    print(f"  [OK] Judge Strategy: Dynamic Failover Enabled\n")

    # [V74.1] 物理持久化：不再启动时清空黑名单，确保坏掉的模型（如 V3）被持久锁定。
    logger.info("🛡️ [算力治理] 启动时保留历史黑名单状态，防止报废模型复活。")

    # [V174.0] 企业级多 Case 稳定性补强：启动时强制重置黑名单
    from app.infra.usage_tracker import usage_tracker
    usage_tracker.reset_blacklists()
    logger.info("✅ [算力治理] 已强制重置模型黑名单，确保 Benchmark 链路满血启动。")

    # 禁用语义动作缓存以强制执行物理 SQL 取证与工具调用流程
    os.environ["DISABLE_AUDIT_CACHE"] = "true"
    logger.info("⚡ [Benchmark] 已禁用动作链缓存，强制物理 SQL 执行。")

    # [V75.0] 企业级观测激活：确保 Benchmark 过程被全量追踪
    init_observability()
    
    # 注册退出钩子以确保 Trace 数据完整性
    import atexit
    atexit.register(shutdown_observability)

    results = []
    for case in TEST_CASES:
        r = await run_one(case, None) # judge_llm 内部动态生成
        results.append(r)
        await asyncio.sleep(2)

    print_summary(results)

    results_dir = "data/bench_history"
    os.makedirs(results_dir, exist_ok=True)
    
    ts   = datetime.now().strftime("%Y%m%d_%H%M")
    path = f"{results_dir}/bench_7dim_{ts}.json"
    
    # 同时保留一个最新的软链接或副本方便仪表盘读取
    latest_path = "data/bench_7dim_latest.json"
    
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    
    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        
    print(f"  [File] Historical record saved: {path}")
    print(f"  [File] Dashboard data updated: {latest_path}")

if __name__ == "__main__":
    asyncio.run(main())
