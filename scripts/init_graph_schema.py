
from app.infra.neo4j_manager import neo4j_manager
from loguru import logger
from dotenv import load_dotenv

load_dotenv()

def init_schema():
    """
    [企业级] 初始化 Neo4j 图谱物理约束与索引。
    确保在大规模数据集下的关联查询性能。
    """
    try:
        driver = neo4j_manager.get_driver()
        with driver.session() as session:
            # 1. 节点唯一性约束
            logger.info("🛠️ 正在创建节点唯一性约束...")
            session.run("CREATE CONSTRAINT PatientPsnNo IF NOT EXISTS FOR (p:Patient) REQUIRE p.psn_no IS UNIQUE")
            session.run("CREATE CONSTRAINT HospitalCode IF NOT EXISTS FOR (h:Hospital) REQUIRE h.fixmedins_code IS UNIQUE")
            session.run("CREATE CONSTRAINT PhoneTel IF NOT EXISTS FOR (t:Phone) REQUIRE t.tel IS UNIQUE")
            
            # 2. 性能索引
            logger.info("🛠️ 正在创建性能索引...")
            session.run("CREATE INDEX HospitalName IF NOT EXISTS FOR (h:Hospital) ON (h.name)")
            session.run("CREATE INDEX PhoneValue IF NOT EXISTS FOR (t:Phone) ON (t.tel)")
            
            logger.success("✅ [Neo4j] 图谱 Schema 初始化完成。")
    except Exception as e:
        logger.error(f"❌ [Neo4j] Schema 初始化失败: {e}")
        print("\n[提示] 请确保 Neo4j 服务已启动 (bolt://localhost:7687) 且密码配置正确。")

if __name__ == "__main__":
    init_schema()
