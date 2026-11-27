"""
调用隔离虚拟环境 (`.venv-bfcl`) 中的官方 `bfcl_eval` 进行复核。

优先尝试 `bfcl evaluate` CLI；若 `.venv-bfcl` 为轻量安装（未装齐各厂商推理 SDK，
导致 `MODEL_CONFIG_MAPPING` 顶层 import 缺包），则自动回退到在同一 `.venv-bfcl`
中直接调用官方 `bfcl_eval.eval_checker.ast_eval.ast_checker` 逐条复核。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Sequence


def find_bfcl_executable() -> Optional[str]:
    for candidate in (
        Path(".venv-bfcl/Scripts/bfcl.exe"),
        Path(".venv-bfcl/bin/bfcl"),
    ):
        if candidate.exists():
            return str(candidate)
    return shutil.which("bfcl")


def find_bfcl_python() -> Optional[str]:
    for candidate in (
        Path(".venv-bfcl/Scripts/python.exe"),
        Path(".venv-bfcl/bin/python"),
    ):
        if candidate.exists():
            return str(candidate)
    return None


_AST_SHIM_SCRIPT = r"""
import json, pathlib, sys, types

result_dir = pathlib.Path(sys.argv[1])
model_name = sys.argv[2]
categories = [c for c in sys.argv[3].split(",") if c]

mc = types.ModuleType("bfcl_eval.constants.model_config")
mc.MODEL_CONFIG_MAPPING = {
    model_name: types.SimpleNamespace(is_fc_model=True, underscore_to_dot=False)
}
sys.modules["bfcl_eval.constants.model_config"] = mc

import bfcl_eval
from bfcl_eval.constants.enums import Language
from bfcl_eval.eval_checker.ast_eval.ast_checker import ast_checker

data_dir = pathlib.Path(bfcl_eval.__file__).resolve().parent / "data"
model_folder = model_name.replace("/", "_")

lang_map = {
    "simple_java": Language.JAVA,
    "simple_javascript": Language.JAVASCRIPT,
}

total_ok = 0
total_n = 0
lines = []
for cat in categories:
    res_file = result_dir / model_folder / f"BFCL_v4_{cat}_result.json"
    if not res_file.exists():
        lines.append(f"{cat}: missing result file {res_file}")
        continue
    prompts = {
        r["id"]: r
        for r in map(json.loads, (data_dir / f"BFCL_v4_{cat}.json").read_text(encoding="utf-8").splitlines())
        if r
    }
    gt_file = data_dir / "possible_answer" / f"BFCL_v4_{cat}.json"
    gts = (
        {r["id"]: r["ground_truth"] for r in map(json.loads, gt_file.read_text(encoding="utf-8").splitlines()) if r}
        if gt_file.exists()
        else {}
    )
    preds = [json.loads(l) for l in res_file.read_text(encoding="utf-8").splitlines() if l.strip()]
    cat_ok = 0
    for p in preds:
        sid = p["id"]
        decoded = [
            {k: (json.loads(v) if isinstance(v, str) else v) for k, v in item.items()}
            for item in p.get("result", [])
        ]
        if cat in ("irrelevance", "live_irrelevance"):
            valid = len(decoded) == 0
        else:
            res = ast_checker(
                prompts[sid]["function"],
                decoded,
                gts[sid],
                lang_map.get(cat, Language.PYTHON),
                cat,
                model_name,
            )
            valid = bool(res.get("valid"))
        if valid:
            cat_ok += 1
    total_ok += cat_ok
    total_n += len(preds)
    acc = (cat_ok / len(preds) * 100.0) if preds else 0.0
    lines.append(f"{cat}: {cat_ok}/{len(preds)} ({acc:.2f}%)")

overall = (total_ok / total_n * 100.0) if total_n else 0.0
lines.append(f"Overall (official ast_checker): {total_ok}/{total_n} ({overall:.2f}%)")
print("\n".join(lines))
"""


def run_official_eval(
    result_dir: str | Path,
    model_name: str,
    categories: Sequence[str],
    partial_eval: bool = True,
) -> Dict[str, Any]:
    """
    运行官方 BFCL 评估复核。
    """
    resolved_dir = str(Path(result_dir).resolve())
    cats_arg = ",".join(categories)

    exe = find_bfcl_executable()
    if exe:
        cmd = [
            exe,
            "evaluate",
            "--model",
            model_name,
            "--test-category",
            cats_arg,
            "--result-dir",
            resolved_dir,
        ]
        if partial_eval:
            cmd.append("--partial-eval")
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if proc.returncode == 0:
            return {
                "available": True,
                "mode": "cli",
                "command": " ".join(cmd),
                "returncode": 0,
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            }

    py_exe = find_bfcl_python()
    if py_exe:
        cmd = [py_exe, "-c", _AST_SHIM_SCRIPT, resolved_dir, model_name, cats_arg]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        return {
            "available": True,
            "mode": "ast_checker",
            "command": f"{py_exe} -c <ast_checker> {resolved_dir} {model_name} {cats_arg}",
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }

    return {
        "available": False,
        "mode": "none",
        "returncode": -1,
        "stdout": "",
        "stderr": "未找到 .venv-bfcl 或系统 bfcl 可执行文件。",
    }
