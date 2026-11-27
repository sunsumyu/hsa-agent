"""
tests/unit/test_memory_conflict_resolution.py
=============================================
真实业务与口语冲突测试套件 (Real-World Colloquial & Semantic Conflict Suite)

涵盖真实人类在多轮会话中的典型纠偏、反悔、撤回与业务冲突：
1. 口语反悔与阈值推翻 (Colloquial Threshold Revision: "不对，五千定太高了，改成两千")
2. 实体认错与紧急撤销 (Colloquial Note Revocation: "搞错了，它是公立三甲别查它了，撤回便签")
3. 时间跨度反转并表 (Colloquial Scope Expansion: "算了，2024太单薄，把2023也并进来算")
4. 数值口径突变 (Numerical Threshold Mutation: 3000 -> 1000)
5. 多跳时序链式反转 (Multi-Hop Flip-Flop: 表格 -> 纯文字 -> 重新启用表格)
6. 集合清单动态剔除 (Scope Invalidation: 急救药移出重点监控黑名单)
7. 特例下级覆盖通则上级 (Specificity Hierarchy: 涉案重点机构取消小额免检)
8. 时效区间自然过期失效 (Time-Bounded Scope: 历史住院豁免期满，不污染当前排查)
"""

import pytest
import datetime
from app.core.memory.conflict_arbiter import (
    MemoryConflictArbiter,
    memory_conflict_arbiter,
)
from app.core.context.coreference_rewriter import coreference_rewriter
from app.core.history_filter import history_context_filter
from app.core.query_classifier import QueryType


