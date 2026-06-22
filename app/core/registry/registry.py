"""
app/core/registry.py
====================
[V150.0] 企业级工具注册表 (Skill Registry)

实现"插拔式"工具管理模式，解耦 Graph 与具体的 Skill 实现。
"""

from typing import Dict, Any, List, Type, Optional
from langchain_core.tools import BaseTool
from loguru import logger

class SkillRegistry:
    def __init__(self):
        self._skills: Dict[str, BaseTool] = {}
        self._defaults_loaded = False

    def _ensure_defaults_loaded(self):
        """Lazily load default skills on first access."""
        if self._defaults_loaded:
            return
        self._defaults_loaded = True
        self.register_default_skills()

    def register(self, skill: BaseTool):
        """注册一个工具到全局注册表"""
        name = skill.name
        if name in self._skills:
            logger.warning(f"⚠️ [Registry] 覆盖已存在的工具: {name}")
        self._skills[name] = skill
        logger.info(f"✅ [Registry] 工具注册成功: {name}")

    def register_default_skills(self):
        """自动导入并注册所有定义好的工具"""
        try:
            import app.skills.tools as tools_mod
            import inspect
            from langchain_core.tools import BaseTool
            
            count = 0
            for name, obj in inspect.getmembers(tools_mod):
                if isinstance(obj, BaseTool):
                    self.register(obj)
                    count += 1
            logger.info(f"✨ [Registry] 自动加载并注册了 {count} 个默认工具。")
        except Exception as e:
            logger.error(f"❌ [Registry] 自动加载默认工具失败: {e}")

    def get_skill(self, name: str) -> Optional[BaseTool]:
        """根据名称获取工具实例"""
        self._ensure_defaults_loaded()
        return self._skills.get(name)

    def get_all_skills(self) -> List[BaseTool]:
        """获取所有已注册的工具"""
        self._ensure_defaults_loaded()
        return list(self._skills.values())

    def get_tool_map(self) -> Dict[str, BaseTool]:
        """返回工具字典 (适配 LangGraph/LangChain)"""
        self._ensure_defaults_loaded()
        return self._skills

# 全局单例
skill_registry = SkillRegistry()
