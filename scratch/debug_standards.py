import clickhouse_connect
import os
from loguru import logger

def probe_connection(host, port, secure=False, verify=False):
    protocol = "HTTPS" if secure else "HTTP"
    logger.info(f"正在探测 {protocol}://{host}:{port} (verify={verify})...")
    try:
        client = clickhouse_connect.get_client(
            host=host,
            port=port,
            username=os.getenv("CLICKHOUSE_USER", "default"),
            password=os.getenv("CLICKHOUSE_PASSWORD", ""),
            secure=secure,
            verify=verify,
            connect_timeout=10
        )
        logger.success(f"✅ 探测成功！协议: {protocol}, 端口: {port}, 证书校验: {verify}")
        return True
    except Exception as e:
        logger.error(f"❌ 探测失败: {e}")
        return False

if __name__ == "__main__":
    host = "172.25.128.80"
    
    # 策略 1: 纯 HTTP (当前配置)
    if not probe_connection(host, 8123, secure=False):
        # 策略 2: HTTPS on 8123 (有些环境会把 HTTPS 放在 8123)
        if not probe_connection(host, 8123, secure=True, verify=False):
            # 策略 3: 标准 HTTPS on 8443
            if not probe_connection(host, 8443, secure=True, verify=False):
                logger.critical("所有标准 HTTP/HTTPS 路径均已断开。可能存在 IP 白名单或防火墙策略拦截。")
