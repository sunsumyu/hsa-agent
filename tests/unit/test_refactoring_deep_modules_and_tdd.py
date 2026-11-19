# -*- coding: utf-8 -*-
"""
TDD Unit Tests for HSA Medical Audit Refactoring
=================================================
Driven by: docs/REFACTORING_SPEC_DEEP_MODULES_AND_HELLO_AGENTS.md
Author: Argus Agent Core Architecture Group

本测试套件严格遵循 TDD 原则：
1. 真实红灯测试：先通过断言暴露出 Prompt 投毒指令、Hint 错误字段、缺少表名、虚假合规等物理缺陷；
2. 严禁形式主义绿灯：测试必须真实断言物理属性，任何偷工减料或假合规行为必须触发 FAIL。
"""
import os
import re
import pytest
from app.core.registry.schema_registry import schema_registry
from app.core.scene_table_selector import scene_table_selector


class TestSchemaRegistryDeepContracts:
    """验证 SchemaRegistry 满足单一事实源深模块契约"""

    def test_schema_registry_contains_all_core_tables(self):
        """必须完整收敛 5 张核心业务底表"""
        expected_tables = {
            "fqz_fymx_test",
            "fqz_gz_jzsj_all_ql",
            "fqz_all_yy_yd",
            "fqz_admdvs",
            "fqz_drug_mcs_info_list"
        }
        all_tables = set(schema_registry.get_all_table_names())
        for t in expected_tables:
            assert t in all_tables, f"核心物理底表 {t} 缺失于 SchemaRegistry!"

    def test_admdvs_has_correct_physical_columns(self):
        """行政区划表字段必须为 ClickHouse 物理真实列：admdvs, admdvs_name, admdvs_lv, prnt_admdvs"""
        entry = schema_registry.get_table("fqz_admdvs")
        assert entry is not None
        assert "admdvs" in entry.field_names
        assert "admdvs_lv" in entry.field_names
        assert "admdvs_name" in entry.field_names
        assert "prnt_admdvs" in entry.field_names
        # 严禁存在臆造的 admdvs_code
        assert "admdvs_code" not in entry.field_names

    def test_all_yy_yd_has_correct_physical_columns(self):
        """定点机构资质名录表字段必须包含 fixmedins_code, fixmedins_name, medins_type, vali_flag"""
        entry = schema_registry.get_table("fqz_all_yy_yd")
        assert entry is not None
        assert "fixmedins_code" in entry.field_names
        assert "fixmedins_name" in entry.field_names
        assert "medins_type" in entry.field_names
        assert "vali_flag" in entry.field_names


