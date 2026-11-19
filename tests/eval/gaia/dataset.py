"""
GAIA 数据集加载器。

支持：
1. 从本地目录加载（优先探测 `<local_data_dir>/2023/<split>/metadata.jsonl` 或 `<local_data_dir>/metadata.jsonl`）；
2. 若本地不存在且配置了 `HF_TOKEN`（环境变量或传入），自动通过 `huggingface_hub.snapshot_download`
   下载受限数据集 `gaia-benchmark/GAIA`。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class GAIASample:
    task_id: str
    question: str
    level: int
    final_answer: str
    file_name: str = ""
    file_path: Optional[Path] = None
    annotator_metadata: Dict[str, Any] = field(default_factory=dict)


def _find_metadata_file(base_dir: Path, split: str) -> Optional[Path]:
    candidates = [
        base_dir / "2023" / split / "metadata.jsonl",
        base_dir / split / "metadata.jsonl",
        base_dir / "metadata.jsonl",
    ]
    for p in candidates:
        if p.exists() and p.is_file():
            return p
    return None


class GAIADataset:
    """GAIA 数据集加载器。"""

    REPO_ID = "gaia-benchmark/GAIA"

    def __init__(
        self,
        split: str = "validation",
        level: Optional[int] = None,
        local_data_dir: Optional[str | Path] = None,
        token: Optional[str] = None,
    ):
        self.split = split
        self.level = level
        self._explicit_dir = local_data_dir is not None
        self.local_data_dir = Path(local_data_dir) if local_data_dir is not None else Path("data/gaia")
        self.token = token or os.getenv("HF_TOKEN")
        self.samples: List[GAIASample] = []

    def _ensure_local_metadata(self) -> Path:
        candidates = [self.local_data_dir]
        if not self._explicit_dir:
            candidates.append(Path("../hello-agents/data/gaia"))
        for base in candidates:
            meta = _find_metadata_file(base, self.split)
            if meta is not None:
                return meta

        if not self.token:
            raise FileNotFoundError(
                f"未找到本地 GAIA 数据集 ({self.local_data_dir}/2023/{self.split}/metadata.jsonl)，"
                "且未检测到 HF_TOKEN。请在 .env 中配置已申请权限的 HF_TOKEN，"
                "或将数据集手动放到 data/gaia/。"
            )

        try:
            from huggingface_hub import snapshot_download
        except ImportError as exc:
            raise RuntimeError(
                "需要 huggingface_hub 才能自动下载 GAIA 数据集：pip install huggingface_hub"
            ) from exc

        snapshot_download(
            repo_id=self.REPO_ID,
            repo_type="dataset",
            local_dir=str(self.local_data_dir),
            token=self.token,
        )
        meta = _find_metadata_file(self.local_data_dir, self.split)
        if meta is None:
            raise FileNotFoundError(f"下载完成但未找到 metadata.jsonl: {self.local_data_dir}")
        return meta

    def load(self, max_samples: int = 0) -> List[GAIASample]:
        """加载 GAIA 样本。level 非空时按难度过滤，max_samples>0 时截断。"""
        meta_file = self._ensure_local_metadata()
        split_dir = meta_file.parent

        items: List[GAIASample] = []
        with meta_file.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                raw = json.loads(line)
                lvl = int(raw.get("Level") or raw.get("level") or 0)
                if self.level is not None and lvl != self.level:
                    continue

                fname = str(raw.get("file_name") or "").strip()
                fpath_raw = str(raw.get("file_path") or "").strip()
                resolved_file: Optional[Path] = None
                if fname:
                    cand = split_dir / fname
                    if cand.exists():
                        resolved_file = cand
                elif fpath_raw:
                    cand = Path(fpath_raw)
                    if not cand.is_absolute():
                        cand = split_dir / cand
                    if cand.exists():
                        resolved_file = cand

                items.append(
                    GAIASample(
                        task_id=str(raw.get("task_id", "")),
                        question=str(raw.get("Question") or raw.get("question") or ""),
                        level=lvl,
                        final_answer=str(raw.get("Final answer") or raw.get("final_answer") or ""),
                        file_name=fname,
                        file_path=resolved_file,
                        annotator_metadata=dict(raw.get("Annotator Metadata") or {}),
                    )
                )

        if max_samples > 0:
            items = items[:max_samples]
        self.samples = items
        return items

    def get_statistics(self) -> Dict[str, Any]:
        if not self.samples:
            self.load()
        dist: Dict[int, int] = {}
        for s in self.samples:
            dist[s.level] = dist.get(s.level, 0) + 1
        return {
            "total_samples": len(self.samples),
            "level_distribution": dict(sorted(dist.items())),
        }