class TestRealWorldColloquialConflicts:
    """测试真实多轮对话中用户的口语纠偏、反悔与指令推翻"""

    def test_user_colloquial_threshold_override(self):
        """
        真实冲突 1: 口语反悔与阈值推翻
        Turn 1: "先帮我拉一下今年报销超过五千的大额名单看看"
        Turn 2 (用户说): "不对，五千定太高了根本没几个人，赶紧改成两千以上的重新查！"
        验证：CoreferenceRewriter 准确识别口语纠偏反悔，将前序任务基线与最新 2000 元口径合成为确切命题。
        """
        mock_state = {
            "accumulated_findings": [
                {
                    "turn": 1,
                    "user_query": "先帮我拉一下今年报销超过五千的大额名单看看",
                    "resolved_query": "查2024年就诊费用明细中报销金额大于5000元的大额结算名单",
                    "key_entities": ["大额结算名单"],
                    "affected_count": 2,
                    "involved_amount": 12800.0
                }
            ]
        }

        user_turn2 = "不对，五千定太高了根本没几个人，赶紧改成两千以上的重新查！"
        resolved, turn_type, _ = coreference_rewriter.resolve_coreference(user_turn2, mock_state)

        assert turn_type == coreference_rewriter.TASK_QUERY
        assert "推翻旧条件并按最新口径重新执行" in resolved
        assert "两千" in resolved
        assert "报销金额大于5000元" in resolved  # 继承了前序核查主题

    async def test_user_colloquial_lifestyle_chitchat(self):
        """
        [Hermes / DeepAgents 范式] 真实场景：用户日常生活闲聊与生活偏好
        用户说: "我喜欢吃鸡肉"
        验证：
        1. 意图分类器识别为 TASK_CHITCHAT (非业务取证任务)；
        2. aligner_node 直通返回亲切、专业的人设对话，并更新用户画像；
        3. 坚决不进入 Planner/SQL 流程，绝对严禁生成具有法律条款的《医保专项稽核报告》。
        """
        from app.orchestration.agent_graph import aligner_node
        from langchain_core.messages import HumanMessage

        user_input = "我喜欢吃鸡肉"
        turn_type = coreference_rewriter.classify_turn_type(user_input)
        assert turn_type == coreference_rewriter.TASK_CHITCHAT

        mock_state = {
            "messages": [HumanMessage(content=user_input)],
            "metadata": {}
        }
        res = await aligner_node(mock_state, config={})
        
        assert res["turn_type"] == coreference_rewriter.TASK_CHITCHAT
        assert res["metadata"]["fast_route_id"] == "CHITCHAT_DIRECT"
        assert res["metadata"]["synthesis_done"] is True
        
        reply = res["messages"][0].content
        # 验证回复具备温度并引导回医保业务
        assert any(w in reply for w in ["鸡肉", "美味", "健康"])
        assert "医保智能稽核助手" in reply
        # 绝不能出现荒谬的医保公文报告
        assert "医保专项稽核报告" not in reply
        assert "国务院令第735号" not in reply

    async def test_user_colloquial_preference_setting(self):
        """
        [Hermes / DeepAgents 范式] 真实场景：用户声明操作格式偏好
        用户说: "我喜欢用表格排版，不要用纯文字"
        验证：
        1. 识别为 TASK_PREFERENCE 偏好配置；
        2. 自动沉淀至便签簿与交互偏好中；
        3. 给出明确的设置生效确认，不跑无谓 SQL。
        """
        from app.orchestration.agent_graph import aligner_node
        from langchain_core.messages import HumanMessage

        user_input = "我喜欢用表格排版，不要用纯文字"
        turn_type = coreference_rewriter.classify_turn_type(user_input)
        assert turn_type == coreference_rewriter.TASK_PREFERENCE

        mock_state = {
            "messages": [HumanMessage(content=user_input)],
            "metadata": {}
        }
        res = await aligner_node(mock_state, config={})
        
        assert res["turn_type"] == coreference_rewriter.TASK_PREFERENCE
        assert res["metadata"]["fast_route_id"] == "PREFERENCE_DIRECT"
        reply = res["messages"][0].content
        assert "已为您更新系统偏好设置" in reply
        assert any("表格" in n for n in res["audit_notes"])

    async def test_user_colloquial_note_revocation(self):
        """
        真实冲突 2: 实体认错与紧急撤销
        Turn 1: 用户将某医院记入便签
        Turn 2 (用户说): "搞错了搞错了！刚核实它是公立三甲，别查它了，撤销便签！"
        验证：
        1. 准确将真实口语分类为 TASK_REVOKE_NOTE；
        2. 提取出需要解绑撤销的目标实体；
        3. 在 Agent 流程中直接完成解绑响应，0ms 熔断，绝不调用无谓 SQL。
        """
        mock_state = {
            "audit_notes": [
                "【重点线索】涉案金额第一的医院（六盘水市水城县九龙村卫生室）存在异常集中开具男性妇科专属药品行为，纳入重点监控名单。"
            ],
            "metadata": {}
        }

        user_turn = "搞错了搞错了！刚核实它是公立三甲，别查它了，撤销便签！"
        
        # 1. 分类与实体提取验证
        classified_type = coreference_rewriter.classify_turn_type(user_turn)
        assert classified_type == coreference_rewriter.TASK_REVOKE_NOTE

        _, _, entities = coreference_rewriter.resolve_coreference(user_turn, mock_state)
        assert "六盘水市水城县九龙村卫生室" in entities

        # 2. 状态机就地响应验证 (调用 aligner_node)
        from app.orchestration.agent_graph import aligner_node
        from langchain_core.messages import HumanMessage
        res = await aligner_node({"messages": [HumanMessage(content=user_turn)], **mock_state}, config={})
        
        assert res["turn_type"] == coreference_rewriter.TASK_REVOKE_NOTE
        assert "REVOKE_NOTE_DIRECT" in res["metadata"]["fast_route_id"]
        assert "撤回并解除对『六盘水市水城县九龙村卫生室』的重点嫌疑标记" in res["messages"][0].content
        # 验证该机构已被从活跃便签名单中移除
        assert not any("纳入重点监控名单" in n and "九龙村卫生室" in n for n in res["audit_notes"])

    def test_user_colloquial_temporal_expansion(self):
        """
        真实冲突 3: 自我打脸与时间跨度反转
        Turn 1: "只看2024年的数据排查"
        Turn 2 (用户说): "算了，2024年数据太单薄了看不出团伙，把2023年的也一块并进来算！"
        验证：识别“算了/并进来/一起算”等口语标记，锁定增量时间范围。
        """
        mock_state = {
            "accumulated_findings": [
                {
                    "turn": 1,
                    "user_query": "只看2024年的数据排查男性妇科专属用药",
                    "resolved_query": "在2024年就诊费用明细中排查男性结算妇科专属用药",
                    "key_entities": ["妇科专属用药"],
                }
            ]
        }

        user_turn = "算了，2024年数据太单薄了看不出团伙，把2023年的也一块并进来算！"
        resolved, turn_type, _ = coreference_rewriter.resolve_coreference(user_turn, mock_state)

        assert turn_type == coreference_rewriter.TASK_QUERY
        assert "推翻旧条件并按最新口径重新执行" in resolved
        assert "2023" in resolved


