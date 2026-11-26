"""
Tool Protocol & Pairing Guard Deep Module.
Adheres to Matt Pocock's Deep Module design: encapsulates LLM tool call protocol pairing,
orphan tool message pruning, past turn tool message compaction, and audit evidence摘要 compression
behind clean, functional interfaces.
"""
from typing import List, Any
import json
import re
from loguru import logger


def compress_tool_content(messages: List[Any], max_len: int = 2000) -> List[Any]:
    """
    智能 ToolMessage 摘要压缩器（审计证据摘要模式）。
    提取核心审计指标（记录数、关键金额字段、状态）生成审计摘要，
    并将完整原始内容存入 ToolMessage 的 additional_kwargs['_raw_content']。
    """
    compressed = []
    for m in messages:
        msg_type = getattr(m, "type", m.__class__.__name__).lower()
        if msg_type == "tool":
            content = str(getattr(m, "content", "") or "")
            if len(content) > 400:
                summary_parts = []

                # 尝试解析结构化结果
                try:
                    data = json.loads(content)
                    if isinstance(data, dict):
                        status = data.get("status", "")
                        msg = data.get("message", "")
                        records = data.get("records_sample", [])
                        if status:
                            summary_parts.append(f"[{status}]")
                        if msg:
                            summary_parts.append(msg[:60])
                        if isinstance(records, list) and records:
                            key_sample = ", ".join(list(records[0].keys())[:5])
                            summary_parts.append(f"核心字段: {key_sample}")
                except (ValueError, TypeError, AttributeError) as exc:
                    logger.debug(f"[ToolProtocolGuard] JSON digest parse skipped: {exc}")

                # fallback：正则提取关键数字
                if not summary_parts:
                    nums = re.findall(r'\d+(?:\.\d+)?', content[:500])
                    row_match = re.search(r'(\d+)\s*(?:条|rows?|records?)', content)
                    if row_match:
                        summary_parts.append(f"{row_match.group(1)}条记录")
                    elif nums:
                        summary_parts.append(f"含数值: {', '.join(nums[:5])}")
                    summary_parts.append(content[:80])

                audit_digest = "📋 [工具执行摘要] " + " | ".join(summary_parts)

                try:
                    from langchain_core.messages import ToolMessage as _TM
                    new_msg = _TM(
                        content=audit_digest[:300],
                        tool_call_id=getattr(m, "tool_call_id", ""),
                        additional_kwargs={"_raw_content": content[:3000]}
                    )
                    compressed.append(new_msg)
                    continue
                except ImportError as exc:
                    logger.debug(f"[ToolProtocolGuard] ToolMessage import fallback: {exc}")
        compressed.append(m)
    return compressed


