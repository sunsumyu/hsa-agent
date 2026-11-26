"""
BFCL v4 数据集加载器。

支持从本地 gorilla 仓库 (`bfcl_eval/data`) 或已安装的 `bfcl_eval` 包内数据目录加载
`BFCL_v4_{category}.json` 与对应的 `possible_answer/BFCL_v4_{category}.json` (JSONL 格式)。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

SUPPORTED_CATEGORIES = (
    "simple_python",
    "simple_java",
    "simple_javascript",
    "multiple",
    "parallel",
    "parallel_multiple",
    "irrelevance",
    "live_simple",
    "live_multiple",
    "live_parallel",
    "live_parallel_multiple",
    "live_irrelevance",
    "live_relevance",
)

# 不需要 possible_answer 的类别（期望模型不调用任何函数）
IRRELEVANCE_CATEGORIES = frozenset({"irrelevance", "live_irrelevance"})


@dataclass
class BFCLSample:
    id: str
    category: str
    question: List[List[Dict[str, str]]]
    function: List[Dict[str, Any]]
    ground_truth: Optional[List[Dict[str, Any]]] = field(default=None)

    @property
    def first_turn_messages(self) -> List[Dict[str, str]]:
        """返回第一轮对话消息列表 (BFCL single-turn 数据集默认只有一个 turn)。"""
        if not self.question:
            return []
        return self.question[0]


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def resolve_bfcl_data_dir(explicit_dir: Optional[str] = None) -> Path:
    """按优先级解析 BFCL v4 数据目录。"""
    candidates: List[Path] = []
    if explicit_dir:
        candidates.append(Path(explicit_dir))

    candidates.extend([
        Path("data/bfcl"),
        Path("temp_gorilla/berkeley-function-call-leaderboard/bfcl_eval/data"),
        Path("../gorilla/berkeley-function-call-leaderboard/bfcl_eval/data"),
        Path(".venv-bfcl/Lib/site-packages/bfcl_eval/data"),
        Path(".venv-bfcl/lib/python3.11/site-packages/bfcl_eval/data"),
    ])

    try:
        import bfcl_eval  # type: ignore

        candidates.append(Path(bfcl_eval.__file__).resolve().parent / "data")
    except ImportError as exc:
        logging.getLogger(__name__).debug("bfcl_eval package not installed: %s", exc)

    for c in candidates:
        if c.exists() and c.is_dir():
            return c

    searched = ", ".join(str(c) for c in candidates)
    raise FileNotFoundError(
        f"未找到 BFCL 数据目录。已尝试: {searched}。"
        "请传入 bfcl_data_dir，或将 gorilla 仓库的 bfcl_eval/data 放到 data/bfcl。"
    )


class BFCLDataset:
    """BFCL v4 数据集加载器。"""

    def __init__(
        self,
        category: str = "simple_python",
        bfcl_data_dir: Optional[str] = None,
    ):
        self.category = category
        self.bfcl_data_dir = bfcl_data_dir
        self.resolved_dir: Optional[Path] = None
        self.samples: List[BFCLSample] = []

    def load(self, max_samples: int = 0) -> List[BFCLSample]:
        """加载指定类别的测试样本及 ground truth。max_samples=0 表示加载全部。"""
        data_dir = resolve_bfcl_data_dir(self.bfcl_data_dir)
        self.resolved_dir = data_dir

        test_file = data_dir / f"BFCL_v4_{self.category}.json"
        if not test_file.exists():
            raise FileNotFoundError(f"找不到测试数据文件: {test_file}")

        raw_items = _read_jsonl(test_file)
        if max_samples > 0:
            raw_items = raw_items[:max_samples]

        gt_map: Dict[str, List[Dict[str, Any]]] = {}
        if self.category not in IRRELEVANCE_CATEGORIES:
            gt_file = data_dir / "possible_answer" / f"BFCL_v4_{self.category}.json"
            if gt_file.exists():
                for row in _read_jsonl(gt_file):
                    gt_map[row["id"]] = row.get("ground_truth", [])

        samples: List[BFCLSample] = []
        for item in raw_items:
            sid = item["id"]
            samples.append(
                BFCLSample(
                    id=sid,
                    category=self.category,
                    question=item.get("question", []),
                    function=item.get("function", []),
                    ground_truth=gt_map.get(sid),
                )
            )

        self.samples = samples
        return samples