class TestDomainMemoryConflictArbiter:
    """测试审计知识库与便签簿中的深度语义事实冲突"""

    def test_case_1_numerical_threshold_mutation_conflict(self):
        """
        Case 1: 数值/口径突变冲突 (Threshold Mutation: 3000 -> 1000)
        """
        arbiter = MemoryConflictArbiter()
        note_t1 = "## 📌 [AUDIT_NOTE] - 2026-06-01 10:00:00\n对定点药店大额购药排查：单笔结算金额阈值设定为 >= 3000 元，低于3000元视为常规用药不予预警。"
        note_t2 = "## 📌 [AUDIT_NOTE] - 2026-10-15 10:00:00\n根据最新局端稽核通知，定点药店大额排查阈值下调为 >= 1000 元，收紧监管尺度。"

        raw_notes = f"{note_t1}\n\n---\n\n{note_t2}"
        result = arbiter.resolve_note_conflicts(raw_notes, strip_superseded=True)

        assert "1000" in result
        assert "3000" not in result

    def test_case_2_multihop_flip_flop_chain_resolution(self):
        """
        Case 2: 多跳链式时序反转 (Multi-Hop Flip-Flop Chain: 表格 -> 纯文字 -> 重新启用表格)
        """
        arbiter = MemoryConflictArbiter()
        note_day1 = "## 📌 [USER_PREFERENCE] - 2026-10-01 10:00:00\n输出审计报告时，必须使用 Markdown 表格排版，不要用纯文字。"
        note_day3 = "## 📌 [USER_PREFERENCE] - 2026-10-03 10:00:00\n表格在移动端太宽，取消表格，全部改用纯文字无序列表罗列要点。"
        note_day7 = "## 📌 [USER_PREFERENCE] - 2026-10-07 10:00:00\n根据领导汇报要求，重新启用 Markdown 表格排版，恢复格式。"

        raw_notes = f"{note_day1}\n\n---\n\n{note_day3}\n\n---\n\n{note_day7}"
        result = arbiter.resolve_note_conflicts(raw_notes, strip_superseded=True)

        assert "重新启用 Markdown 表格排版" in result
        assert "取消表格" not in result
        assert "2026-10-07" in result

    def test_case_3_set_inclusion_and_scope_exclusion_conflict(self):
        """
        Case 3: 集合包含与范围移出冲突 (黄体酮注射液移出重点监控清单)
        """
        arbiter = MemoryConflictArbiter()
        note_t1 = "## 📌 [AUDIT_NOTE] - 2026-10-01 10:00:00\n药品专项核查清单：黄体酮注射液列为本次专项核查重点监控范围。"
        note_t2 = "## 📌 [AUDIT_NOTE] - 2026-10-15 10:00:00\n经临床专家组复核，黄体酮注射液属于保胎常规急救药，移出本次专项核查黑名单，免于核查。"

        raw_notes = f"{note_t1}\n\n---\n\n{note_t2}"
        result = arbiter.resolve_note_conflicts(raw_notes, strip_superseded=True)

        assert "移出本次专项核查黑名单" in result
        assert "重点监控范围" not in result

    def test_case_4_specificity_hierarchy_exception_overrides_general(self):
        """
        Case 4: 特例下级覆盖通则上级冲突 (涉案九龙村卫生室取消小额免检)
        """
        arbiter = MemoryConflictArbiter()
        note_general = "## 📌 [AUDIT_NOTE] - 2026-10-01 10:00:00\n宏观通则：所有一级基层医疗机构的门诊月度统计，单次结算小于 500 元直接划入小额免检豁免池。"
        note_specific = "## 📌 [AUDIT_NOTE] - 2026-10-10 10:00:00\n微观特例：六盘水市水城县九龙村卫生室因存在重大团伙套现嫌疑，取消所有小额免检特权，强制执行 100% 全量穿透！"

        raw_notes = f"{note_general}\n\n---\n\n{note_specific}"
        result = arbiter.resolve_note_conflicts(raw_notes, strip_superseded=True)

        assert "取消所有小额免检特权" in result
        assert "直接划入小额免检豁免池" not in result

    def test_case_5_time_bounded_scope_and_expiration_invalidation(self):
        """
        Case 5: 时效区间自然过期冲突 (2024 住院豁免期满，不污染 2026 年排查)
        """
        arbiter = MemoryConflictArbiter()
        note_expired = "## 📌 [AUDIT_NOTE] - 2024-03-01 10:00:00\n参保人张三在 2024-03-01 至 2024-03-15 期间处于重症住院期，期间产生的门诊费用纳入急诊一体化合规豁免结算。"
        note_current = "## 📌 [AUDIT_NOTE] - 2026-10-15 10:00:00\n当前核查发现张三在门诊反复结算高档耗材，列为异常嫌疑对象。"

        raw_notes = f"{note_expired}\n\n---\n\n{note_current}"
        result = arbiter.resolve_note_conflicts(raw_notes, strip_superseded=True)

        assert "列为异常嫌疑对象" in result
        assert "合规豁免结算" not in result

    def test_history_context_filter_integration(self):
        """
        端到端集成测试：HistoryContextFilter 在真实场景下调用冲突仲裁器过滤旧结论
        """
        note_1 = "## 📌 [AUDIT_NOTE] - 2026-10-10 12:00:00\n机构定性：威宁县朝阳卫生室各项指标正常，评定为合规单位。"
        note_2 = "## 📌 [AUDIT_NOTE] - 2026-10-15 12:00:00\n机构定性：威宁县朝阳卫生室核查存在大额异常，判定为违规嫌疑单位。"

        raw_notes = f"{note_1}\n\n---\n\n{note_2}"
        filtered = history_context_filter.filter_relevant_notes(
            notes_raw=raw_notes,
            current_query="核查违规单位",
            query_type=QueryType.THRESHOLD_FILTER
        )

        assert "违规嫌疑单位" in filtered
        assert "评定为合规单位" not in filtered
