"""
app/routes/prompts.py
=====================
[V192.0] 提示词版本与历史管理器 API
支持提示词的列出、详情查看、历史记录、保存新版本、版本回滚以及比对。
"""

from fastapi import APIRouter, HTTPException, Body
from fastapi.responses import JSONResponse
from loguru import logger
import os
import yaml
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional
from app.core.prompt_registry import prompt_registry, PromptEntry

router = APIRouter(prefix="/api/prompts", tags=["Prompt Manager"])

PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"
HISTORY_DIR = PROMPTS_DIR / "history"

# 确保历史目录存在
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

def _get_history_files(prompt_id: str) -> List[Path]:
    """获取指定提示词的所有历史文件列表（按修改时间倒序排列）"""
    pattern = f"{prompt_id.lower()}_v*.yaml"
    files = list(HISTORY_DIR.glob(pattern))
    # 按照修改时间排序
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return files

def _parse_yaml_file(file_path: Path) -> Dict[str, Any]:
    """安全解析一个 YAML 文件并返回其元数据"""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return {
            "id": data.get("id", file_path.stem.split("_v")[0]),
            "version": data.get("version", "0.0.0"),
            "description": data.get("description", ""),
            "variables": data.get("variables", []),
            "has_messages_placeholder": data.get("has_messages_placeholder", True),
            "system_template": data.get("system_template", ""),
            "human_suffix": data.get("human_suffix"),
            "last_modified": datetime.fromtimestamp(file_path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "file_size": file_path.stat().st_size
        }
    except Exception as e:
        logger.error(f"[PromptAPI] 无法解析 YAML 文件 {file_path.name}: {e}")
        return {}

@router.get("/list")
async def list_prompts():
    """获取当前所有提示词的最新版本及其基本元数据"""
    try:
        prompt_registry.reload() # 强制重新加载以保证获取最新值
        prompts = []
        for pid in prompt_registry.list_prompts():
            entry = prompt_registry.get_entry(pid)
            # 获取历史文件数
            hist_count = len(_get_history_files(pid))
            
            # 同时读取文件修改时间
            active_file = PROMPTS_DIR / f"{pid.lower()}.yaml"
            last_modified = ""
            if active_file.exists():
                last_modified = datetime.fromtimestamp(active_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
                
            prompts.append({
                "id": pid,
                "version": entry.version,
                "description": entry.description,
                "variables": entry.variables,
                "has_messages_placeholder": entry.has_messages_placeholder,
                "human_suffix": entry.human_suffix,
                "content_hash": entry.content_hash,
                "history_count": hist_count,
                "last_modified": last_modified
            })
        return JSONResponse(content={"ok": True, "prompts": prompts})
    except Exception as e:
        logger.error(f"❌ [PromptAPI] 获取提示词列表失败: {e}")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

@router.get("/{prompt_id}/details")
async def get_prompt_details(prompt_id: str):
    """获取单个提示词的详细内容和完整参数"""
    try:
        prompt_registry.reload()
        pid = prompt_id.upper()
        entry = prompt_registry.get_entry(pid)
        
        active_file = PROMPTS_DIR / f"{pid.lower()}.yaml"
        last_modified = ""
        if active_file.exists():
            last_modified = datetime.fromtimestamp(active_file.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")

        return JSONResponse(content={
            "ok": True,
            "data": {
                "id": pid,
                "version": entry.version,
                "description": entry.description,
                "variables": entry.variables,
                "has_messages_placeholder": entry.has_messages_placeholder,
                "system_template": entry.system_template,
                "human_suffix": entry.human_suffix,
                "content_hash": entry.content_hash,
                "last_modified": last_modified
            }
        })
    except KeyError:
        return JSONResponse(status_code=404, content={"ok": False, "error": f"未找到提示词 {prompt_id}"})
    except Exception as e:
        logger.error(f"❌ [PromptAPI] 获取提示词详情失败: {e}")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

@router.get("/{prompt_id}/history")
async def get_prompt_history(prompt_id: str):
    """获取指定提示词的完整版本历史列表"""
    try:
        pid = prompt_id.lower()
        files = _get_history_files(pid)
        history = []
        for f in files:
            p_data = _parse_yaml_file(f)
            if p_data:
                history.append(p_data)
        return JSONResponse(content={"ok": True, "history": history})
    except Exception as e:
        logger.error(f"❌ [PromptAPI] 获取提示词历史失败: {e}")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

@router.post("/save")
async def save_prompt(
    prompt_id: str = Body(..., embed=True),
    version: str = Body(..., embed=True),
    description: str = Body(..., embed=True),
    system_template: str = Body(..., embed=True),
    variables: List[str] = Body(default=[], embed=True),
    has_messages_placeholder: bool = Body(default=True, embed=True),
    human_suffix: Optional[str] = Body(default=None, embed=True)
):
    """保存新版本的提示词，同时将旧版本归档至历史记录"""
    try:
        pid = prompt_id.lower()
        active_file = PROMPTS_DIR / f"{pid}.yaml"
        
        # 1. 备份当前活动文件到历史目录中（如果存在的话）
        if active_file.exists():
            old_data = _parse_yaml_file(active_file)
            old_ver = old_data.get("version", "0.0.0")
            # 格式：planner_v1.0.0.yaml
            backup_file = HISTORY_DIR / f"{pid}_v{old_ver}.yaml"
            # 只有当该备份文件不存在时，才写入备份，防止重复覆盖
            if not backup_file.exists():
                with open(backup_file, "w", encoding="utf-8") as f:
                    with open(active_file, "r", encoding="utf-8") as rf:
                        f.write(rf.read())
                logger.info(f"💾 [PromptAPI] 成功归档老版本 {old_ver} 到历史文件: {backup_file.name}")
        
        # 2. 写入新版本到活动文件
        new_content = {
            "id": prompt_id.upper(),
            "version": version,
            "description": description,
            "variables": variables,
            "has_messages_placeholder": has_messages_placeholder,
            "system_template": system_template
        }
        if human_suffix is not None:
            new_content["human_suffix"] = human_suffix
            
        with open(active_file, "w", encoding="utf-8") as f:
            yaml.dump(new_content, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
            
        # 3. 同时将新版本也往历史文件夹中写一份备份以记录这一刻
        new_backup_file = HISTORY_DIR / f"{pid}_v{version}.yaml"
        with open(new_backup_file, "w", encoding="utf-8") as f:
            yaml.dump(new_content, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
            
        # 4. 重新加载注册表以使更改立即生效
        prompt_registry.reload()
        
        return JSONResponse(content={
            "ok": True,
            "message": f"成功保存提示词 {prompt_id.upper()} 新版本 {version}，已同步热重载！"
        })
    except Exception as e:
        logger.error(f"❌ [PromptAPI] 保存提示词失败: {e}")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

@router.post("/rollback")
async def rollback_prompt(
    prompt_id: str = Body(..., embed=True),
    target_version: str = Body(..., embed=True)
):
    """回滚提示词至指定的历史版本"""
    try:
        pid = prompt_id.lower()
        history_file = HISTORY_DIR / f"{pid}_v{target_version}.yaml"
        
        if not history_file.exists():
            return JSONResponse(
                status_code=404, 
                content={"ok": False, "error": f"未找到历史版本文件: {pid}_v{target_version}.yaml"}
            )
            
        active_file = PROMPTS_DIR / f"{pid}.yaml"
        
        # 1. 备份当前的活动版本（如果还没备份的话）
        if active_file.exists():
            curr_data = _parse_yaml_file(active_file)
            curr_ver = curr_data.get("version", "0.0.0")
            curr_backup = HISTORY_DIR / f"{pid}_v{curr_ver}.yaml"
            if not curr_backup.exists():
                with open(curr_backup, "w", encoding="utf-8") as f:
                    with open(active_file, "r", encoding="utf-8") as rf:
                        f.write(rf.read())
                        
        # 2. 将历史版本文件复制到活动文件
        with open(active_file, "w", encoding="utf-8") as f:
            with open(history_file, "r", encoding="utf-8") as hf:
                f.write(hf.read())
                
        # 3. 热重载生效
        prompt_registry.reload()
        
        return JSONResponse(content={
            "ok": True,
            "message": f"成功将提示词 {prompt_id.upper()} 回滚至历史版本 {target_version}！"
        })
    except Exception as e:
        logger.error(f"❌ [PromptAPI] 回滚提示词失败: {e}")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})

@router.get("/compare")
async def compare_prompts(prompt_id: str, version_a: str, version_b: str):
    """获取两个版本的系统提示模板，用于前端进行差异(Diff)对比"""
    try:
        pid = prompt_id.lower()
        file_a = HISTORY_DIR / f"{pid}_v{version_a}.yaml"
        file_b = HISTORY_DIR / f"{pid}_v{version_b}.yaml"
        
        # 针对活动文件特别处理 (可能是活动文件还没备份)
        active_file = PROMPTS_DIR / f"{pid}.yaml"
        
        data_a = None
        data_b = None
        
        if file_a.exists():
            data_a = _parse_yaml_file(file_a)
        elif active_file.exists():
            active_data = _parse_yaml_file(active_file)
            if active_data.get("version") == version_a:
                data_a = active_data
                
        if file_b.exists():
            data_b = _parse_yaml_file(file_b)
        elif active_file.exists():
            active_data = _parse_yaml_file(active_file)
            if active_data.get("version") == version_b:
                data_b = active_data
                
        if not data_a or not data_b:
            return JSONResponse(
                status_code=404,
                content={"ok": False, "error": "未能找到指定版本的比对文件，请确保版本号正确且已存在历史记录中。"}
            )
            
        return JSONResponse(content={
            "ok": True,
            "prompt_id": prompt_id.upper(),
            "version_a": version_a,
            "version_b": version_b,
            "template_a": data_a.get("system_template", ""),
            "template_b": data_b.get("system_template", ""),
            "desc_a": data_a.get("description", ""),
            "desc_b": data_b.get("description", "")
        })
    except Exception as e:
        logger.error(f"❌ [PromptAPI] 比对提示词失败: {e}")
        return JSONResponse(status_code=500, content={"ok": False, "error": str(e)})