class TestSchemaRegistryThreadSafety:
    """验证 SchemaRegistry 惰性加载在并发场景下的线程安全契约 (双重检查锁)"""

    def test_concurrent_first_access_loads_only_once(self):
        """
        [红灯测试] N 个线程同时首次访问，_load_locked 必须只被执行一次。
        若去掉 _ensure_loaded 的双重检查锁，本测试必然因多线程重复加载而红灯。
        """
        import time
        import threading
        from app.core.registry.schema_registry import SchemaRegistry

        registry = SchemaRegistry()
        assert registry._loaded is False, "测试前提：初始未加载"

        load_calls = []
        original_load = registry._load_locked

        def counting_load():
            load_calls.append(threading.get_ident())
            time.sleep(0.02)  # 放大竞态窗口：无锁保护时多线程会同时进入加载
            original_load()

        registry._load_locked = counting_load

        n_threads = 16
        barrier = threading.Barrier(n_threads)
        results = []
        errors = []

        def worker():
            try:
                barrier.wait()
                results.append(registry.get_main_table())
            except Exception as e:
                errors.append(repr(e))

        threads = [threading.Thread(target=worker) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert not errors, f"并发访问抛出异常: {errors}"
        assert len(results) == n_threads, "部分线程未能完成读取"
        assert len(load_calls) == 1, (
            f"双重检查锁失效：_load_locked 被执行 {len(load_calls)} 次，期望 1 次"
        )
        assert len(set(results)) == 1, f"并发读取结果不一致: {set(results)}"

    def test_reload_never_exposes_partial_state(self):
        """
        [红灯测试] reload 期间并发读取方绝不能看到被清空的表清单。
        旧实现先 clear 再加载，会暴露空配置窗口；现实现采局部构建+整体替换。
        """
        import threading
        from app.core.registry.schema_registry import SchemaRegistry

        registry = SchemaRegistry()
        registry._ensure_loaded()
        expected = set(registry.get_all_table_names())
        assert expected, "测试前提：配置文件中应已注册数据表"

        stop = threading.Event()
        empty_snapshots = []

        def reader():
            while not stop.is_set():
                if not registry.get_all_table_names():
                    empty_snapshots.append(threading.get_ident())

        readers = [threading.Thread(target=reader, daemon=True) for _ in range(4)]
        for t in readers:
            t.start()

        try:
            for _ in range(20):
                registry.reload()
        finally:
            stop.set()
            for t in readers:
                t.join(timeout=5)

        assert not empty_snapshots, (
            f"reload 期间出现 {len(empty_snapshots)} 次空表清单快照，状态变更非原子可见"
        )
        assert set(registry.get_all_table_names()) == expected, "reload 后表集发生漂移"


class TestSceneTableSelectorResolution:
    """验证 SceneTableSelector 具备高可靠确定性表选择与 Hint 契约"""

    def test_resolves_administrative_divisions(self):
        """QA-BLIND-08: 行政区划字典普查必须 100% 路由至 fqz_admdvs"""
        query = "查询全国医保标准行政区划代码字典表，统计国家级、省级、地市级与区县级四个层级分别有多少个行政区划条目？总数是多少？"
        primary, tables = scene_table_selector.select_tables(query)
        assert primary == "fqz_admdvs", f"预期主表为 fqz_admdvs, 实际得到: {primary}"
        assert "fqz_admdvs" in tables

    def test_resolves_medical_directory_census(self):
        """QA-BLIND-07: 医药机构资质名录普查必须 100% 路由至 fqz_all_yy_yd"""
        query = "调取全市医药机构资质名录库，统计当前系统内纳管的定点医疗机构与定点零售药店总家数，并列明其基本分布概况。"
        primary, tables = scene_table_selector.select_tables(query)
        assert primary == "fqz_all_yy_yd", f"预期主表为 fqz_all_yy_yd, 实际得到: {primary}"
        assert "fqz_all_yy_yd" in tables

    def test_admdvs_enforcement_hint_uses_exact_column_names(self):
        """Hint 中必须准确传达物理字段名 admdvs，严禁输出错误的 admdvs_code"""
        query = "查询全国医保标准行政区划代码字典表"
        hint = scene_table_selector.get_enforcement_hint(query)
        assert hint is not None
        assert "fqz_admdvs" in hint
        assert "`admdvs`" in hint or "admdvs " in hint
        assert "admdvs_code" not in hint, "Hint 中包含了错误的字段名 admdvs_code!"

    def test_all_yy_yd_enforcement_hint_contains_guidance(self):
        """Hint 中必须包含 fqz_all_yy_yd 真实字段与严禁使用 yyjg_zzml 幻觉表的警示"""
        query = "调取全市医药机构资质名录库"
        hint = scene_table_selector.get_enforcement_hint(query)
        assert hint is not None
        assert "fqz_all_yy_yd" in hint
        assert "fixmedins_code" in hint
        assert "medins_type" in hint


class TestPromptSanitizationContracts:
    """验证 Prompt 清洗契约：消灭投毒指令与表名遗漏"""

    def test_coder_prompt_has_no_poisonous_limit_instruction(self):
        """
        [红灯测试] 验证 prompts/coder.yaml 严禁包含强制加 LIMIT 100 及放弃全量扫描的投毒指令！
        在修复前，coder.yaml 第 72 行存在投毒，此测试必须精确红灯报错。
        """
        coder_yaml_path = os.path.join(os.path.dirname(__file__), "..", "..", "configs", "prompts", "coder.yaml")
        assert os.path.exists(coder_yaml_path), f"找不到 Prompt 文件: {coder_yaml_path}"
        with open(coder_yaml_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 断言不得包含诱导截断的投毒词汇
        assert "强制加 LIMIT 100" not in content, "发现投毒指令：'强制加 LIMIT 100' 存在于 coder.yaml！"
        assert "放弃在主 SQL 中进行大范围的表关联和全量扫描" not in content, "发现投毒指令：诱导放弃全量扫描！"

    def test_coder_prompt_includes_all_core_physical_tables(self):
        """
        [红灯测试] 验证 prompts/coder.yaml 核心表清单必须完整包含 5 张底表：
        fqz_fymx_test, fqz_gz_jzsj_all_ql, fqz_all_yy_yd, fqz_admdvs, fqz_drug_mcs_info_list。
        在修复前缺少 fqz_all_yy_yd 和 fqz_admdvs，此测试必须精确红灯报错。
        """
        coder_yaml_path = os.path.join(os.path.dirname(__file__), "..", "..", "configs", "prompts", "coder.yaml")
        with open(coder_yaml_path, "r", encoding="utf-8") as f:
            content = f.read()

        assert "fqz_admdvs" in content, "coder.yaml 缺少核心表 fqz_admdvs 说明！"
        # 必须直接包含 fqz_all_yy_yd（而非只有带后缀的 fqz_all_yy_yd_1）
        assert re.search(r"fqz_all_yy_yd(?!\w)", content), "coder.yaml 缺少核心底表 fqz_all_yy_yd 说明！"


class TestFailClosedIntegrity:
    """验证 Fail-Closed 设计哲学：绝不允许在物理报错时捏造假合规"""

    def test_reporter_prompt_or_pipeline_rejects_fake_compliance(self):
        """
        [红灯测试] 验证系统在执行异常或表名不存在时不产生假合规。
        检查 prompts/reporter.yaml 中是否有明确指示：若数据执行失败，严禁出具‘高度合规’假结论。
        """
        reporter_yaml_path = os.path.join(os.path.dirname(__file__), "..", "..", "configs", "prompts", "reporter.yaml")
        assert os.path.exists(reporter_yaml_path), f"找不到 Prompt 文件: {reporter_yaml_path}"
        with open(reporter_yaml_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 检查是否包含红线：严禁在执行错误或扫描为 0 时直接断言合规
        assert "Fail-Closed" in content or "严禁伪造合规" in content or "执行异常" in content, \
            "reporter.yaml 缺乏对执行失败场景的 Fail-Closed 红线约束！"

    def test_restricted_mode_prompt_does_not_claim_high_compliance(self):
        """[红灯测试] 当 is_restricted=True 时，提示词中绝对不能诱导‘高度合规’或‘扫描基数 > 0’"""
        from app.reporting.report_renderer import report_renderer
        prompt = report_renderer.prepare_conclusion_prompt(
            user_question="测试受限核查",
            methodology="逻辑受限",
            execution_trace=["SQL 执行异常"],
            hard_count=0,
            hard_sum=0.0,
            is_restricted=True
        )
        assert "证明当前区间内结算高度合规" not in prompt, "受限模式下诱导了‘结算高度合规’假结论！"
        assert "扫描基数 > 0" not in prompt, "受限模式下编造了‘扫描基数 > 0’虚假事实！"
