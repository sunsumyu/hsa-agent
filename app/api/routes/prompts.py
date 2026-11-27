"""
app/routes/prompts.py
=====================
[V192.0] 提示词版本与历史管理 API
支持提示词的列出、详情查看、历史记录、保存新版本、版本回滚以及比对。
接入统一 ResponseEnvelope 深模块，薄控制器设计。
底层完全委托给 PromptVersionManager 深模块。
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Body
from loguru import logger

from app.core.registry.prompt_version_manager import PromptVersionManager
from app.api.envelope import ResponseEnvelope

router = APIRouter(prefix="/api/prompts", tags=["Prompt Manager"])

# 模块级全局实例，便于外部注入与测试隔离
prompt_version_manager = PromptVersionManager()

# 向后兼容别名委托
_get_history_files = prompt_version_manager.get_history_files
_parse_yaml_file = prompt_version_manager.parse_yaml_file


@router.get("/list")
async def list_prompts():
    """获取当前所有提示词的最新版本及其基本元数据"""
    prompts = prompt_version_manager.list_prompt_summaries()
    return ResponseEnvelope.success(prompts=prompts)


@router.get("/{prompt_id}/details")
async def get_prompt_details(prompt_id: str):
    """获取单个提示词的详细内容和完整参数"""
    try:
        data = prompt_version_manager.get_prompt_details(prompt_id)
        return ResponseEnvelope.success(data=data)
    except KeyError:
        return ResponseEnvelope.error(error=f"未找到提示词 {prompt_id}", status_code=404)


@router.get("/{prompt_id}/history")
async def get_prompt_history(prompt_id: str):
    """获取指定提示词的完整版本历史列表"""
    history = prompt_version_manager.get_prompt_history(prompt_id)
    return ResponseEnvelope.success(history=history)


@router.post("/save")
async def save_prompt(payload: Dict[str, Any] = Body(...)):
    """保存提示词的新版本，物理生成新历史快照并更新当前活跃版本"""
    prompt_id = payload.get("prompt_id")
    version = payload.get("version")
    description = payload.get("description", "")
    system_template = payload.get("system_template", "")
    variables = payload.get("variables")
    has_messages_placeholder = payload.get("has_messages_placeholder", True)
    human_suffix = payload.get("human_suffix")

    res = prompt_version_manager.save_prompt_version(
        prompt_id=prompt_id,
        version=version,
        description=description,
        system_template=system_template,
        variables=variables,
        has_messages_placeholder=has_messages_placeholder,
        human_suffix=human_suffix,
    )
    return ResponseEnvelope.success(
        message=f"成功保存提示词 {prompt_id.upper()} 新版本 {version}，已同步热重载！"
    )


@router.post("/rollback")
async def rollback_prompt(payload: Dict[str, Any] = Body(...)):
    """将提示词精准回滚至指定历史版本快照"""
    prompt_id = payload.get("prompt_id")
    target_version = payload.get("target_version")
    try:
        prompt_version_manager.rollback_prompt_version(
            prompt_id=prompt_id,
            target_version=target_version,
        )
        return ResponseEnvelope.success(
            message=f"成功将提示词 {prompt_id.upper()} 回滚至历史版本 {target_version}！"
        )
    except (KeyError, FileNotFoundError) as fe:
        return ResponseEnvelope.error(
            error=f"未找到历史版本文件: {prompt_id.lower()}_v{target_version}.yaml",
            status_code=404,
        )


@router.get("/compare")
async def compare_prompts(prompt_id: str, version_a: str, version_b: str):
    """获取两个版本的系统提示模板，用于前端进行差异(Diff)对比"""
    try:
        res = prompt_version_manager.compare_prompt_versions(
            prompt_id=prompt_id,
            version_a=version_a,
            version_b=version_b,
        )
        return ResponseEnvelope.success(**res)
    except (KeyError, FileNotFoundError):
        return ResponseEnvelope.error(
            error="未能找到指定版本的比对文件，请确保版本号正确且已存在历史记录中。",
            status_code=404,
        )
