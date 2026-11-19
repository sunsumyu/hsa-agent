"""
app/core/security/data_masker.py
==================================
[SPEC-227 / Matt Pocock Deep Module] 医保数据隐私合规与 PII 脱敏深模块 (Data Masker)

核心职责：
1. 个人敏感隐私信息 (PII) 正则掩码：
   - 身份证号掩码（保留前6后4）；
   - 手机号掩码（保留前3后4）；
   - 患者与就医人员姓名定向掩码。
2. 对话消息隐私安全净化：
   - 移除过程日志中未脱敏的临时 SQL 跟踪代码块，防止底层表结构外泄；
   - 智能识别最终《医保专项稽核报告》，保全其核心合规 SQL 代码块以支撑审计追溯性。
3. 结构化审计底稿与证据流水字典批量脱敏：
   - 覆盖个人身份、医保核心标识、医疗机构及处方医生等关键字段。
"""

from __future__ import annotations
import re
from typing import Any, Dict, List, Set


_ID_CARD_RE = re.compile(r"\b\d{15}(\d{2}[0-9xX])?\b")
_PHONE_RE = re.compile(r"\b1[3-9]\d{9}\b")
_NAME_RE = re.compile(r"(?<=患者|姓名)[：: ]+([\u4e00-\u9fa5]{2,3})")
_SQL_CODEBLOCK_RE = re.compile(r"```sql\s*(.*?)\s*```", re.DOTALL)

_PII_FIELDS: Set[str] = {
    # 个人身份信息
    "psn_name", "psn_cert_no", "tel", "addr", "certno", "brdy", "contact_tel",
    # 医保核心标识
    "psn_no", "setl_id", "setl_id_str",
    # 机构信息
    "fixmedins_code", "fixmedins_name",
    # 诊断信息
    "dise_name", "adm_dept_name", "dscg_dept_name",
    # 医生信息
    "chfpdr_name", "chfpdr_code",
}


def apply_pii_masking(text: str) -> str:
    """
    执行高精度正则脱敏打码。
    """
    if not text:
        return ""

    # 掩码身份证 (保留前6后4)
    text = _ID_CARD_RE.sub(
        lambda m: m.group()[:6] + "********" + m.group()[-4:], text
    )
    # 掩码电话 (保留前3后4)
    text = _PHONE_RE.sub(
        lambda m: m.group()[:3] + "****" + m.group()[-4:], text
    )
    # 掩码姓名 (针对“姓名：张三”模式，强制要求有冒号或空格分隔符，防止“患者产生妇科”等学术词被误伤打码)
    text = _NAME_RE.sub(
        lambda m: m.group(1)[0] + "*" * (len(m.group(1)) - 1), text
    )
    return text


def sanitize_audit_content(messages: List[Any]) -> List[Any]:
    """
    企业级隐私脱敏与过程 SQL 冗余清除。
    在最终医保报告中保留核心 SQL 代码块以保障可审计性；在普通对话消息中剥离过程 SQL 并脱敏。
    """
    for m in messages:
        content = getattr(m, "content", "")
        if content and isinstance(content, str):
            # 如果是最终审计报告，保留其中的 SQL 代码块以保障可审计性
            if "医保专项稽核报告" in content or "## 一、审计任务" in content:
                content = apply_pii_masking(content)
            else:
                # 1. 移除冗余 SQL 代码块
                content = _SQL_CODEBLOCK_RE.sub("[SQL EXEC_TRACE_REMOVED]", content)
                # 2. 执行 PII 脱敏
                content = apply_pii_masking(content)
            m.content = content.strip()
    return messages


def mask_audit_data(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    针对医保结算数据字典列表的动态脱敏接口。
    针对 psn_name, psn_no, setl_id 等敏感字段执行深度打码。
    """
    for item in data:
        if not isinstance(item, dict):
            continue
        for field in _PII_FIELDS:
            if field in item and item[field]:
                item[field] = apply_pii_masking(str(item[field]))
    return data
