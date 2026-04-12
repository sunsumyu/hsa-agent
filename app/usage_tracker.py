import json
import os
from datetime import datetime
from loguru import logger

class UsageTracker:
    def __init__(self, stats_path="data/usage_stats.json", config_path="app/llm_providers.json"):
        self.stats_path = stats_path
        self.config_path = config_path
        self._ensure_dir()
        self.stats = self._load_stats()
        self.model_configs = self._load_model_configs()

    def _ensure_dir(self):
        os.makedirs(os.path.dirname(self.stats_path), exist_ok=True)

    def _load_model_configs(self):
        """加载模型成本与限额配置"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"加载模型配置失败: {e}")
        return {}

    def _load_stats(self):
        if os.path.exists(self.stats_path):
            try:
                with open(self.stats_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    today = datetime.now().strftime("%Y-%m-%d")
                    if data.get("today") != today:
                        logger.info(f"新的一天 ({today})，重置每日用量计数器。")
                        data["today"] = today
                        data["daily_usage"] = {}
                    return data
            except Exception as e:
                logger.error(f"加载用量统计失败: {e}")
        
        return {
            "today": datetime.now().strftime("%Y-%m-%d"),
            "daily_usage": {},
            "total_usage": {}
        }

    def _save_stats(self):
        try:
            with open(self.stats_path, 'w', encoding='utf-8') as f:
                json.dump(self.stats, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存用量统计失败: {e}")

    def record_usage(self, model_id, input_tokens, output_tokens):
        total = input_tokens + output_tokens
        
        # 更新每日用量
        daily = self.stats.setdefault("daily_usage", {})
        daily[model_id] = daily.get(model_id, 0) + total
        
        # 更新累计用量
        lifetime = self.stats.setdefault("total_usage", {})
        lifetime[model_id] = lifetime.get(model_id, 0) + total
        
        self._save_stats()
        
        # 计算当前成本 (虚拟)
        cfg = self.model_configs.get(model_id, {})
        i_cost = (input_tokens / 1000) * cfg.get("input_cost_1k", 0)
        o_cost = (output_tokens / 1000) * cfg.get("output_cost_1k", 0)
        total_cost = i_cost + o_cost
        
        logger.info(f"Token 占用统计: {model_id} +{total} (计费: ${total_cost:.4f})")

    def check_limit(self, model_id):
        """
        检查特定模型的用量限额。
        返回 (is_safe, current, limit, message)
        """
        # 实时重新加载配置以确保持久化修改生效
        self.model_configs = self._load_model_configs()
        
        current_usage = self.stats.get("daily_usage", {}).get(model_id, 0)
        model_cfg = self.model_configs.get(model_id, {})
        
        # 获取该模型的特定限额，如果没有则给定极大的默认值
        limit = model_cfg.get("daily_quota", 100000000) 
        
        if current_usage >= limit:
            return False, current_usage, limit, f"模型 [{model_id}] 已达每日免费额度"

        return True, current_usage, limit, "额度充足"

# 全局单例
usage_tracker = UsageTracker()
