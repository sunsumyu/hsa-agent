import re
import json
import asyncio
import concurrent.futures
from typing import Tuple
from loguru import logger
from langchain_core.messages import HumanMessage
from app.core.llm_provider import llm_provider

# 阶段 1：硬规则快速通道（极高置信度，不走 LLM）
HARD_EVIDENCE_CLAIMS = {
    "单价一致":    ["PRIC"],
    "金额完全相同": ["MEDFEE", "FEE", "AMT"],
}

# 阶段 2：候选词提取
CANDIDATE_KEYWORDS = {
    "明细":    ["FYMX", "HILIST", "DET_ITEM", "ITEM_CODE", "JZSJ", "B."],
    "具体项目": ["HILIST", "DET_ITEM", "ITEM_CODE", "B."],
    "收费项目": ["HILIST", "ITEM_CODE", "ITEM_NAME", "B."],
    "单价":    ["PRIC", "B."],
    "科室":    ["DEPT"],
    "性别":    ["GEND"],
    "年龄":    ["AGE", "BRDY"],
}


def judge_semantic_alignment(sql: str, report_text: str) -> Tuple[bool, str]:
    """[V133.0 / Matt Pocock Deep Module]
    上下文感知型语义一致性审计裁判引擎（LLM-as-Judge）。
    
    隐藏实现细节：
    - 硬证据断言词与物理 SQL 字段强匹配熔断
    - 潜在涉嫌证据维度候选词扫描
    - 嵌套异步事件循环保护的线程池 LLM 智能裁判调用
    - 整改建议 (PASS) 与虚假证据主张 (FAIL) 区分
    - 裁判服务不可用时的防御性优雅降级
    """
    if not report_text:
        return True, ""

    sql_u = str(sql or "").upper()

    # ── 阶段 1：硬规则快速通道 ──
    for keyword, fields in HARD_EVIDENCE_CLAIMS.items():
        if keyword in report_text and not any(f in sql_u for f in fields):
            msg = f"❌ [语义不一致·硬规则] 报告出现证据声明词 {keyword!r}，但 SQL 无对应字段。"
            logger.error(msg)
            return False, msg

    # ── 阶段 2：候选词提取 ──
    suspect_keywords = [
        kw for kw, fields in CANDIDATE_KEYWORDS.items()
        if kw in report_text and not any(f in sql_u for f in fields)
    ]
    if not suspect_keywords:
        return True, ""

    # ── 阶段 3：LLM 上下文裁判 ──
    try:
        report_snippet = report_text[:600]
        judge_prompt = (
            "你是医疗审计报告语义裁判。判断关键词属于【证据声明】还是【整改建议】。\n"
            "- 证据声明：主张已查询分析了该维度数据（需SQL支撑），如：发现科室X违规\n"
            "- 整改建议：基于发现提出后续行动（无需SQL支撑），如：建议对科室X整改\n\n"
            f"以下关键词出现在报告中但SQL无对应字段：{suspect_keywords}\n\n"
            'ONLY output JSON: {"verdict": "PASS"|"FAIL", "reason": "简短说明"}\n'
            "PASS=均属整改建议，FAIL=至少一个属证据声明\n\n"
            f"报告摘要(前600字):\n{report_snippet}"
        )

        async def _call_judge():
            resp = await llm_provider.chat(
                role="planner_light",
                messages=[HumanMessage(content=judge_prompt)],
                config={"metadata": {"role": "booster_judge", "target": "evidence_validation"}}
            )
            return resp.content

        try:
            asyncio.get_running_loop()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                raw_response = pool.submit(asyncio.run, _call_judge()).result(timeout=20)
        except RuntimeError:
            raw_response = asyncio.run(_call_judge())

        raw_response_str = str(raw_response)
        json_match = re.search(r'\{.*\}', raw_response_str, re.DOTALL)

        if json_match:
            result = json.loads(json_match.group())
            verdict = str(result.get("verdict") or "PASS").upper()
            reason = result.get("reason", "")
            if verdict == "FAIL":
                msg = (f"❌ [LLM语义裁判·拦截] 关键词 {suspect_keywords} "
                       f"被判定为证据声明但缺 SQL 支撑。理由：{reason}")
                logger.error(msg)
                return False, msg
            logger.info(f"✅ [LLM语义裁判·放行] {suspect_keywords} 属整改建议。理由：{reason}")
            return True, ""

    except Exception as e:
        logger.warning(f"⚠️ [LLM语义裁判·降级] 调用失败，宽松放行: {e}")

    return True, ""