def ensure_tool_pairing(messages: List[Any]) -> List[Any]:
    """
    配对完整性校验：确保每条 ToolMessage 前方存在对应的 AIMessage(tool_calls)。
    防止触发百炼/OpenAI 400 InvalidParameter 错误。
    """
    # Pass 1: 收集所有 AI 消息声明的 tool_call_id → set
    declared_ids: set = set()
    for m in messages:
        msg_type = getattr(m, "type", m.__class__.__name__).lower()
        if msg_type in ("ai", "aimessagechunk", "assistant"):
            for tc in getattr(m, "tool_calls", []) or []:
                tid = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                if tid:
                    declared_ids.add(tid)

    # Pass 2: 收集实际存在的 ToolMessage 的 tool_call_id
    present_tool_ids: set = set()
    result = []
    for m in messages:
        msg_type = getattr(m, "type", m.__class__.__name__).lower()
        if msg_type in ("tool", "toolmessagechunk", "toolmessage"):
            tid = getattr(m, "tool_call_id", None)
            if tid and tid not in declared_ids:
                # 孤儿 ToolMessage：前方无对应 AI tool_calls → 丢弃
                continue
            if tid:
                present_tool_ids.add(tid)
        result.append(m)

    # Pass 3: 修正 AI 消息中的 tool_calls 声明并清理空壳 AI
    final = []
    for m in result:
        msg_type = getattr(m, "type", m.__class__.__name__).lower()
        if msg_type in ("ai", "aimessagechunk", "assistant"):
            tc_list = getattr(m, "tool_calls", []) or []
            if tc_list:
                # 仅保留对应的 ToolMessage 实际存在的 tool_calls
                valid_tc = []
                for tc in tc_list:
                    tid = tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)
                    if tid in present_tool_ids:
                        valid_tc.append(tc)

                # 如果有 tool_calls 被丢弃（例如在超限裁剪中被裁掉），重新构造全新、干净的 AIMessage
                if len(valid_tc) != len(tc_list):
                    from langchain_core.messages import AIMessage as _AM
                    new_additional_kwargs = m.additional_kwargs.copy() if hasattr(m, "additional_kwargs") and m.additional_kwargs else {}
                    if "tool_calls" in new_additional_kwargs:
                        new_additional_kwargs.pop("tool_calls")

                    new_kwargs = {
                        "content": m.content,
                        "additional_kwargs": new_additional_kwargs,
                        "response_metadata": m.response_metadata.copy() if hasattr(m, "response_metadata") and m.response_metadata else {},
                        "tool_calls": valid_tc
                    }
                    if hasattr(m, "id"):
                        new_kwargs["id"] = m.id

                    m = _AM(**new_kwargs)

                content = str(getattr(m, "content", "") or "").strip()
                if not getattr(m, "tool_calls", []) and not content:
                    # 空壳 AI：只有 tool_calls 但无任何响应也无文本内容 → 丢弃
                    continue
        final.append(m)

    return final


def prune_past_turn_tools(messages: List[Any]) -> List[Any]:
    """
    [状态防腐与结构治理]
    以最后一条 HumanMessage 为活跃轮次边界：
    - 前方（已完结历史轮次）：剥离历史内部 ToolMessage 与中间过渡工具调用 AIMessage，
      只保留干净纯正的 Human -> AI 对话对，根除历史 ToolMessage 泄漏与 400 校验隐患。
    - 后方（当前活跃执行轮次）：100% 完整保留工具调用与执行反馈，保障当前轮次正常流转。
    """
    if not messages or len(messages) <= 1:
        return messages

    # 寻找最后一条 HumanMessage 的位置
    last_human_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        msg_type = getattr(m, "type", m.__class__.__name__).lower()
        if msg_type in ("human", "user"):
            last_human_idx = i
            break

    # 若无 HumanMessage 或最后一条 HumanMessage 位于首位（单轮进行中），无需修剪历史
    if last_human_idx <= 0:
        return messages

    past_msgs = messages[:last_human_idx]
    active_msgs = messages[last_human_idx:]

    clean_past = []
    for i, m in enumerate(past_msgs):
        msg_type = getattr(m, "type", m.__class__.__name__).lower()
        # 丢弃历史内部 ToolMessage
        if msg_type in ("tool", "toolmessage", "toolmessagechunk"):
            continue

        # 针对历史 AIMessage：如果该消息含有 tool_calls，且在其后存在最终结论 AIMessage，则剔除过渡性工具调用
        if msg_type in ("ai", "assistant", "aimessagechunk", "aimessage"):
            tc = getattr(m, "tool_calls", None) or (getattr(m, "additional_kwargs", {}) or {}).get("tool_calls", [])
            if tc:
                # 检查后续是否还有其它 AIMessage
                has_subsequent_ai = any(
                    getattr(next_m, "type", next_m.__class__.__name__).lower() in ("ai", "assistant", "aimessagechunk", "aimessage")
                    for next_m in past_msgs[i + 1:]
                )
                if has_subsequent_ai:
                    continue

        clean_past.append(m)

    return clean_past + active_msgs
