#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AstrBot 1Panel 面板监控插件

功能：
1. 查看系统状态（CPU、内存、负载、磁盘）
2. 查看系统信息（主机名、版本、运行时间等）
3. 容器管理、应用管理、定时任务等

版本: 1.0.3
"""

import asyncio
import json
import time
import hashlib
from datetime import datetime
from typing import Dict, Optional

import httpx

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger


class OnePanelAPI:
    """1Panel 面板 API 封装（异步版本）
    
    使用共享的 HTTP 客户端以复用连接池，提高性能。
    """
    
    def __init__(self, host: str, api_key: str, verify_ssl: bool = False):
        """初始化 1Panel API
        
        Args:
            host: 1Panel 面板地址，如 http://192.168.1.1:10086
            api_key: API 密钥（在面板设置中获取）
            verify_ssl: 是否验证 SSL 证书（自签名证书需设为 False）
        """
        self.host = host.rstrip('/')
        self.api_key = api_key
        self.verify_ssl = verify_ssl
        self._client: Optional[httpx.AsyncClient] = None
        
        if not verify_ssl:
            logger.warning("SSL 证书验证已禁用，请确保在安全的网络环境中使用")
    
    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 HTTP 客户端（复用连接池）"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10, verify=self.verify_ssl)
        return self._client
    
    async def close(self):
        """关闭 HTTP 客户端"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    def _get_headers(self) -> Dict[str, str]:
        """生成请求头（包含认证信息）"""
        timestamp = str(int(time.time()))
        token_str = f"1panel{self.api_key}{timestamp}"
        token = hashlib.md5(token_str.encode()).hexdigest()
        
        return {
            "1Panel-Token": token,
            "1Panel-Timestamp": timestamp,
            "Content-Type": "application/json"
        }
    
    async def _request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Optional[Dict]:
        """统一的请求方法
        
        Args:
            method: HTTP 方法 (GET/POST)
            endpoint: API 端点
            data: POST 请求的数据
            
        Returns:
            API 返回的 data 字段，失败返回 None
        """
        try:
            client = await self._get_client()
            url = f"{self.host}{endpoint}"
            
            if method.upper() == "GET":
                response = await client.get(url, headers=self._get_headers())
            else:
                response = await client.post(url, headers=self._get_headers(), json=data or {})
            
            result = response.json()
            
            if result.get('code') == 200:
                return result.get('data', {})
            else:
                logger.error(f"API 请求失败 [{endpoint}]: {result.get('message')}")
                return None
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP 请求异常 [{endpoint}]: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析异常 [{endpoint}]: {e}")
            return None
        except Exception as e:
            logger.error(f"请求异常 [{endpoint}]: {e}")
            return None
    
    async def get_current_status(self, with_net_speed: bool = False) -> Optional[Dict]:
        """获取当前系统状态（CPU、内存、负载、磁盘等）"""
        data = await self._request("GET", "/api/v2/dashboard/current/all/all")
        
        if data and with_net_speed:
            first_recv = data.get('netBytesRecv', 0)
            first_sent = data.get('netBytesSent', 0)
            
            await asyncio.sleep(1)
            
            data2 = await self._request("GET", "/api/v2/dashboard/current/all/all")
            if data2:
                data['netRecvSpeed'] = data2.get('netBytesRecv', 0) - first_recv
                data['netSentSpeed'] = data2.get('netBytesSent', 0) - first_sent
                data['netBytesRecv'] = data2.get('netBytesRecv', 0)
                data['netBytesSent'] = data2.get('netBytesSent', 0)
        
        return data
    
    async def get_dashboard_base(self) -> Optional[Dict]:
        """获取仪表盘基础信息"""
        return await self._request("GET", "/api/v2/dashboard/base/all/all")
    
    async def get_containers(self, page: int = 1, page_size: int = 20) -> Optional[Dict]:
        """获取容器列表"""
        return await self._request("POST", "/api/v2/containers/search", {
            "page": page, "pageSize": page_size,
            "filters": "", "name": "", "state": "all",
            "orderBy": "name", "order": "null"
        })
    
    async def operate_container(self, container_id: str, operation: str) -> tuple[bool, str]:
        """操作容器（启动/停止/重启）"""
        try:
            client = await self._get_client()
            response = await client.post(
                f"{self.host}/api/v2/containers/operate",
                headers=self._get_headers(),
                json={"names": [container_id], "operation": operation},
                timeout=30
            )
            result = response.json()
            
            if result.get('code') == 200:
                return True, "操作成功"
            return False, result.get('message', '未知错误')
        except httpx.HTTPError as e:
            return False, f"网络错误: {e}"
        except Exception as e:
            return False, str(e)
    
    async def get_installed_apps(self, page: int = 1, page_size: int = 20) -> Optional[Dict]:
        """获取已安装应用列表"""
        return await self._request("POST", "/api/v2/apps/installed/search", {
            "page": page, "pageSize": page_size,
            "name": "", "tags": [], "update": False
        })
    
    async def get_ssh_logs(self, page: int = 1, page_size: int = 20, status: str = "All") -> Optional[Dict]:
        """获取 SSH 登录日志"""
        return await self._request("POST", "/api/v2/hosts/ssh/log", {
            "page": page, "pageSize": page_size, "status": status
        })
    
    async def get_cronjobs(self, page: int = 1, page_size: int = 20) -> Optional[Dict]:
        """获取定时任务列表"""
        return await self._request("POST", "/api/v2/cronjobs/search", {
            "page": page, "pageSize": page_size,
            "orderBy": "name", "order": "null"
        })
    
    async def get_firewall_rules(self, rule_type: str = "port", page: int = 1, page_size: int = 50) -> Optional[Dict]:
        """获取防火墙规则"""
        return await self._request("POST", "/api/v2/hosts/firewall/search", {
            "page": page, "pageSize": page_size, "type": rule_type
        })


