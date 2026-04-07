import os
import json
from loguru import logger
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv

load_dotenv()

class ModelManager:
    def __init__(self, config_path="app/llm_providers.json"):
        self.config_path = config_path
        self.providers = self._load_config()
        
    def _load_config(self):
        """加载模型注册表配置"""
        try:
            if not os.path.exists(self.config_path):
                logger.error(f"配置文件不存在: {self.config_path}")
                return {}
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载模型注册表失败: {e}")
            return {}

    def get_model_list(self):
        """获取可向前端展示的模型列表 (剔除敏感信息)"""
        return [
            {
                "id": k,
                "name": v.get("model_name"),
                "provider": v.get("provider"),
                "tools_support": v.get("tools_support", False),
                "priority": v.get("priority", 99)
            }
            for k, v in self.providers.items()
        ]

    def _create_llm(self, name, cfg):
        """根据供应商类型实例化具体的 LLM 类 (协议自适应)"""
        provider = cfg.get("provider", "openai-compatible")
        api_key = os.getenv(cfg["api_key_env"]) if "api_key_env" in cfg else cfg.get("api_key")
        base_url = os.getenv(cfg["base_url_env"]) if "base_url_env" in cfg else cfg.get("base_url")

        if not api_key:
            logger.warning(f"模型 {name} 缺少 API_KEY，跳过。")
            return None

        try:
            if provider == "google":
                from langchain_google_genai import ChatGoogleGenerativeAI
                return ChatGoogleGenerativeAI(
                    model=cfg["model_name"],
                    google_api_key=api_key,
                    temperature=cfg.get("temperature", 0.1),
                    streaming=True,
                )
            else:
                return ChatOpenAI(
                    model=cfg["model_name"],
                    api_key=api_key,
                    base_url=base_url,
                    temperature=cfg.get("temperature", 0.3),
                    streaming=True,
                    max_retries=1 
                )
        except Exception as e:
            logger.error(f"实例化模型 {name} 失败: {e}")
            return None

    def get_adaptive_llm(self, model_id=None, require_tools=True):
        """
        根据注册表构造高可用回退链。
        如果传入 model_id，则将其置为首选模型。
        """
        # 按优先级排序模型
        sorted_models = sorted(
            [(k, v) for k, v in self.providers.items()],
            key=lambda x: x[1].get("priority", 99)
        )
        
        # 如果用户指定了模型，将该模型提到最前面
        if model_id and model_id in self.providers:
            target = (model_id, self.providers[model_id])
            # 从原列表中移除并插入到队首
            sorted_models = [m for m in sorted_models if m[0] != model_id]
            sorted_models.insert(0, target)
            logger.info(f"用户显式选择了模型: {model_id}，已将其设为首选回路。")

        fallback_chain = []
        for name, cfg in sorted_models:
            if require_tools and not cfg.get("tools_support", False):
                # 如果是用户主动指定的模型但不带工具，我们依然尝试加载它作为首发，
                # 但后续的回退节点仍需保证工具支持。 (此处保留灵活性)
                if name != model_id:
                    continue
                
            llm = self._create_llm(name, cfg)
            if llm:
                fallback_chain.append(llm)
            
        if not fallback_chain:
            raise ValueError("没有发现可用模型")
            
        main_llm = fallback_chain[0]
        # 终极物理日志：强制在终端打印当前生效的主算力节点名
        node_name = sorted_models[0][0]
        logger.warning(f"!!! [物理算力锁定] 全链路已并网，当前主控节点: {node_name} !!!")

        if len(fallback_chain) > 1:
            return main_llm.with_fallbacks(fallback_chain[1:]), node_name
        
        return main_llm, node_name

# 全局单例
model_manager = ModelManager()
