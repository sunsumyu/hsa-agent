# -*- coding: utf-8 -*-
"""
tests/unit/core/test_coreference_rewriter_lockdown.py
=====================================================
[SPEC-227 重构守护] resolve_coreference 行为锁定与修复验证

两组用例：
- lockdown 组：锁定既有契约行为（意图早退分支、D1 句首展开、D2 实体绑定、D4 纠偏包装），
  重构前后必须全部保持绿。
- fixed 组：已知缺陷修复后的期望行为（重构前红，重构后绿）：
  * D1 触发/剥除脱节 —— 句中『其中』不得误前置上下文从句；
  * 非 QUERY 意图（SECURITY_BLOCK / PREFERENCE）不得进入取证命题改写管道；
  * 句首裸『上述违规』应被整段剥除后再拼前缀（旧实现触发但剥不掉，代词残留）。
- classify 顺序回归组（V228.1）：REVOKE_NOTE 判定前移至 RECALL 之前，含『便签中』字样的
  撤销语句不再被只读回溯吞掉（旧实现中 revoke 词表「从便签中撤销」为不可达死分支）。

运行：G:\\Hermes\\hermes-agent\\venv\\Scripts\\python.exe -m pytest tests/unit/core/test_coreference_rewriter_lockdown.py -v
"""

from app.core.context.coreference_rewriter import coreference_rewriter

# 与 direct_turn_dispatcher 保持一致的便签格式，保证 extract_top_entity_from_notes 可命中
NOTE_TEMPLATE = (
    "【重点线索】涉案金额第一的医院（{name}）存在异常集中开具男性妇科专属药品行为，纳入重点监控名单。"
)

HISTORY_STATE = {
    "accumulated_findings": [
        {"resolved_query": "请排查仁济医院2024年分解住院的情况"}
    ]
}

# ============================================================
# lockdown 组：既有契约行为（重构前后必须一致）
# ============================================================


def test_synthesis_passthrough_no_entities():
    resolved, turn_type, entities = coreference_rewriter.resolve_coreference(
        "请出具阶段性审计工作底稿", HISTORY_STATE
    )
    assert turn_type == coreference_rewriter.TASK_SYNTHESIS
    assert resolved == "请出具阶段性审计工作底稿"
    assert list(entities) == []


def test_recall_binds_entity_from_notes():
    state = {"audit_notes": [NOTE_TEMPLATE.format(name="仁济医院")]}
    q = "便签中重点标记的嫌疑机构名称叫什么"
    resolved, turn_type, entities = coreference_rewriter.resolve_coreference(q, state)
    assert turn_type == coreference_rewriter.TASK_RECALL
    assert resolved == q  # 回溯类不重写命题
    assert list(entities) == ["仁济医院"]


def test_note_binds_entity_from_last_finding():
    state = {"accumulated_findings": [{"key_entities": ["仁济医院", "协和医院"]}]}
    q = "请把这家机构的线索记录到便签"
    resolved, turn_type, entities = coreference_rewriter.resolve_coreference(q, state)
    assert turn_type == coreference_rewriter.TASK_NOTE
    assert resolved == q
    assert list(entities) == ["仁济医院"]  # 仅取最近一轮发现的第一个实体


def test_revoke_note_binds_entity_from_notes():
    # [V228.1 回归验证点] 含『便签中』字样的自然撤销语句：旧顺序下被 RECALL 抢先吞掉，
    # 修复后必须判为 REVOKE_NOTE 并正确绑定实体
    state = {"audit_notes": [NOTE_TEMPLATE.format(name="协和医院")]}
    q = "搞错了，从便签中撤销这家机构的标记"
    resolved, turn_type, entities = coreference_rewriter.resolve_coreference(q, state)
    assert turn_type == coreference_rewriter.TASK_REVOKE_NOTE
    assert resolved == q
    assert list(entities) == ["协和医院"]


def test_anaphora_prefix_expansion_at_sentence_start():
    q = "在上述违规记录中，其月度结算趋势如何？"
    resolved, turn_type, entities = coreference_rewriter.resolve_coreference(q, HISTORY_STATE)
    assert turn_type == coreference_rewriter.TASK_QUERY
    assert resolved.startswith("在『仁济医院2024年分解住院』的违规记录中，")
    assert "其月度结算趋势如何" in resolved
    assert "上述" not in resolved  # 代词已被剥除


