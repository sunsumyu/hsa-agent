"""
app/core/memory/action_cache.py
==========================
[V227.0] 动作压缩与规范化语义缓存层 (Action Cache Deep Module)

核心职责：
1. 口语修饰语、虚词、停用词与标点规范化清洗 (normalize_question)
2. 双重索引构建 (精确查询 lookup 与 0ms 规范化意图直通索引 canonical_lookup)
3. Matt Pocock 确定性契约与指纹校验 (get_or_compute & evict)
4. 多级缓存穿透保护 (L0 字典 -> L0.5 规范化 -> L1 Redis 分布式 -> L2 向量余弦相似度)
5. 物理持久化与断言失败自愈重算
"""

from __future__ import annotations

import os
import json
import re
import numpy as np
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from loguru import logger

from app.infra.redis_client import redis_manager


class ActionCacheManager:
    """情节与动作缓存管理器 (Episodic Action Cache)。"""

    def __init__(self, cache_file: str = "data/action_cache.json"):
        self.cache_file = cache_file
        self.cache: List[Dict[str, Any]] = self._load()
        # [V159.0] 精确匹配索引
        self.lookup: Dict[str, Dict[str, Any]] = {
            item["question"].strip(): item for item in self.cache if item.get("question")
        }
        # [V227.0 规范化索引] 去除口语虚词，实现相近表述 0ms 意图直通命中
        self.canonical_lookup: Dict[str, Dict[str, Any]] = {
            self.normalize_question(item["question"]): item
            for item in self.cache
            if item.get("question")
        }
        self._engine = None
        self._stats: Dict[str, Any] = {
            "queries": 0,
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "hits_by_tier": {"L0": 0, "L0.5": 0, "L1": 0, "L2": 0},
        }

    @staticmethod
    def normalize_question(q: str) -> str:
        """剥离口语修饰、停用词与标点，产出规范化核心语义指纹。"""
        if not q:
            return ""
        cleaned = q.strip().lower()
        # 1. 过滤全角/半角标点符号及空白
        cleaned = re.sub(r"[，。？！,\?!：:\s\(\)（）\"\'“”‘’、；;【】\[\]]+", "", cleaned)
        # 2. 剥离句首礼貌修饰词
        cleaned = re.sub(r"^(请帮我|请协助|麻烦帮我|麻烦|请问|请重点|请|帮我)+", "", cleaned)
        # 3. 剥离句首范围引导词
        cleaned = re.sub(r"^(针对|关于|对于|调取|检索|查找|对)+", "", cleaned)
        # 4. 剥离通用动作口语短语（全句范围）
        action_patterns = [
            r"开展(核查|排查|审计|检查|分析|统计)",
            r"进行(核查|排查|审计|检查|分析|统计)",
            r"(查一下|排查一下|核查一下|看下|查下|看一下|一下)",
            r"(开展|进行|排查|核查|统计|查询)$",
        ]
        for pat in action_patterns:
            cleaned = re.sub(pat, "", cleaned)
        # 5. 再次剥离首尾残留修饰动词
        cleaned = re.sub(r"^(排查|核查|统计|查询|调取|开展|进行)+", "", cleaned)
        cleaned = re.sub(r"(排查|核查|统计|查询|核对|分析|开展|进行)$", "", cleaned)
        return cleaned.strip()

    @property
    def engine(self):
        """惰性加载嵌入向量引擎。"""
        if self._engine is None:
            try:
                from app.core.memory.embedding import embedding_engine
                self._engine = embedding_engine
            except Exception as e:
                logger.debug(f"[ActionCacheManager] 嵌入引擎引用获取跳过: {e}")
                self._engine = None
        return self._engine

    def _load(self) -> List[Dict[str, Any]]:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8-sig") as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"[ActionCacheManager] 加载缓存失败 {self.cache_file}: {e}")
        return []

    def _persist(self):
        """物理持久化缓存至本地 JSON 文件 (os.replace 原子替换，杜绝半包截断)。"""
        try:
            dir_name = os.path.dirname(self.cache_file) or "."
            os.makedirs(dir_name, exist_ok=True)
            tmp_file = f"{self.cache_file}.tmp.{os.getpid()}_{datetime.now().strftime('%f')}"
            with open(tmp_file, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, ensure_ascii=False, indent=2)
            os.replace(tmp_file, self.cache_file)
        except Exception as e:
            logger.error(f"[ActionCacheManager] 持久化缓存失败: {e}")

    def evict(self, question: str):
        """[V222.0] 物理淘汰指定脏缓存。"""
        q_strip = question.strip()
        canon_q = self.normalize_question(q_strip)
        if q_strip in self.lookup:
            del self.lookup[q_strip]
        if canon_q in self.canonical_lookup:
            del self.canonical_lookup[canon_q]
        self.cache = [item for item in self.cache if item.get("question", "").strip() != q_strip]
        self._stats["evictions"] += 1
        self._persist()
        try:
            redis_manager.delete(f"action_cache:{q_strip}")
        except Exception as exc:
            logger.debug(f"[ActionCacheManager] Redis delete skipped for {q_strip[:20]}: {exc}")
        logger.warning(f"🧹 [Action Cache] 契约断言未通过，已物理淘汰脏缓存: {question[:20]}...")

    def _record_hit(self, item: Dict[str, Any], tier: str) -> None:
        """记录单次命中统计并更新条目 hit_count。"""
        self._stats["hits"] += 1
        if tier in self._stats["hits_by_tier"]:
            self._stats["hits_by_tier"][tier] += 1
        item["hit_count"] = int(item.get("hit_count", 0)) + 1
        item["last_hit_at"] = datetime.now().isoformat()
        q_strip = str(item.get("question", "") or "").strip()
        if q_strip and q_strip in self.lookup:
            self.lookup[q_strip]["hit_count"] = item["hit_count"]
            self.lookup[q_strip]["last_hit_at"] = item["last_hit_at"]
            self._persist()

    def get_stats(self, top_n: int = 5) -> Dict[str, Any]:
        """返回动作语义缓存的实时命中率、分层命中分布与高频条目摘要。"""
        queries = self._stats["queries"]
        hits = self._stats["hits"]
        hit_rate = round(hits / queries, 4) if queries > 0 else 0.0
        sorted_entries = sorted(
            self.cache,
            key=lambda x: int(x.get("hit_count", 0)),
            reverse=True,
        )[:top_n]
        top_entries = [
            {
                "question": str(e.get("question", ""))[:80],
                "hit_count": int(e.get("hit_count", 0)),
                "last_hit_at": e.get("last_hit_at"),
                "prompt_version": e.get("prompt_version"),
            }
            for e in sorted_entries
        ]
        return {
            "total_entries": len(self.cache),
            "queries": queries,
            "hits": hits,
            "misses": self._stats["misses"],
            "evictions": self._stats["evictions"],
            "hit_rate": hit_rate,
            "hits_by_tier": dict(self._stats["hits_by_tier"]),
            "total_entry_hits": sum(int(e.get("hit_count", 0)) for e in self.cache),
            "top_hit_entries": top_entries,
        }

    def save(
        self,
        question: str,
        sql: str,
        tasks: Optional[List[str]] = None,
        methodology: str = "",
        fingerprint: Optional[Dict[str, str]] = None,
    ):
        """保存审计动作并建立多级检索索引。"""
        q_strip = question.strip()
        emb = None
        if self._engine is not None:
            try:
                emb = self.engine.embed_query(question) if self.engine else None
            except Exception:
                emb = None

        prev_item = self.lookup.get(q_strip) or {}
        item: Dict[str, Any] = {
            "question": question,
            "sql": sql,
            "tasks": tasks or [],
            "methodology": methodology,
            "embedding": emb,
            "timestamp": datetime.now().isoformat(),
            "hit_count": int(prev_item.get("hit_count", 0)),
        }
        if prev_item.get("last_hit_at"):
            item["last_hit_at"] = prev_item["last_hit_at"]
        if fingerprint:
            item.update(fingerprint)

        # 覆盖或追加
        self.cache = [entry for entry in self.cache if entry.get("question", "").strip() != q_strip]
        self.cache.append(item)
        self.lookup[q_strip] = item
        canon_q = self.normalize_question(q_strip)
        if canon_q:
            self.canonical_lookup[canon_q] = item
        self._persist()

        # 分布式同步
        try:
            redis_manager.set_cache(f"action_cache:{q_strip}", json.dumps(item), expire_hours=48)
        except Exception as exc:
            logger.debug(f"[ActionCacheManager] Redis set_cache skipped for {q_strip[:20]}: {exc}")
        logger.success(f"💾 [Action Cache] 已固化审计动作链至缓存 (含指纹与规范化键): {question[:15]}...")

    def get_or_compute(
        self,
        question: str,
        fingerprint: Optional[Dict[str, str]] = None,
        validator: Optional[Callable[[str], bool]] = None,
        computer: Optional[Callable[[], str]] = None,
    ) -> str:
        """
        [Matt Pocock 确定性接缝] 带指纹契约与自愈淘汰机制的缓存存取。
        1. 查找缓存：根据 question 匹配已有记录；
        2. 指纹校验：比对 prompt_version、schema_hash，不一致则判定为 Miss；
        3. 契约校验：若传入 validator(sql) 返回 False（例如全量普查场景含有 LIMIT），
           则立即从内存 lookup、cache 列表及本地 json 文件中物理淘汰（Evict）该脏记录；
        4. 自愈计算：Cache Miss 或 Evict 时，调用 computer() 生成全新正确 SQL，
           绑定新指纹并写回持久化存储；
        5. 返回有效结果。
        """
        self._stats["queries"] += 1
        q_strip = question.strip()
        hit_tier = "L0"
        matched_item = self.lookup.get(q_strip)
        if not matched_item:
            canon_q = self.normalize_question(q_strip)
            if canon_q:
                matched_item = self.canonical_lookup.get(canon_q)
                if matched_item:
                    hit_tier = "L0.5"

        if matched_item:
            fingerprint_valid = True
            if fingerprint:
                for k, v in fingerprint.items():
                    if matched_item.get(k) != v:
                        fingerprint_valid = False
                        logger.info(f"🔄 [Action Cache] 缓存指纹不匹配 ({k}: {matched_item.get(k)} != {v})，判定失效")
                        break

            if fingerprint_valid:
                cached_sql = matched_item.get("sql", "")
                if validator:
                    if validator(cached_sql):
                        self._record_hit(matched_item, hit_tier)
                        return cached_sql
                    else:
                        logger.warning(f"⚠️ [Action Cache] 缓存内容未通过运行时契约校验，执行淘汰: {question[:20]}")
                        self.evict(question)
                else:
                    self._record_hit(matched_item, hit_tier)
                    return cached_sql

        self._stats["misses"] += 1
        if computer:
            logger.info(f"⚙️ [Action Cache] 触发重新生成: {question[:20]}")
            computed_sql = computer()
            self.save(question=question, sql=computed_sql, fingerprint=fingerprint)
            return computed_sql

        return ""

    def search(self, question: str, threshold: float = 0.85) -> Optional[Dict[str, Any]]:
        """[V159.0] 高性能语义搜索：返回完整的动作链载荷。"""
        self._stats["queries"] += 1
        if not self.cache:
            self._stats["misses"] += 1
            return None

        q_strip = question.strip()
        # A. 内存字典精确匹配 (L0)
        if q_strip in self.lookup:
            logger.success(f"⚡ [Action Cache] 字典精确命中: {question[:15]}...")
            item = self.lookup[q_strip]
            self._record_hit(item, "L0")
            return item

        # A.1 规范化意图匹配 (L0.5 极速语义命中，免除向量与网络计算)
        canon_q = self.normalize_question(q_strip)
        if canon_q and canon_q in self.canonical_lookup:
            logger.success(f"🎯 [Action Cache] 规范化意图直通命中 ({canon_q[:15]}...): {question[:15]}...")
            item = self.canonical_lookup[canon_q]
            self._record_hit(item, "L0.5")
            return item

        # B. Redis 分布式缓存匹配 (L1)
        cached_json = redis_manager.get_cache(f"action_cache:{q_strip}")
        if cached_json:
            logger.success(f"🚀 [REDIS] 动作链缓存命中: {question[:15]}...")
            item = json.loads(cached_json)
            self._record_hit(item, "L1")
            return item

        # C. 语义相似度匹配 (L2)
        if not self.engine:
            self._stats["misses"] += 1
            return None

        query_emb = np.array(self.engine.embed_query(question))
        query_norm = np.linalg.norm(query_emb)

        best_score = 0
        best_item = None

        for item in self.cache:
            if "embedding" in item:
                target_emb = np.array(item["embedding"])
                if len(target_emb) != len(query_emb):
                    continue

                dot_product = np.dot(query_emb, target_emb)
                target_norm = np.linalg.norm(target_emb)
                score = dot_product / (query_norm * target_norm) if (query_norm * target_norm) != 0 else 0

                if score > best_score:
                    best_score = score
                    best_item = item

        if best_score >= threshold and best_item is not None:
            logger.success(f"🔍 [Action Cache] 语义命中 (Score: {best_score:.2f}): {question[:15]}...")
            self._record_hit(best_item, "L2")
            return best_item
        self._stats["misses"] += 1
        return None


# 全局默认单例与向后兼容别名
action_cache_manager = ActionCacheManager()
sql_cache_manager = action_cache_manager
