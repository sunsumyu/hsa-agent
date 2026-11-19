import os
import json
import tempfile
import pytest
from unittest.mock import patch
from app.memory.action_cache import ActionCacheManager
from app.memory.history import HistoryManager

def test_action_cache_persist_uses_atomic_replace():
    """RED 测试：ActionCacheManager 持久化必须使用 os.replace 原子替换，杜绝半包写入风险"""
    with tempfile.TemporaryDirectory() as tmpdir:
        cache_file = os.path.join(tmpdir, "action_cache.json")
        manager = ActionCacheManager(cache_file=cache_file)
        
        replace_calls = []
        orig_replace = os.replace
        def mock_replace(src, dst):
            replace_calls.append((src, dst))
            return orig_replace(src, dst)

        with patch("os.replace", side_effect=mock_replace):
            manager.save(
                question="测试原子写入",
                sql="SELECT 1",
                tasks=["t1"],
                methodology="m1"
            )

        assert len(replace_calls) >= 1
        src, dst = replace_calls[0]
        assert dst == cache_file
        assert ".tmp." in src
        assert os.path.exists(cache_file)
        with open(cache_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert len(data) == 1
            assert data[0]["question"] == "测试原子写入"

def test_history_save_turn_uses_atomic_replace():
    """RED 测试：HistoryManager 对话保存必须使用 os.replace 原子替换"""
    with tempfile.TemporaryDirectory() as tmpdir:
        history_mgr = HistoryManager(storage_dir=tmpdir)
        session_id = "test_atomic_session"
        target_path = history_mgr._get_path(session_id)

        replace_calls = []
        orig_replace = os.replace
        def mock_replace(src, dst):
            replace_calls.append((src, dst))
            return orig_replace(src, dst)

        with patch("os.replace", side_effect=mock_replace):
            history_mgr.save_turn(session_id, "用户提问", "系统回答")

        assert len(replace_calls) >= 1
        src, dst = replace_calls[0]
        assert dst == target_path
        assert ".tmp." in src
        assert os.path.exists(target_path)
        with open(target_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            assert len(data) == 2
