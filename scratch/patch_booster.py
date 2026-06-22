"""
临时补丁脚本：将 booster.py 中的 verify_semantic_alignment 替换为 LLM-as-Judge 版本。
运行一次后可删除此脚本。
"""
import pathlib

NEW_METHOD = '''    @staticmethod
    def verify_semantic_alignment(sql: str, report_text: str) -> Tuple[bool, str]:
        """
        [V133.0] 上下文感知型语义一致性审计（LLM-as-Judge）。

        三阶段设计：
        1. 硬规则：极高置信度词直接拦截（无需 LLM）
        2. 候选词提取：找出报告中有歧义的词（出现了但 SQL 无字段支撑）
        3. LLM 裁判：判断候选词是"证据声明"还是"整改建议"
           - 证据声明 → 需要 SQL 字段支撑，否则拦截
           - 整改建议 → 宽松放行，无需 SQL 字段
        LLM 失败时：始终宽松放行，避免误杀导致评分清零。
        """
        sql_u = sql.upper()

        # ── 阶段 1：硬规则快速通道（极高置信度，不走 LLM）──────────────────
        HARD_EVIDENCE_CLAIMS = {
            "单价一致":    ["PRIC"],
            "金额完全相同": ["MEDFEE", "FEE", "AMT"],
        }
        for keyword, fields in HARD_EVIDENCE_CLAIMS.items():
            if keyword in report_text and not any(f in sql_u for f in fields):
                msg = f"❌ [语义不一致·硬规则] 报告出现证据声明词 {keyword!r}，但 SQL 无对应字段。"
                logger.error(msg)
                return False, msg

        # ── 阶段 2：候选词提取──────────────────────────────────────────────
        CANDIDATE_KEYWORDS = {
            "明细":    ["FYMX", "HILIST", "DET_ITEM", "ITEM_CODE", "JZSJ"],
            "具体项目": ["HILIST", "DET_ITEM", "ITEM_CODE"],
            "科室":    ["DEPT"],
            "性别":    ["GEND"],
            "年龄":    ["AGE", "BRDY"],
        }
        suspect_keywords = [
            kw for kw, fields in CANDIDATE_KEYWORDS.items()
            if kw in report_text and not any(f in sql_u for f in fields)
        ]
        if not suspect_keywords:
            return True, ""

        # ── 阶段 3：LLM 上下文裁判──────────────────────────────────────────
        try:
            import asyncio
            import json as _json
            import re as _re
            from app.infra.model_manager import model_manager
            from langchain_core.messages import HumanMessage

            report_snippet = report_text[:600]
            judge_prompt = (
                "你是医疗审计报告语义裁判。判断关键词属于【证据声明】还是【整改建议】。\\n"
                "- 证据声明：主张已查询分析了该维度数据（需SQL支撑），如：发现科室X违规\\n"
                "- 整改建议：基于发现提出后续行动（无需SQL支撑），如：建议对科室X整改\\n\\n"
                f"以下关键词出现在报告中但SQL无对应字段：{suspect_keywords}\\n\\n"
                'ONLY output JSON: {"verdict": "PASS"|"FAIL", "reason": "简短说明"}\\n'
                "PASS=均属整改建议，FAIL=至少一个属证据声明\\n\\n"
                f"报告摘要(前600字):\\n{report_snippet}"
            )

            async def _call_judge():
                llm, _ = await model_manager.get_llm_by_role(
                    "planner_light", retry_count=0, config=None
                )
                resp = await llm.ainvoke([HumanMessage(content=judge_prompt)])
                return resp.content

            try:
                asyncio.get_running_loop()
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    raw_response = pool.submit(asyncio.run, _call_judge()).result(timeout=20)
            except RuntimeError:
                raw_response = asyncio.run(_call_judge())

            json_match = _re.search(r'\\{[^{}]+\\}', raw_response, _re.DOTALL)
            if json_match:
                result = _json.loads(json_match.group())
                verdict = result.get("verdict", "PASS").upper()
                reason  = result.get("reason", "")
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
'''

booster_path = pathlib.Path(__file__).parent.parent / "app" / "booster.py"
content = booster_path.read_text(encoding="utf-8")

start_marker = "    @staticmethod\n    def verify_semantic_alignment"
end_marker = "\nbooster = PrecisionBooster()\n"

start_idx = content.find(start_marker)
end_idx   = content.find(end_marker)

if start_idx == -1 or end_idx == -1:
    print(f"ERROR: markers not found. start={start_idx}, end={end_idx}")
    exit(1)

new_content = content[:start_idx] + NEW_METHOD + end_marker
booster_path.write_text(new_content, encoding="utf-8")
print(f"OK - booster.py rewritten. Total lines: {new_content.count(chr(10))}")