def format_bytes(bytes_val: float) -> str:
    """格式化字节数为人类可读格式"""
    if bytes_val < 1024:
        return f"{bytes_val:.2f} B"
    elif bytes_val < 1024 ** 2:
        return f"{bytes_val / 1024:.2f} KB"
    elif bytes_val < 1024 ** 3:
        return f"{bytes_val / 1024 ** 2:.2f} MB"
    else:
        return f"{bytes_val / 1024 ** 3:.2f} GB"


def format_uptime(seconds: int) -> str:
    """格式化运行时间"""
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    
    parts = []
    if days > 0:
        parts.append(f"{days}天")
    if hours > 0:
        parts.append(f"{hours}小时")
    if minutes > 0:
        parts.append(f"{minutes}分钟")
    
    return " ".join(parts) if parts else "刚刚启动"


@register("astrbot_plugin_1panel", "Haitun", "1Panel 面板监控插件", "1.0.3")
class OnePanelPlugin(Star):
    """AstrBot 1Panel 插件主类"""
    
    def __init__(self, context: Context, config: dict):
        """初始化插件"""
        super().__init__(context)
        self.config = config
        
        panel_host = config.get("panel_host", "http://localhost:10086")
        panel_api_key = config.get("panel_api_key", "")
        verify_ssl = config.get("verify_ssl", False)
        
        # 权限管理配置
        self.enable_whitelist = config.get("enable_whitelist", False)
        self.whitelist_users = config.get("whitelist_users", [])
        
        self.panel_api = OnePanelAPI(panel_host, panel_api_key, verify_ssl)
        
        logger.info("1Panel 监控插件已加载")
        logger.info(f"  Host: {panel_host}")
        if self.enable_whitelist:
            logger.info(f"  权限管理: 已启用 (白名单用户: {len(self.whitelist_users)}个)")
        else:
            logger.info(f"  权限管理: 未启用 (所有用户可用)")
    
    def _check_permission(self, event: AstrMessageEvent) -> tuple[bool, str]:
        """检查用户权限
        
        Returns:
            (是否有权限, 错误消息)
        """
        # 如果未启用白名单，所有人都可以使用
        if not self.enable_whitelist:
            return True, ""
        
        # 获取用户ID
        user_id = event.get_sender_id()
        
        # 检查是否在白名单中
        if user_id in self.whitelist_users:
            return True, ""
        
        # 权限不足
        return False, f"❌ 权限不足\n\n您的ID: {user_id}\n此命令仅限授权用户使用"
    
    @filter.command("panel")
    async def panel_command(self, event: AstrMessageEvent):
        '''1Panel 面板监控命令，查看服务器状态和系统信息'''
        # 检查权限
        has_permission, error_msg = self._check_permission(event)
        if not has_permission:
            yield event.plain_result(error_msg)
            return
        
        if not self.panel_api.api_key:
            yield event.plain_result("❌ 插件未配置 API 密钥，请在插件设置中配置")
            return
        
        parts = event.message_str.strip().split()
        command = parts[1].lower() if len(parts) > 1 else "help"
        
        # 命令路由
        handlers = {
            "help": self._handle_help,
            "status": self._handle_status,
            "info": self._handle_info,
            "all": self._handle_all,
            "docker": self._handle_docker,
            "apps": self._handle_apps,
            "ssh": self._handle_ssh,
            "firewall": self._handle_firewall,
            "cron": self._handle_cron,
            "whoami": self._handle_whoami,
            "whitelist": self._handle_whitelist,
        }
        
        handler = handlers.get(command)
        if handler:
            async for result in handler(event, parts):
                yield result
        else:
            yield event.plain_result(f"❌ 未知命令: {command}\n使用 /panel 查看帮助")
    
    async def _handle_help(self, event: AstrMessageEvent, parts: list):
        """显示帮助信息"""
        help_text = """🖥️ 1Panel 面板监控插件 v1.0.3

📊 系统监控:
/panel status - 系统状态（CPU、内存、负载、磁盘）
/panel info - 系统信息（主机名、版本、运行时间）
/panel all - 全部信息

🐳 容器管理:
/panel docker - 查看容器列表
/panel docker start <名称> - 启动容器
/panel docker stop <名称> - 停止容器
/panel docker restart <名称> - 重启容器

📦 应用管理:
/panel apps - 查看已安装应用

🔐 安全相关:
/panel ssh [页码] - SSH 登录日志
/panel firewall - 防火墙端口规则

⏰ 定时任务:
/panel cron - 查看定时任务

👤 权限管理:
/panel whoami - 查看当前用户ID
/panel whitelist list - 查看白名单列表
/panel whitelist add <用户ID> - 添加白名单
/panel whitelist remove <用户ID> - 移除白名单"""
        
        # 如果启用了白名单，显示权限状态
        if self.enable_whitelist:
            user_id = event.get_sender_id()
            if user_id in self.whitelist_users:
                help_text += "\n\n✅ 您已获得授权"
            else:
                help_text += f"\n\n⚠️ 您的ID: {user_id}\n请联系管理员添加到白名单"
        
        yield event.plain_result(help_text)
    
    async def _handle_status(self, event: AstrMessageEvent, parts: list):
        """处理 status 命令"""
        status = await self.panel_api.get_current_status(with_net_speed=True)
        
        if not status:
            yield event.plain_result("❌ 获取系统状态失败，请检查配置")
            return
        
        result = "📊 系统状态\n\n"
        result += f"🔲 CPU: {status.get('cpuUsedPercent', 0):.2f}% ({status.get('cpuCores', 0)} 核)\n"
        
        mem_used = status.get('memoryUsedPercent', 0)
        mem_total = status.get('memoryTotal', 0)
        mem_used_bytes = status.get('memoryUsed', 0)
        result += f"💾 内存: {mem_used:.2f}% ({format_bytes(mem_used_bytes)} / {format_bytes(mem_total)})\n"
        
        load = status.get('load1', 0)
        load_status = "运行流畅" if load < 1 else ("负载较高" if load < 2 else "负载过高")
        result += f"⚡ 负载: {load:.2f} ({load_status})\n"
        
        for disk in status.get('diskData', []):
            path = disk.get('path', '/')
            result += f"💿 磁盘 {path}: {disk.get('usedPercent', 0):.2f}% ({format_bytes(disk.get('used', 0))} / {format_bytes(disk.get('total', 0))})\n"
        
        result += f"\n🌐 网络流量:\n"
        result += f"  ↑ 上行: {format_bytes(status.get('netSentSpeed', 0))}/s | 总发送: {format_bytes(status.get('netBytesSent', 0))}\n"
        result += f"  ↓ 下行: {format_bytes(status.get('netRecvSpeed', 0))}/s | 总接收: {format_bytes(status.get('netBytesRecv', 0))}\n"
        
        yield event.plain_result(result)
    
    async def _handle_info(self, event: AstrMessageEvent, parts: list):
        """处理 info 命令"""
        info = await self.panel_api.get_dashboard_base()
        
        if not info:
            yield event.plain_result("❌ 获取系统信息失败，请检查配置")
            return
        
        result = "📋 系统信息\n\n"
        result += f"🏠 主机名称: {info.get('hostname', '未知')}\n"
        
        os_info = info.get('prettyDistro') or f"{info.get('platform', '')} {info.get('platformVersion', '')}"
        result += f"🐧 发行版本: {os_info}\n"
        result += f"🔧 内核版本: {info.get('kernelVersion', '未知')}\n"
        result += f"🖥️ 系统类型: {info.get('kernelArch', '未知')}\n"
        result += f"🌐 主机地址: {info.get('ipV4Addr', '未知')}\n"
        
        # 解析运行时间
        virt_info = info.get('virtualizationSystem', '')
        if virt_info and isinstance(virt_info, str):
            try:
                virt_data = json.loads(virt_info)
                if boot_time := virt_data.get('bootTime', 0):
                    result += f"📅 启动时间: {datetime.fromtimestamp(boot_time).strftime('%Y-%m-%d %H:%M:%S')}\n"
                if uptime := virt_data.get('uptime', 0):
                    result += f"⏱️ 运行时间: {format_uptime(uptime)}\n"
            except json.JSONDecodeError:
                pass
        
        yield event.plain_result(result)
    
    async def _handle_all(self, event: AstrMessageEvent, parts: list):
        """处理 all 命令"""
        status = await self.panel_api.get_current_status(with_net_speed=True)
        info = await self.panel_api.get_dashboard_base()
        
        if not status and not info:
            yield event.plain_result("❌ 获取服务器信息失败，请检查配置")
            return
        
        result = "🖥️ 1Panel 服务器概览\n" + "=" * 20 + "\n\n"
        
        if info:
            result += f"🏠 主机名称: {info.get('hostname', '未知')}\n"
            os_info = info.get('prettyDistro') or f"{info.get('platform', '')} {info.get('platformVersion', '')}"
            result += f"🐧 发行版本: {os_info}\n"
            if kernel := info.get('kernelVersion'):
                result += f"🔧 内核版本: {kernel}\n"
            if arch := info.get('kernelArch'):
                result += f"🖥️ 系统类型: {arch}\n"
            if ip := info.get('ipV4Addr'):
                result += f"🌐 主机地址: {ip}\n"
            
            virt_info = info.get('virtualizationSystem', '')
            if virt_info and isinstance(virt_info, str):
                try:
                    virt_data = json.loads(virt_info)
                    if boot_time := virt_data.get('bootTime', 0):
                        result += f"📅 启动时间: {datetime.fromtimestamp(boot_time).strftime('%Y-%m-%d %H:%M:%S')}\n"
                    if uptime := virt_data.get('uptime', 0):
                        result += f"⏱️ 运行时间: {format_uptime(uptime)}\n"
                except json.JSONDecodeError:
                    pass
            result += "\n"
        
        if status:
            load = status.get('load1', 0)
            cpu_cores = status.get('cpuCores') or (info.get('cpuCores') if info else 0) or 1
            load_percent = (load / cpu_cores * 100) if cpu_cores > 0 else 0
            load_status = "运行流畅" if load < 1 else ("负载较高" if load < 2 else "负载过高")
            
            result += "📊 状态\n"
            result += f"  ⚡ 负载: {load_percent:.2f}% ({load_status})\n"
            result += f"  🔲 CPU: {status.get('cpuUsedPercent', 0):.2f}% ({cpu_cores} 核)\n"
            result += f"  💾 内存: {status.get('memoryUsedPercent', 0):.2f}% ({format_bytes(status.get('memoryUsed', 0))} / {format_bytes(status.get('memoryTotal', 0))})\n"
            
            for disk in status.get('diskData', []):
                result += f"  💿 磁盘 {disk.get('path', '/')}: {disk.get('usedPercent', 0):.2f}% ({format_bytes(disk.get('used', 0))} / {format_bytes(disk.get('total', 0))})\n"
            
            result += f"\n🌐 网络流量\n"
            result += f"  ↑ 上行: {format_bytes(status.get('netSentSpeed', 0))}/s | 总发送: {format_bytes(status.get('netBytesSent', 0))}\n"
            result += f"  ↓ 下行: {format_bytes(status.get('netRecvSpeed', 0))}/s | 总接收: {format_bytes(status.get('netBytesRecv', 0))}\n"
        
        yield event.plain_result(result)
    
    async def _handle_docker(self, event: AstrMessageEvent, parts: list):
        """处理 docker 命令"""
        sub_cmd = parts[2] if len(parts) > 2 else "list"
        
        # 操作容器
        if sub_cmd in ["start", "stop", "restart", "pause", "unpause"]:
            if len(parts) < 4:
                yield event.plain_result(f"❌ 请指定容器名称\n用法: /panel docker {sub_cmd} <容器名称>")
                return
            
            container_name = parts[3]
            success, message = await self.panel_api.operate_container(container_name, sub_cmd)
            
            if success:
                op_text = {"start": "启动", "stop": "停止", "restart": "重启", "pause": "暂停", "unpause": "恢复"}
                yield event.plain_result(f"✅ 容器 {container_name} {op_text.get(sub_cmd, sub_cmd)}成功")
            else:
                yield event.plain_result(f"❌ 操作失败: {message}")
            return
        
        # 查看容器列表
        data = await self.panel_api.get_containers()
        
        if not data:
            yield event.plain_result("❌ 获取容器列表失败")
            return
        
        items = data.get('items', [])
        total = data.get('total', 0)
        
        if not items:
            yield event.plain_result("📦 暂无容器")
            return
        
        result = f"🐳 容器列表 (共 {total} 个)\n\n"
        state_icons = {"running": "🟢", "exited": "🔴", "paused": "🟡", "created": "⚪"}
        
        for c in items[:15]:
            state = c.get('state', '未知')
            result += f"{state_icons.get(state, '⚫')} {c.get('name', '未知')}\n"
            result += f"   镜像: {c.get('imageName', '').split('/')[-1][:20]}\n"
        
        if total > 15:
            result += f"\n... 还有 {total - 15} 个容器"
        
        result += "\n\n💡 操作容器:\n"
        result += "/panel docker start <名称>\n"
        result += "/panel docker stop <名称>\n"
        result += "/panel docker restart <名称>"
        yield event.plain_result(result)
    
    async def _handle_apps(self, event: AstrMessageEvent, parts: list):
        """处理 apps 命令"""
        data = await self.panel_api.get_installed_apps()
        
        if not data:
            yield event.plain_result("❌ 获取应用列表失败")
            return
        
        items = data.get('items', [])
        total = data.get('total', 0)
        
        if not items:
            yield event.plain_result("📦 暂无已安装应用")
            return
        
        result = f"📦 已安装应用 (共 {total} 个)\n\n"
        status_icons = {"Running": "🟢", "Stopped": "🔴", "Installing": "🔄", "Error": "❌"}
        
        for app in items:
            name = app.get('name', '未知')
            app_name = app.get('app', {}).get('name', '') or app.get('appName', '')
            status = app.get('status', '未知')
            version = app.get('version', '')
            
            result += f"{status_icons.get(status, '⚫')} {name}"
            if app_name and app_name != name:
                result += f" ({app_name})"
            if version:
                result += f" v{version}"
            result += "\n"
        
        yield event.plain_result(result)
    
    async def _handle_ssh(self, event: AstrMessageEvent, parts: list):
        """处理 ssh 命令"""
        page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
        status_filter = parts[3] if len(parts) > 3 else "All"
        
        data = await self.panel_api.get_ssh_logs(page=page, page_size=10, status=status_filter)
        
        if not data:
            yield event.plain_result("❌ 获取 SSH 日志失败")
            return
        
        logs = data.get('logs', [])
        total = data.get('total', 0)
        
        if not logs:
            yield event.plain_result("📋 暂无 SSH 登录记录")
            return
        
        result = f"🔐 SSH 登录日志 (第 {page} 页，共 {total} 条)\n\n"
        
        for log_entry in logs:
            status_icon = "✅" if log_entry.get('status') == "Success" else "❌"
            result += f"{status_icon} {log_entry.get('date', '')}\n"
            result += f"   {log_entry.get('user', 'root')}@{log_entry.get('address', '未知')}\n"
        
        result += f"\n💡 翻页: /panel ssh <页码>"
        yield event.plain_result(result)
    
    async def _handle_firewall(self, event: AstrMessageEvent, parts: list):
        """处理 firewall 命令"""
        rule_type = parts[2] if len(parts) > 2 else "port"
        
        data = await self.panel_api.get_firewall_rules(rule_type=rule_type)
        
        if not data:
            yield event.plain_result("❌ 获取防火墙规则失败")
            return
        
        items = data.get('items', [])
        total = data.get('total', 0)
        
        if not items:
            yield event.plain_result("🔥 暂无防火墙规则")
            return
        
        result = f"🔥 防火墙规则 (共 {total} 条)\n\n"
        
        for rule in items[:20]:
            strategy = rule.get('strategy', '')
            icon = "✅" if strategy == "accept" else "🚫"
            
            if rule_type == "port":
                port = rule.get('port', '')
                protocol = rule.get('protocol', 'tcp')
                desc = rule.get('description', '')
                result += f"{icon} {port}/{protocol}"
                if desc:
                    result += f" - {desc}"
                result += "\n"
            else:
                result += f"{icon} {rule.get('address', '')}\n"
        
        if total > 20:
            result += f"\n... 还有 {total - 20} 条规则"
        
        yield event.plain_result(result)
    
    async def _handle_cron(self, event: AstrMessageEvent, parts: list):
        """处理 cron 命令"""
        data = await self.panel_api.get_cronjobs()
        
        if not data:
            yield event.plain_result("❌ 获取定时任务失败")
            return
        
        items = data.get('items', [])
        total = data.get('total', 0)
        
        if not items:
            yield event.plain_result("⏰ 暂无定时任务")
            return
        
        result = f"⏰ 定时任务 (共 {total} 个)\n\n"
        
        for job in items:
            status_icon = "🟢" if job.get('status') == "Enable" else "🔴"
            result += f"{status_icon} {job.get('name', '未知')}\n"
            result += f"   类型: {job.get('type', '')} | {job.get('spec', '')}\n"
        
        yield event.plain_result(result)
    
    async def _handle_whoami(self, event: AstrMessageEvent, parts: list):
        """处理 whoami 命令 - 查看当前用户ID和权限状态"""
        user_id = event.get_sender_id()
        
        result = "👤 用户信息\n\n"
        result += f"用户ID: {user_id}\n"
        
        if self.enable_whitelist:
            if user_id in self.whitelist_users:
                result += "权限状态: ✅ 已授权\n"
                result += f"白名单用户数: {len(self.whitelist_users)}个"
            else:
                result += "权限状态: ❌ 未授权\n"
                result += "\n💡 如需使用此插件，请联系管理员将您的ID添加到白名单"
        else:
            result += "权限状态: ✅ 所有用户可用\n"
            result += "（管理员未启用白名单）"
        
        yield event.plain_result(result)
    
    async def _handle_whitelist(self, event: AstrMessageEvent, parts: list):
        """处理 whitelist 命令 - 白名单管理（仅白名单用户可用）"""
        # 白名单管理命令本身也需要权限检查
        # 但这里我们允许所有人查看自己的状态，只有操作需要权限
        
        if len(parts) < 3:
            yield event.plain_result("❌ 请指定子命令\n\n用法:\n/panel whitelist list - 查看白名单\n/panel whitelist add <用户ID> - 添加用户\n/panel whitelist remove <用户ID> - 移除用户")
            return
        
        sub_cmd = parts[2].lower()
        
        if sub_cmd == "list":
            # 查看白名单列表
            if not self.enable_whitelist:
                yield event.plain_result("ℹ️ 白名单功能未启用\n\n所有用户都可以使用此插件")
                return
            
            if not self.whitelist_users:
                yield event.plain_result("📋 白名单列表\n\n当前白名单为空")
                return
            
            result = f"📋 白名单列表 (共 {len(self.whitelist_users)} 个用户)\n\n"
            for idx, uid in enumerate(self.whitelist_users, 1):
                result += f"{idx}. {uid}\n"
            
            yield event.plain_result(result)
            return
        
        # add 和 remove 需要权限
        if sub_cmd in ["add", "remove"]:
            # 检查操作者是否有权限
            operator_id = event.get_sender_id()
            if self.enable_whitelist and operator_id not in self.whitelist_users:
                yield event.plain_result(f"❌ 权限不足\n\n只有白名单用户才能管理白名单\n您的ID: {operator_id}")
                return
            
            if len(parts) < 4:
                yield event.plain_result(f"❌ 请指定用户ID\n\n用法: /panel whitelist {sub_cmd} <用户ID>")
                return
            
            target_user_id = parts[3]
            
            if sub_cmd == "add":
                # 添加到白名单
                if target_user_id in self.whitelist_users:
                    yield event.plain_result(f"ℹ️ 用户 {target_user_id} 已在白名单中")
                    return
                
                self.whitelist_users.append(target_user_id)
                self._save_whitelist()
                
                yield event.plain_result(f"✅ 已将用户 {target_user_id} 添加到白名单\n\n当前白名单用户数: {len(self.whitelist_users)}个")
                return
            
            elif sub_cmd == "remove":
                # 从白名单移除
                if target_user_id not in self.whitelist_users:
                    yield event.plain_result(f"ℹ️ 用户 {target_user_id} 不在白名单中")
                    return
                
                # 防止移除自己
                if target_user_id == operator_id:
                    yield event.plain_result("❌ 不能移除自己")
                    return
                
                self.whitelist_users.remove(target_user_id)
                self._save_whitelist()
                
                yield event.plain_result(f"✅ 已将用户 {target_user_id} 从白名单移除\n\n当前白名单用户数: {len(self.whitelist_users)}个")
                return
        
        yield event.plain_result(f"❌ 未知子命令: {sub_cmd}\n\n可用命令: list, add, remove")
    
    def _save_whitelist(self):
        """保存白名单到配置文件"""
        try:
            # 更新内存中的配置
            self.config["whitelist_users"] = self.whitelist_users
            
            # 保存到配置文件
            # AstrBot 会自动处理配置持久化
            self.context.update_config(self.config)
            
            logger.info(f"白名单已更新，当前用户数: {len(self.whitelist_users)}")
        except Exception as e:
            logger.error(f"保存白名单失败: {e}")
    
    async def terminate(self):
        """插件卸载时调用"""
        await self.panel_api.close()
        logger.info("1Panel 监控插件已卸载")