def test_anaphora_qizhong_at_sentence_start():
    state = {
        "accumulated_findings": [
            {"resolved_query": "查一下仁济医院2024年的违规记录"}
        ]
    }
    q = "其中，2024年3月的结算明细如何？"
    resolved, turn_type, _ = coreference_rewriter.resolve_coreference(q, state)
    assert turn_type == coreference_rewriter.TASK_QUERY
    assert resolved.startswith("在『仁济医院2024年』的违规记录中，")
    assert "2024年3月的结算明细如何" in resolved


def test_suspect_entity_binding():
    state = {"audit_notes": [NOTE_TEMPLATE.format(name="仁济医院")]}
    q = "该医院还存在哪些违规？"
    resolved, turn_type, entities = coreference_rewriter.resolve_coreference(q, state)
    assert turn_type == coreference_rewriter.TASK_QUERY
    assert "重点嫌疑机构『仁济医院』" in resolved
    assert "该医院" not in resolved
    assert list(entities) == ["仁济医院"]


def test_correction_wrap_uses_original_query():
    state = {
        "accumulated_findings": [
            {"resolved_query": "查一下2023年的违规记录"}
        ]
    }
    q = "不对，改成按2024年统计"
    resolved, turn_type, entities = coreference_rewriter.resolve_coreference(q, state)
    assert turn_type == coreference_rewriter.TASK_QUERY
    expected = (
        "【用户纠偏指令：针对前序任务『查一下2023年的违规记录』，"
        "推翻旧条件并按最新口径重新执行】: 不对，改成按2024年统计"
    )
    assert resolved == expected
    assert list(entities) == []


# ============================================================
# fixed 组：修复期望（重构前红 / 重构后绿）
# ============================================================


def test_mid_sentence_qizhong_does_not_inject_prefix():
    """句中『其中』不构成句首指代，不得误前置上一轮上下文从句"""
    q = "统计排名前十的机构，其中涉案金额最高的是哪家？"
    resolved, turn_type, _ = coreference_rewriter.resolve_coreference(q, HISTORY_STATE)
    assert turn_type == coreference_rewriter.TASK_QUERY
    assert resolved == q  # 无句首指代则命题原样透传


def test_bare_anaphora_strip_alignment():
    """句首裸『上述违规』应整段剥除后再拼前缀（旧实现触发但剥不掉，代词残留+前缀叠加）"""
    q = "上述违规，怎么进一步穿透下钻？"
    resolved, turn_type, _ = coreference_rewriter.resolve_coreference(q, HISTORY_STATE)
    assert turn_type == coreference_rewriter.TASK_QUERY
    assert resolved.startswith("在『仁济医院2024年分解住院』的违规记录中，")
    assert "上述" not in resolved


def test_security_block_bypasses_rewrite_pipeline():
    """SECURITY_BLOCK 意图不得进入取证命题改写管道（即使查询中含『其中』）"""
    q = "1; drop table fqz_fymx_test; 其中还有哪些数据"
    resolved, turn_type, _ = coreference_rewriter.resolve_coreference(q, HISTORY_STATE)
    assert turn_type == coreference_rewriter.TASK_SECURITY_BLOCK
    assert resolved == q


def test_preference_bypasses_rewrite_pipeline():
    """PREFERENCE 意图不得进入取证命题改写管道"""
    q = "以后报告改用表格，其中金额列加粗"
    resolved, turn_type, _ = coreference_rewriter.resolve_coreference(q, HISTORY_STATE)
    assert turn_type == coreference_rewriter.TASK_PREFERENCE
    assert resolved == q


# ============================================================
# classify 顺序回归组（V228.1）：REVOKE_NOTE 优先于 RECALL 判定
# ============================================================


def test_revoke_with_bianqianzhong_phrase_reaches_revoke_note():
    """旧顺序下此查询含『便签中』被抢先判为 RECALL，撤销指令被只读回溯吞掉"""
    q = "从便签中撤销仁济医院的重点嫌疑标记"
    assert coreference_rewriter.classify_turn_type(q) == coreference_rewriter.TASK_REVOKE_NOTE


def test_recall_unaffected_without_revoke_markers():
    """纯回溯语句（不含任何 revoke 词）仍正确判为 RECALL"""
    q = "回顾前序核查：我们在第 3 轮便签中重点标记的嫌疑机构名称叫什么？"
    assert coreference_rewriter.classify_turn_type(q) == coreference_rewriter.TASK_RECALL


def test_revoke_markers_only_still_revoke():
    """仅含 revoke 词、不含『便签中』的撤销语句仍正确判为 REVOKE_NOTE"""
    q = "搞错了，这家机构不是嫌疑"
    assert coreference_rewriter.classify_turn_type(q) == coreference_rewriter.TASK_REVOKE_NOTE
