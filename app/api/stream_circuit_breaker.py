"""
app/api/stream_circuit_breaker.py
=================================
[Matt Pocock Deep Module] 算力熔断异常分类自愈与降级文案生成器

核心职责：
1. 识别 403 权限配额不足与耗尽（平台分流识别：阿里云百炼 / 火山引擎）
2. 触发黑名单熔断锁定与后台异步健康探针联动
3. 识别 Token 耗尽 (OUT_OF_TOKEN) 结构化协议透传
4. 识别模型标识符不存在等配置缺失异常
5. 输出标准化 Markdown 告警与自愈提示语
"""

from __future__ import annotations

from typing import Any, List, Optional
from loguru import logger


class StreamCircuitBreaker:
    """流式推演算力熔断与自愈协调器"""

    def classify_and_render(
        self,
        err_msg: str,
        resolved_id: Optional[str],
        usage_tracker: Any,
        model_manager: Any,
        background_tasks: Any,
    ) -> List[str]:
        """
        根据错误类型返回 UI 需要的自愈文案列表，并在需要时触发熔断与后台体检。
        """
        out: List[str] = []

        # 1. Token 耗尽结构化建议原样透传
        if "[[[OUT_OF_TOKEN" in err_msg:
            out.append(f"\n{err_msg}")
            return out

        # 2. 供应商配额 / 403
        if any(kw in err_msg for kw in ("403", "Forbidden")) or "exhausted" in err_msg.lower():
            if resolved_id:
                consumed = 0
                if hasattr(usage_tracker, "stats") and hasattr(usage_tracker.stats, "daily_usage"):
                    consumed = usage_tracker.stats.daily_usage.get(resolved_id, 0)

                is_free_tier = (
                    "FreeTierOnly" in err_msg or "free tier" in err_msg.lower()
                )
                if is_free_tier:
                    platform = (
                        "阿里云百炼 (Bailian)"
                        if any(k in resolved_id for k in ("qwen", "deepseek", "llama"))
                        else "火山引擎 (Volcengine)"
                    )
                    usage_tracker.blacklist_model(
                        resolved_id,
                        reason="FreeTier Limit (Switch Required)",
                        permanent=True,
                    )
                    if background_tasks and hasattr(background_tasks, "add_task"):
                        background_tasks.add_task(model_manager.probe_all_endpoints)

                    out.append(
                        f"\n\n> [!CAUTION]\n"
                        f"> **检测到算力配额冲突 (403)**\n> \n"
                        f"> **平台来源**: {platform}\n"
                        f"> **架构自愈中**: 您的账号目前开启了\"仅限免费额度\"保护。"
                        f"系统已封禁该节点，并同步启动后台探测全场可用性。\n> \n"
                        f"> **📊 资源消耗公开**: 节点 `{resolved_id}` 今日消耗 `{consumed:,}` Tokens。"
                    )
                else:
                    usage_tracker.blacklist_model(
                        resolved_id,
                        reason="Provider Quota Exhausted (403)",
                        permanent=True,
                    )
                    if background_tasks and hasattr(background_tasks, "add_task"):
                        background_tasks.add_task(model_manager.probe_all_endpoints)

                    out.append(
                        f"\n\n> [!WARNING]\n"
                        f"> **算力配额熔断 (403)**\n"
                        f"> 当前模型 `{resolved_id}` 已耗尽。"
                        f"系统已启动后台自检排查，自动锁定健康的存活模型。"
                    )
            return out

        # 3. 模型标识符缺失
        if "Model not found" in err_msg:
            out.append(
                "\n[算力链路异常]: 找不到模型标识符。请检查 llm_providers.json 配置。"
            )
            return out

        # 4. 兜底
        out.append(f"\n[核心审计异常]: 处理中断。详细信息: {err_msg[:50]}...")
        return out


# 全局默认单例
stream_circuit_breaker = StreamCircuitBreaker()
