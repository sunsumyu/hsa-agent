import sys
import os
import json
import datetime
from loguru import logger

sys.path.append(os.getcwd())

from app.infra.db_conn import get_clickhouse_client
from scripts.sync_to_neo4j import sync_clickhouse_to_neo4j

def reseed_all_databases():
    logger.info("🎬 开始执行本地测试库图节点自愈与同步装载...")
    
    # 1. 读取 Schema 缓存
    cache_path = os.path.join("data", "physical_schema_cache.json")
    if not os.path.exists(cache_path):
        logger.error(f"❌ 未找到物理 Schema 缓存: {cache_path}，无法自动生成 DDL！")
        return
        
    with open(cache_path, "r", encoding="utf-8") as f:
        schema_data = json.load(f)
        
    cache = schema_data.get("cache", {})
    metadata = schema_data.get("metadata", [])
    
    # 整理元数据
    meta_dict = {}
    for entry in metadata:
        tbl = entry["table"].lower()
        if tbl not in meta_dict:
            meta_dict[tbl] = {}
        meta_dict[tbl][entry["field"].lower()] = {
            "type": entry["type"],
            "desc": entry.get("desc", "")
        }
        
    client = get_clickhouse_client()
    logger.info("🔌 成功建立 ClickHouse 连接。")
    
    # 确保数据库存在
    client.command("CREATE DATABASE IF NOT EXISTS fqz_hsa")
    client.command("USE fqz_hsa")
    
    # 2. 自动构建并创建表
    tables_to_create = ["fqz_gz_jzsj_all_ql", "fqz_fymx_test", "fqz_fymx_test1"]
    
    for tbl in tables_to_create:
        cache_key = "FQZ_FYMX_TEST" if tbl in ["fqz_fymx_test", "fqz_fymx_test1"] else tbl.upper()
        cols = cache.get(cache_key, [])
        if not cols:
            logger.warning(f"⚠️ 在缓存中未找到表 {tbl} 的列定义，跳过创建。")
            continue
            
        logger.info(f"🔨 正在构建表 {tbl} 的 DDL...")
        
        # 字段列表
        fields_ddl = []
        tbl_meta = meta_dict.get("fqz_fymx_test" if tbl in ["fqz_fymx_test", "fqz_fymx_test1"] else tbl.lower(), {})
        
        # 记录每张表字段对应的物理类型，供写入时格式化参考
        table_types = {}
        
        for col in cols:
            col_lower = col.lower()
            col_meta = tbl_meta.get(col_lower, {})
            c_type = col_meta.get("type")
            
            # [自愈级类型推导 fallback] 
            if not c_type:
                if any(x in col_lower for x in ["time", "date", "begn", "end"]):
                    c_type = "DateTime"
                elif any(x in col_lower for x in ["amt", "pric", "fee", "cnt", "age", "days", "level", "pay"]):
                    c_type = "Float64"
                else:
                    c_type = "String"
                    
            table_types[col_lower] = c_type
            c_desc = col_meta.get("desc", "").replace("'", "\\'")
            
            fields_ddl.append(f"`{col_lower}` {c_type} COMMENT '{c_desc}'")
            
        fields_str = ",\n    ".join(fields_ddl)
        
        # Drop 并重新创建表 (使用 MergeTree 以保证 UPDATE/DELETE 可用)
        client.command(f"DROP TABLE IF EXISTS {tbl}")
        
        ddl = f"""
        CREATE TABLE {tbl} (
            {fields_str}
        ) ENGINE = MergeTree()
        ORDER BY tuple()
        """
        client.command(ddl)
        logger.success(f"✅ 表 {tbl} 构建成功！")
        
    # 3. 准备并插入就诊明细表 Mock 数据 (fqz_fymx_test / fqz_fymx_test1)
    # 明细测试表包含 QA-CUST-08 (住院超限计费)
    logger.info("📝 正在生成收费明细测试表 (QA-CUST-08)...")
    
    fymx_cols = [c.lower() for c in cache["FQZ_FYMX_TEST"]]
    fymx_rows = []
    
    # 埋入违规点：同一人同一天同一医院
    # A. 拔牙 9 颗 (超 8)
    # B. 一级护理费 4 次 (超 3)
    t_base = datetime.datetime(2026, 4, 10, 10, 0, 0)
    
    # 患者 P00001
    fymx_rows.append({
        "prv_name": "广东省", "city_name": "广州市", "admdvs_name": "本级",
        "psn_no": "P00001", "psn_name": "张小牙", "certno": "440100199001011111",
        "gend": "1", "age": 36.0, "insutype": "310", "med_type": "21",
        "fixmedins_code": "H001", "fixmedins_name": "中心医院",
        "hilist_code": "1000201", "hilist_name": "牙齿拔除术",
        "cnt": 9.0, "pric": 150.0, "det_item_fee_sumamt": 1350.0,
        "setl_time": t_base, "fee_ocur_time": t_base, "fx_level": "3"
    })
    fymx_rows.append({
        "prv_name": "广东省", "city_name": "广州市", "admdvs_name": "本级",
        "psn_no": "P00001", "psn_name": "张小牙", "certno": "440100199001011111",
        "gend": "1", "age": 36.0, "insutype": "310", "med_type": "21",
        "fixmedins_code": "H001", "fixmedins_name": "中心医院",
        "hilist_code": "1000502", "hilist_name": "一级护理费",
        "cnt": 4.0, "pric": 50.0, "det_item_fee_sumamt": 200.0,
        "setl_time": t_base, "fee_ocur_time": t_base, "fx_level": "3"
    })
    
    # 填充一些正常明细数据
    for i in range(2, 20):
        fymx_rows.append({
            "prv_name": "广东省", "city_name": "广州市", "admdvs_name": "本级",
            "psn_no": f"P000{i:02d}", "psn_name": f"普通患者_{i}", "certno": f"4401001990010122{i:02d}",
            "gend": str(i % 2 + 1), "age": 40.0 + i, "insutype": "310", "med_type": "21",
            "fixmedins_code": f"H{i:03d}", "fixmedins_name": f"定点医疗机构_{i}",
            "hilist_code": "1000101", "hilist_name": "阿莫西林胶囊",
            "cnt": 2.0, "pric": 15.5, "det_item_fee_sumamt": 31.0,
            "setl_time": t_base + datetime.timedelta(days=i), "fee_ocur_time": t_base + datetime.timedelta(days=i),
            "fx_level": "1"
        })
        
    # 执行明细表数据插入
    def insert_table(table_name, rows_list, cols_list):
        # 动态判定当前表的物理字段类型
        tbl_meta = meta_dict.get("fqz_fymx_test" if table_name in ["fqz_fymx_test", "fqz_fymx_test1"] else table_name.lower(), {})
        
        insert_data = []
        for r in rows_list:
            row_vals = []
            for col in cols_list:
                col_lower = col.lower()
                val = r.get(col_lower)
                
                # 类型匹配与默认值填充
                c_meta = tbl_meta.get(col_lower, {})
                c_type = c_meta.get("type")
                if not c_type:
                    # fallback 推导
                    if any(x in col_lower for x in ["time", "date", "begn", "end"]):
                        c_type = "DateTime"
                    elif any(x in col_lower for x in ["amt", "pric", "fee", "cnt", "age", "days", "level", "pay"]):
                        c_type = "Float64"
                    else:
                        c_type = "String"
                
                # 将空字符串也视为缺失值进行类型强转，防止插入空字符串到数值/日期列
                if val is None or val == "":
                    if "Int" in c_type:
                        val = 0
                    elif "Decimal" in c_type or "Float" in c_type:
                        val = 0.0
                    elif "DateTime" in c_type:
                        val = datetime.datetime.now()
                    else:
                        val = ""
                else:
                    # 强健数据类型清洗转换
                    if "Int" in c_type:
                        val = int(float(val))
                    elif "Decimal" in c_type or "Float" in c_type:
                        val = float(val)
                    elif "DateTime" in c_type:
                        if isinstance(val, str):
                            try:
                                val = datetime.datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
                            except:
                                val = datetime.datetime.now()
                    else:
                        if isinstance(val, (datetime.datetime, datetime.date)):
                            val = val.strftime("%Y-%m-%d %H:%M:%S")
                        else:
                            val = str(val)
                row_vals.append(val)
            insert_data.append(row_vals)
            
        try:
            # 物理级自愈：完全抛弃字符串 SQL 拼接，改用 ClickHouse Native 二进制协议插入，彻底消除字符集乱码与 HTTP 500 解析崩溃
            target_client = client.client if hasattr(client, 'client') and hasattr(client.client, 'insert') else client
            target_client.insert(table_name, insert_data, column_names=cols_list)
        except Exception as e:
            logger.error(f"Failed to native insert into {table_name}: {e}")
            raise
        
    insert_table("fqz_fymx_test", fymx_rows, fymx_cols)
    insert_table("fqz_fymx_test1", fymx_rows, fymx_cols)
    logger.success(f"🎉 明细表数据装载完毕，共 {len(fymx_rows)} 行明细。")
    
    # 4. 准备并插入就诊大宽表 Mock 数据 (fqz_gz_jzsj_all_ql)
    # 包含 QA-CUST-10 (药贩子回流药利益链)
    logger.info("📝 正在生成就诊结算大宽表 (QA-CUST-10)...")
    
    ql_cols = [c.lower() for c in cache["FQZ_GZ_JZSJ_ALL_QL"]]
    ql_rows = []
    
    # 利益链设定：
    # 6 个参保人：P00101 到 P00106
    # 相同的手机和地址：tel="13988888888", addr="桃源小区6号楼"
    # 同一家医院同一大夫开处方：fixmedins_code="H001", fixmedins_name="中心医院", chfpdr_name="王大夫"
    # 同一家药店购药：fixmedins_code="P001", fixmedins_name="德济大药房"
    # 间隔时间小于 24 小时，高额慢病药（medfee_sumamt=12000 ~ 16000）
    
    shared_tel = "13988888888"
    shared_addr = "桃源小区6号楼"
    
    for idx in range(1, 7):
        p_no = f"P0010{idx}"
        p_name = f"回流参保人_{idx}"
        cert = f"44010019700101333{idx}"
        
        # 医院就诊日
        visit_time = datetime.datetime(2026, 4, idx + 2, 9, 30, 0)
        # 药店刷卡日 (间隔 4 小时，符合 24 小时限制)
        pharmacy_time = datetime.datetime(2026, 4, idx + 2, 13, 30, 0)
        
        fee = 10000.0 + idx * 1000.0
        fund = fee * 0.75
        
        # 1. 医院门诊结算
        ql_rows.append({
            "psn_no": p_no, "psn_name": p_name, "gend": str(idx % 2 + 1),
            "certno": cert, "tel": shared_tel, "addr": shared_addr,
            "fixmedins_code": "H001", "fixmedins_name": "中心医院",
            "chfpdr_name": "王大夫", "med_type": "门诊慢特病",
            "setl_time": visit_time, "start_date": visit_time, "end_date": visit_time,
            "medfee_sumamt": fee, "fund_pay_sumamt": fund, "hifp_pay": fund,
            "admdvs_code": 440100, "admdvs_name": "广州市本级", "vali_flag": "1"
        })
        
        # 2. 药店刷卡洗钱
        ql_rows.append({
            "psn_no": p_no, "psn_name": p_name, "gend": str(idx % 2 + 1),
            "certno": cert, "tel": shared_tel, "addr": shared_addr,
            "fixmedins_code": "P001", "fixmedins_name": "德济大药房",
            "chfpdr_name": "", "med_type": "定点药店购药",
            "setl_time": pharmacy_time, "start_date": pharmacy_time, "end_date": pharmacy_time,
            "medfee_sumamt": fee, "fund_pay_sumamt": fund, "hifp_pay": fund,
            "admdvs_code": 440100, "admdvs_name": "广州市本级", "vali_flag": "1"
        })
        
    # 填充一些普通的就诊大宽表记录
    for i in range(20, 60):
        t_visit = datetime.datetime(2026, 4, 15) - datetime.timedelta(days=i-20)
        fee = 300.0 + i * 10.0
        ql_rows.append({
            "psn_no": f"P002{i:02d}", "psn_name": f"大宽表普通患者_{i}", "gend": "1",
            "certno": f"4401001980010199{i:02d}", "tel": f"1366666{i:04d}", "addr": f"普通街道_{i}号",
            "fixmedins_code": f"H{i:03d}", "fixmedins_name": f"普通定点医院_{i}",
            "chfpdr_name": f"普通医生_{i}", "med_type": "门诊",
            "setl_time": t_visit, "start_date": t_visit, "end_date": t_visit,
            "medfee_sumamt": fee, "fund_pay_sumamt": fee * 0.7, "hifp_pay": fee * 0.7,
            "admdvs_code": 440100, "admdvs_name": "广州市本级", "vali_flag": "1"
        })
        
    # 插入就诊结算大表
    insert_table("fqz_gz_jzsj_all_ql", ql_rows, ql_cols)
    logger.success(f"🎉 就诊结算大表数据装载完毕，共 {len(ql_rows)} 行就诊记录。")
    
    # 5. 调用同步逻辑，将 ClickHouse 数据一键灌入 Neo4j
    logger.info("🔗 开始执行 ClickHouse -> Neo4j 图谱管道同步...")
    sync_clickhouse_to_neo4j(limit=100)
    logger.success("🚀 数据装载与图自愈管道执行完毕，状态完美就绪！")

if __name__ == "__main__":
    reseed_all_databases()
