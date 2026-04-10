#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import hashlib
import json
import time
from typing import Dict, Optional

import httpx

from astrbot.api import logger


class OnePanelAPI:
    """1Panel 面板 API 封装（异步版本）。"""

    def __init__(self, host: str, api_key: str, verify_ssl: bool = False):
        self.host = host.rstrip("/")
        self.api_key = api_key
        self.verify_ssl = verify_ssl
        self._client: Optional[httpx.AsyncClient] = None

        if not verify_ssl:
            logger.warning("SSL 证书验证已禁用，请确保在安全的网络环境中使用")

    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端。"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10, verify=self.verify_ssl)
        return self._client

    async def close(self):
        """关闭 HTTP 客户端。"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    def _get_headers(self) -> Dict[str, str]:
        """生成请求头（包含鉴权信息）。"""
        timestamp = str(int(time.time()))
        token = hashlib.md5(f"1panel{self.api_key}{timestamp}".encode()).hexdigest()
        return {
            "1Panel-Token": token,
            "1Panel-Timestamp": timestamp,
            "Content-Type": "application/json",
        }

    async def _request_result(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        timeout: Optional[float] = None,
    ) -> Optional[Dict]:
        """发送请求并返回完整 JSON 响应。"""
        try:
            client = await self._get_client()
            request_kwargs = {"headers": self._get_headers()}
            if method.upper() != "GET":
                request_kwargs["json"] = data or {}
            if timeout is not None:
                request_kwargs["timeout"] = timeout

            response = await client.request(method.upper(), f"{self.host}{endpoint}", **request_kwargs)
            response.raise_for_status()
        except httpx.HTTPStatusError as e:
            status_code = e.response.status_code if e.response else "unknown"
            logger.error(f"HTTP 状态异常 [{endpoint}]: {status_code}")
            return None
        except httpx.HTTPError as e:
            logger.error(f"HTTP 请求异常 [{endpoint}]: {e}")
            return None

        try:
            result = response.json()
        except json.JSONDecodeError as e:
            response_preview = response.text[:200].replace("\n", " ").strip()
            logger.error(f"JSON 解析异常 [{endpoint}]: {e}; 响应片段: {response_preview}")
            return None

        if not isinstance(result, dict):
            logger.error(f"API 响应格式异常 [{endpoint}]: {type(result).__name__}")
            return None

        return result

    async def _request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Optional[Dict]:
        """统一请求方法，成功时返回 data 字段。"""
        result = await self._request_result(method, endpoint, data=data)
        if result is None:
            return None

        if result.get("code") != 200:
            logger.error(f"API 请求失败 [{endpoint}]: {result.get('message')} (code={result.get('code')})")
            return None

        response_data = result.get("data", {})
        if isinstance(response_data, dict):
            return response_data

        logger.error(f"API data 格式异常 [{endpoint}]: {type(response_data).__name__}")
        return None

    async def get_current_status(self, with_net_speed: bool = False) -> Optional[Dict]:
        """获取当前系统状态（CPU、内存、负载、磁盘等）。"""
        data = await self._request("GET", "/api/v2/dashboard/current/all/all")
        if data and with_net_speed:
            first_recv = data.get("netBytesRecv", 0)
            first_sent = data.get("netBytesSent", 0)

            await asyncio.sleep(1)

            data2 = await self._request("GET", "/api/v2/dashboard/current/all/all")
            if data2:
                data["netRecvSpeed"] = max(data2.get("netBytesRecv", 0) - first_recv, 0)
                data["netSentSpeed"] = max(data2.get("netBytesSent", 0) - first_sent, 0)
                data["netBytesRecv"] = data2.get("netBytesRecv", 0)
                data["netBytesSent"] = data2.get("netBytesSent", 0)

        return data

    async def get_dashboard_base(self) -> Optional[Dict]:
        """获取仪表盘基础信息。"""
        return await self._request("GET", "/api/v2/dashboard/base/all/all")

    async def get_containers(self, page: int = 1, page_size: int = 20) -> Optional[Dict]:
        """获取容器列表。"""
        return await self._request(
            "POST",
            "/api/v2/containers/search",
            {
                "page": page,
                "pageSize": page_size,
                "filters": "",
                "name": "",
                "state": "all",
                "orderBy": "name",
                "order": "null",
            },
        )

    async def operate_container(self, container_id: str, operation: str) -> tuple[bool, str]:
        """操作容器（启动/停止/重启）。"""
        result = await self._request_result(
            "POST",
            "/api/v2/containers/operate",
            data={"names": [container_id], "operation": operation},
            timeout=30,
        )
        if result is None:
            return False, "请求失败，请查看插件日志"

        if result.get("code") == 200:
            return True, "操作成功"

        error_message = result.get("message")
        if isinstance(error_message, str) and error_message.strip():
            return False, error_message

        return False, f"未知错误 (code={result.get('code', 'unknown')})"

    async def get_installed_apps(self, page: int = 1, page_size: int = 20) -> Optional[Dict]:
        """获取已安装应用列表。"""
        return await self._request(
            "POST",
            "/api/v2/apps/installed/search",
            {
                "page": page,
                "pageSize": page_size,
                "name": "",
                "tags": [],
                "update": False,
            },
        )

    async def get_ssh_logs(self, page: int = 1, page_size: int = 20, status: str = "All") -> Optional[Dict]:
        """获取 SSH 登录日志。"""
        return await self._request(
            "POST",
            "/api/v2/hosts/ssh/log",
            {"page": page, "pageSize": page_size, "status": status},
        )

    async def get_cronjobs(self, page: int = 1, page_size: int = 20) -> Optional[Dict]:
        """获取定时任务列表。"""
        return await self._request(
            "POST",
            "/api/v2/cronjobs/search",
            {
                "page": page,
                "pageSize": page_size,
                "orderBy": "name",
                "order": "null",
            },
        )

    async def get_firewall_rules(self, rule_type: str = "port", page: int = 1, page_size: int = 50) -> Optional[Dict]:
        """获取防火墙规则。"""
        return await self._request(
            "POST",
            "/api/v2/hosts/firewall/search",
            {"page": page, "pageSize": page_size, "type": rule_type},
        )
