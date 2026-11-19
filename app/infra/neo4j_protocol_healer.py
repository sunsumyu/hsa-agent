"""
app/infra/neo4j_protocol_healer.py
==================================
[Matt Pocock Deep Module] Neo4j 连接协议自愈与网络端口探活器

核心职责：
1. 本地协议自愈：针对本地与 WSL 容器环境，将易导致路由失败的 neo4j:// 协议自动降级自愈为 bolt://
2. 端口解析与探活：在建立昂贵连接池前，执行低开销的非阻塞 socket 端口物理探测，防止长期挂起与产生 defunct connection
3. 安全降级：探活失败时提供清晰告警并协助上层透明降级为内存图谱
"""

from __future__ import annotations

import socket
from typing import Tuple
from loguru import logger


class Neo4jProtocolHealer:
    """Neo4j 协议自愈与端口探活深模块"""

    def heal_uri(self, uri: str) -> str:
        """针对本地环境将 neo4j:// 协议自愈为 bolt://"""
        if not uri:
            return "bolt://localhost:7687"

        if ("localhost" in uri or "127.0.0.1" in uri) and uri.startswith("neo4j://"):
            logger.warning("[NEO4J] 检测到本地环境使用 neo4j:// 协议，可能导致路由失败。正在尝试降级为 bolt://...")
            return uri.replace("neo4j://", "bolt://")
        return uri

    def parse_endpoint(self, uri: str) -> Tuple[str, int]:
        """从连接 URI 中解析主机名和端口号"""
        clean_uri = self.heal_uri(uri)
        try:
            if "//" in clean_uri:
                addr_part = clean_uri.split("//")[1].split("/")[0]
            else:
                addr_part = clean_uri

            if ":" in addr_part:
                host, port_str = addr_part.split(":")
                return host, int(port_str)
            return addr_part, 7687
        except Exception:
            return "localhost", 7687

    def probe_port(self, uri: str, timeout: float = 2.0) -> Tuple[bool, str, int]:
        """执行非阻塞 socket 物理连通性探活"""
        host, port = self.parse_endpoint(uri)
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True, host, port
        except Exception as e:
            logger.warning(f">>> [NEO4J] 物理探测失败 ({host}:{port}): {e}。将自动降级为内存图谱。")
            return False, host, port


# 单例默认实例
neo4j_protocol_healer = Neo4jProtocolHealer()
