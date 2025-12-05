#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AstrBot 1Panel 面板监控插件

功能：
1. 查看系统状态（CPU、内存、负载、磁盘）
2. 查看系统信息（主机名、版本、运行时间等）

版本: 1.0.0
"""

import time
import hashlib
from typing import Dict, Optional

import httpx

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger


class OnePanelAPI:
    """1Panel 面板 API 封装（异步版本）"""
    
    def __init__(self, host: str, api_key: str):
        """初始化 1Panel API
        
        Args:
            host: 1Panel 面板地址，如 http://192.168.1.1:10086
            api_key: API 密钥（在面板设置中获取）
        """
        self.host = host.rstrip('/')
        self.api_key = api_key
    
    def _get_headers(self) -> Dict[str, str]:
        """生成请求头（包含认证信息）"""
        timestamp = str(int(time.time()))
        # Token = md5('1panel' + API-Key + UnixTimestamp)
        token_str = f"1panel{self.api_key}{timestamp}"
        token = hashlib.md5(token_str.encode()).hexdigest()
        
        return {
            "1Panel-Token": token,
            "1Panel-Timestamp": timestamp,
            "Content-Type": "application/json"
        }
    
    async def get_current_status(self, with_net_speed: bool = False) -> Optional[Dict]:
        """获取当前系统状态（CPU、内存、负载、磁盘等）
        
        API: GET /api/v2/dashboard/current/:ioOption/:netOption
        
        Args:
            with_net_speed: 是否计算网络速率（需要两次请求，间隔1秒）
        """
        try:
            url = f"{self.host}/api/v2/dashboard/current/all/all"
            
            async with httpx.AsyncClient(timeout=10, verify=False) as client:
                response = await client.get(url, headers=self._get_headers())
                result = response.json()
            
            if result.get('code') != 200:
                logger.error(f"获取系统状态失败: {result.get('message')}")
                return None
            
            data = result.get('data', {})
            
            # 计算网络速率
            if with_net_speed:
                import asyncio
                first_recv = data.get('netBytesRecv', 0)
                first_sent = data.get('netBytesSent', 0)
                
                await asyncio.sleep(1)
                
                async with httpx.AsyncClient(timeout=10, verify=False) as client:
                    response2 = await client.get(url, headers=self._get_headers())
                    result2 = response2.json()
                
                if result2.get('code') == 200:
                    data2 = result2.get('data', {})
                    second_recv = data2.get('netBytesRecv', 0)
                    second_sent = data2.get('netBytesSent', 0)
                    
                    # 计算每秒速率
                    data['netRecvSpeed'] = second_recv - first_recv
                    data['netSentSpeed'] = second_sent - first_sent
                    # 使用最新的总流量
                    data['netBytesRecv'] = second_recv
                    data['netBytesSent'] = second_sent
            
            return data
        
        except Exception as e:
            logger.error(f"获取系统状态异常: {e}")
            return None
    
    async def get_system_info(self) -> Optional[Dict]:
        """获取系统基本信息
        
        API: POST /api/v2/toolbox/device/base
        """
        try:
            url = f"{self.host}/api/v2/toolbox/device/base"
            
            async with httpx.AsyncClient(timeout=10, verify=False) as client:
                response = await client.post(url, headers=self._get_headers())
                result = response.json()
            
            if result.get('code') == 200:
                return result.get('data', {})
            else:
                logger.error(f"获取系统信息失败: {result.get('message')}")
                return None
        
        except Exception as e:
            logger.error(f"获取系统信息异常: {e}")
            return None
    
    async def get_dashboard_base(self) -> Optional[Dict]:
        """获取仪表盘基础信息（包含系统版本、运行时间等）
        
        API: GET /api/v2/dashboard/base/:ioOption/:netOption
        """
        try:
            url = f"{self.host}/api/v2/dashboard/base/all/all"
            
            async with httpx.AsyncClient(timeout=10, verify=False) as client:
                response = await client.get(url, headers=self._get_headers())
                result = response.json()
            
            if result.get('code') == 200:
                return result.get('data', {})
            else:
                logger.error(f"获取仪表盘信息失败: {result.get('message')}")
                return None
        
        except Exception as e:
            logger.error(f"获取仪表盘信息异常: {e}")
            return None
    
    async def get_containers(self, page: int = 1, page_size: int = 20) -> Optional[Dict]:
        """获取容器列表
        
        API: POST /api/v2/containers/search
        """
        try:
            url = f"{self.host}/api/v2/containers/search"
            data = {
                "page": page,
                "pageSize": page_size,
                "filters": "",
                "name": "",
                "state": "all",
                "orderBy": "name",
                "order": "null"
            }
            
            logger.debug(f"请求容器列表: {url}")
            async with httpx.AsyncClient(timeout=10, verify=False) as client:
                response = await client.post(url, headers=self._get_headers(), json=data)
                logger.debug(f"容器列表响应状态: {response.status_code}")
                result = response.json()
                logger.debug(f"容器列表响应: {result}")
            
            if result.get('code') == 200:
                return result.get('data', {})
            else:
                logger.error(f"获取容器列表失败: code={result.get('code')}, message={result.get('message')}")
                return None
        
        except Exception as e:
            logger.error(f"获取容器列表异常: {e}", exc_info=True)
            return None
    
    async def operate_container(self, container_id: str, operation: str) -> tuple[bool, str]:
        """操作容器（启动/停止/重启）
        
        API: POST /api/v2/containers/operate
        operation: start, stop, restart, pause, unpause
        
        Returns:
            (success, message)
        """
        try:
            url = f"{self.host}/api/v2/containers/operate"
            data = {
                "names": [container_id],
                "operation": operation
            }
            
            logger.debug(f"操作容器: {data}")
            async with httpx.AsyncClient(timeout=30, verify=False) as client:
                response = await client.post(url, headers=self._get_headers(), json=data)
                result = response.json()
                logger.debug(f"操作容器响应: {result}")
            
            if result.get('code') == 200:
                return True, "操作成功"
            else:
                return False, result.get('message', '未知错误')
        
        except Exception as e:
            logger.error(f"操作容器异常: {e}")
            return False, str(e)
    
    async def get_installed_apps(self, page: int = 1, page_size: int = 20) -> Optional[Dict]:
        """获取已安装应用列表
        
        API: POST /api/v2/apps/installed/search
        """
        try:
            url = f"{self.host}/api/v2/apps/installed/search"
            data = {
                "page": page,
                "pageSize": page_size,
                "name": "",
                "tags": [],
                "update": False
            }
            
            async with httpx.AsyncClient(timeout=10, verify=False) as client:
                response = await client.post(url, headers=self._get_headers(), json=data)
                result = response.json()
            
            if result.get('code') == 200:
                return result.get('data', {})
            else:
                logger.error(f"获取应用列表失败: {result.get('message')}")
                return None
        
        except Exception as e:
            logger.error(f"获取应用列表异常: {e}")
            return None
    
    async def get_ssh_logs(self, page: int = 1, page_size: int = 20, status: str = "All") -> Optional[Dict]:
        """获取 SSH 登录日志
        
        API: POST /api/v2/hosts/ssh/log
        status: All, Success, Failed
        """
        try:
            url = f"{self.host}/api/v2/hosts/ssh/log"
            data = {
                "page": page,
                "pageSize": page_size,
                "status": status
            }
            
            async with httpx.AsyncClient(timeout=10, verify=False) as client:
                response = await client.post(url, headers=self._get_headers(), json=data)
                result = response.json()
            
            if result.get('code') == 200:
                return result.get('data', {})
            else:
                logger.error(f"获取SSH日志失败: {result.get('message')}")
                return None
        
        except Exception as e:
            logger.error(f"获取SSH日志异常: {e}")
            return None
    
    async def get_cronjobs(self, page: int = 1, page_size: int = 20) -> Optional[Dict]:
        """获取定时任务列表
        
        API: POST /api/v2/cronjobs/search
        """
        try:
            url = f"{self.host}/api/v2/cronjobs/search"
            data = {
                "page": page,
                "pageSize": page_size,
                "orderBy": "name",
                "order": "null"
            }
            
            async with httpx.AsyncClient(timeout=10, verify=False) as client:
                response = await client.post(url, headers=self._get_headers(), json=data)
                result = response.json()
            
            if result.get('code') == 200:
                return result.get('data', {})
            else:
                logger.error(f"获取定时任务失败: {result.get('message')}")
                return None
        
        except Exception as e:
            logger.error(f"获取定时任务异常: {e}")
            return None
    
    async def get_firewall_rules(self, rule_type: str = "port", page: int = 1, page_size: int = 50) -> Optional[Dict]:
        """获取防火墙规则
        
        API: POST /api/v2/hosts/firewall/search
        rule_type: port, address
        """
        try:
            url = f"{self.host}/api/v2/hosts/firewall/search"
            data = {
                "page": page,
                "pageSize": page_size,
                "type": rule_type
            }
            
            async with httpx.AsyncClient(timeout=10, verify=False) as client:
                response = await client.post(url, headers=self._get_headers(), json=data)
                result = response.json()
            
            if result.get('code') == 200:
                return result.get('data', {})
            else:
                logger.error(f"获取防火墙规则失败: {result.get('message')}")
                return None
        
        except Exception as e:
            logger.error(f"获取防火墙规则异常: {e}")
            return None


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


@register("astrbot_plugin_1panel", "Your Name", "1Panel 面板监控插件", "1.0.0")
class OnePanelPlugin(Star):
    """AstrBot 1Panel 插件主类"""
    
    def __init__(self, context: Context, config: dict):
        """初始化插件"""
        super().__init__(context)
        self.config = config
        
        # 读取配置项
        panel_host = config.get("panel_host", "http://localhost:10086")
        panel_api_key = config.get("panel_api_key", "")
        
        # 初始化 1Panel API
        self.panel_api = OnePanelAPI(panel_host, panel_api_key)
        
        logger.info("1Panel 监控插件已加载")
        logger.info(f"  Host: {panel_host}")
    
    @filter.command("panel")
    async def panel_command(self, event: AstrMessageEvent):
        '''1Panel 面板监控命令，查看服务器状态和系统信息'''
        if not self.panel_api.api_key:
            yield event.plain_result("❌ 插件未配置 API 密钥，请在插件设置中配置")
            return
        
        message = event.message_str.strip()
        parts = message.split()
        
        # 默认显示帮助
        if len(parts) < 2:
            help_text = """🖥️ 1Panel 面板监控插件 v1.0

📊 系统监控:
/panel status - 系统状态（CPU、内存、负载、磁盘）
/panel info - 系统信息（主机名、版本、运行时间）
/panel all - 全部信息

🐳 容器管理:
/panel docker - 查看容器列表
/panel docker start/stop/restart <名称> - 操作容器

📦 应用管理:
/panel apps - 查看已安装应用

🔐 安全相关:
/panel ssh [页码] - SSH 登录日志
/panel firewall - 防火墙端口规则

⏰ 定时任务:
/panel cron - 查看定时任务"""
            yield event.plain_result(help_text)
            return
        
        command = parts[1].lower()
        
        # 查看系统状态
        if command == "status":
            status = await self.panel_api.get_current_status(with_net_speed=True)
            
            if not status:
                yield event.plain_result("❌ 获取系统状态失败，请检查配置")
                return
            
            result = "📊 系统状态\n\n"
            
            # CPU 使用率
            cpu_used = status.get('cpuUsedPercent', 0)
            cpu_cores = status.get('cpuCores', 0)
            result += f"🔲 CPU: {cpu_used:.2f}% ({cpu_cores} 核)\n"
            
            # 内存使用
            mem_used = status.get('memoryUsedPercent', 0)
            mem_total = status.get('memoryTotal', 0)
            mem_used_bytes = status.get('memoryUsed', 0)
            result += f"💾 内存: {mem_used:.2f}% ({format_bytes(mem_used_bytes)} / {format_bytes(mem_total)})\n"
            
            # 负载
            load = status.get('load1', 0)
            load_status = "运行流畅" if load < 1 else ("负载较高" if load < 2 else "负载过高")
            result += f"⚡ 负载: {load:.2f} ({load_status})\n"
            
            # 磁盘使用
            disk_data = status.get('diskData', [])
            if disk_data:
                for disk in disk_data:
                    path = disk.get('path', '/')
                    used_percent = disk.get('usedPercent', 0)
                    total = disk.get('total', 0)
                    used = disk.get('used', 0)
                    result += f"💿 磁盘 {path}: {used_percent:.2f}% ({format_bytes(used)} / {format_bytes(total)})\n"
            
            # 网络 IO
            net_bytes_recv = status.get('netBytesRecv', 0)
            net_bytes_sent = status.get('netBytesSent', 0)
            net_recv_speed = status.get('netRecvSpeed', 0)
            net_sent_speed = status.get('netSentSpeed', 0)
            result += f"\n🌐 网络流量:\n"
            result += f"  ↑ 上行: {format_bytes(net_sent_speed)}/s | 总发送: {format_bytes(net_bytes_sent)}\n"
            result += f"  ↓ 下行: {format_bytes(net_recv_speed)}/s | 总接收: {format_bytes(net_bytes_recv)}\n"
            
            yield event.plain_result(result)
        
        # 查看系统信息
        elif command == "info":
            # 从 dashboard base API 获取完整系统信息
            info = await self.panel_api.get_dashboard_base()
            
            if not info:
                yield event.plain_result("❌ 获取系统信息失败，请检查配置")
                return
            
            result = "📋 系统信息\n\n"
            
            # 主机名
            hostname = info.get('hostname', '未知')
            result += f"🏠 主机名称: {hostname}\n"
            
            # 发行版本 (使用 prettyDistro，如 "Debian GNU/Linux 12")
            os_info = info.get('prettyDistro') or f"{info.get('platform', '')} {info.get('platformVersion', '')}"
            result += f"🐧 发行版本: {os_info}\n"
            
            # 内核版本
            kernel = info.get('kernelVersion', '未知')
            result += f"🔧 内核版本: {kernel}\n"
            
            # 系统架构
            arch = info.get('kernelArch', '未知')
            result += f"🖥️ 系统类型: {arch}\n"
            
            # IP 地址
            ip = info.get('ipV4Addr', '未知')
            result += f"🌐 主机地址: {ip}\n"
            
            # 解析 virtualizationSystem 中的 uptime 和 bootTime
            virt_info = info.get('virtualizationSystem', '')
            uptime = 0
            boot_time = 0
            if virt_info and isinstance(virt_info, str):
                try:
                    import json
                    virt_data = json.loads(virt_info)
                    uptime = virt_data.get('uptime', 0)
                    boot_time = virt_data.get('bootTime', 0)
                except:
                    pass
            
            # 启动时间
            if boot_time > 0:
                from datetime import datetime
                boot_dt = datetime.fromtimestamp(boot_time)
                result += f"📅 启动时间: {boot_dt.strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            # 运行时间
            if uptime > 0:
                result += f"⏱️ 运行时间: {format_uptime(uptime)}\n"
            
            yield event.plain_result(result)
        
        # 查看全部信息
        elif command == "all":
            # 获取状态和基础信息
            status = await self.panel_api.get_current_status(with_net_speed=True)
            info = await self.panel_api.get_dashboard_base()
            
            result = "🖥️ 1Panel 服务器概览\n"
            result += "=" * 20 + "\n\n"
            
            # 系统信息
            if info:
                hostname = info.get('hostname', '未知')
                os_info = info.get('prettyDistro') or f"{info.get('platform', '')} {info.get('platformVersion', '')}"
                kernel = info.get('kernelVersion', '')
                arch = info.get('kernelArch', '')
                ip = info.get('ipV4Addr', '')
                
                # 解析运行时间
                virt_info = info.get('virtualizationSystem', '')
                uptime = 0
                boot_time = 0
                if virt_info and isinstance(virt_info, str):
                    try:
                        import json
                        virt_data = json.loads(virt_info)
                        uptime = virt_data.get('uptime', 0)
                        boot_time = virt_data.get('bootTime', 0)
                    except:
                        pass
                
                result += f"🏠 主机名称: {hostname}\n"
                result += f"🐧 发行版本: {os_info}\n"
                if kernel:
                    result += f"🔧 内核版本: {kernel}\n"
                if arch:
                    result += f"🖥️ 系统类型: {arch}\n"
                if ip:
                    result += f"🌐 主机地址: {ip}\n"
                if boot_time > 0:
                    from datetime import datetime
                    boot_dt = datetime.fromtimestamp(boot_time)
                    result += f"📅 启动时间: {boot_dt.strftime('%Y-%m-%d %H:%M:%S')}\n"
                if uptime > 0:
                    result += f"⏱️ 运行时间: {format_uptime(uptime)}\n"
                result += "\n"
            
            # 系统状态
            if status:
                # 按照 1Panel 面板的顺序：负载、CPU、内存、磁盘
                load = status.get('load1', 0)
                cpu_cores = status.get('cpuCores') or (info.get('cpuCores') if info else 0) or 1
                load_percent = (load / cpu_cores * 100) if cpu_cores > 0 else 0
                load_status = "运行流畅" if load < 1 else ("负载较高" if load < 2 else "负载过高")
                
                cpu_used = status.get('cpuUsedPercent', 0)
                mem_used = status.get('memoryUsedPercent', 0)
                mem_total = status.get('memoryTotal', 0)
                mem_used_bytes = status.get('memoryUsed', 0)
                
                result += "📊 状态\n"
                result += f"  ⚡ 负载: {load_percent:.2f}% ({load_status})\n"
                result += f"  🔲 CPU: {cpu_used:.2f}% ({cpu_cores} 核)\n"
                result += f"  💾 内存: {mem_used:.2f}% ({format_bytes(mem_used_bytes)} / {format_bytes(mem_total)})\n"
                
                disk_data = status.get('diskData', [])
                if disk_data:
                    for disk in disk_data:
                        path = disk.get('path', '/')
                        used_percent = disk.get('usedPercent', 0)
                        total = disk.get('total', 0)
                        used = disk.get('used', 0)
                        result += f"  💿 磁盘 {path}: {used_percent:.2f}% ({format_bytes(used)} / {format_bytes(total)})\n"
                
                # 网络流量
                net_bytes_recv = status.get('netBytesRecv', 0)
                net_bytes_sent = status.get('netBytesSent', 0)
                net_recv_speed = status.get('netRecvSpeed', 0)
                net_sent_speed = status.get('netSentSpeed', 0)
                result += f"\n🌐 网络流量\n"
                result += f"  ↑ 上行: {format_bytes(net_sent_speed)}/s | 总发送: {format_bytes(net_bytes_sent)}\n"
                result += f"  ↓ 下行: {format_bytes(net_recv_speed)}/s | 总接收: {format_bytes(net_bytes_recv)}\n"
            
            if not status and not info:
                result = "❌ 获取服务器信息失败，请检查配置"
            
            yield event.plain_result(result)
        
        # 容器管理
        elif command == "docker":
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
            
            for c in items[:15]:  # 最多显示15个
                name = c.get('name', '未知')
                state = c.get('state', '未知')
                image = c.get('imageName', '').split('/')[-1][:20]  # 简化镜像名
                
                # 状态图标
                state_icon = {
                    "running": "🟢",
                    "exited": "🔴",
                    "paused": "🟡",
                    "created": "⚪"
                }.get(state, "⚫")
                
                result += f"{state_icon} {name}\n"
                result += f"   镜像: {image}\n"
            
            if total > 15:
                result += f"\n... 还有 {total - 15} 个容器"
            
            result += "\n\n💡 操作: /panel docker start|stop|restart <名称>"
            yield event.plain_result(result)
        
        # 应用管理
        elif command == "apps":
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
            
            for app in items:
                name = app.get('name', '未知')
                app_name = app.get('app', {}).get('name', '') or app.get('appName', '')
                status = app.get('status', '未知')
                version = app.get('version', '')
                
                # 状态图标
                status_icon = {
                    "Running": "🟢",
                    "Stopped": "🔴",
                    "Installing": "🔄",
                    "Error": "❌"
                }.get(status, "⚫")
                
                result += f"{status_icon} {name}"
                if app_name and app_name != name:
                    result += f" ({app_name})"
                if version:
                    result += f" v{version}"
                result += "\n"
            
            yield event.plain_result(result)
        
        # SSH 登录日志
        elif command == "ssh":
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
            
            for log in logs:
                date = log.get('date', '')
                ip = log.get('address', '未知')
                user = log.get('user', 'root')
                status = log.get('status', '')
                
                status_icon = "✅" if status == "Success" else "❌"
                result += f"{status_icon} {date}\n"
                result += f"   {user}@{ip}\n"
            
            result += f"\n💡 翻页: /panel ssh <页码>"
            yield event.plain_result(result)
        
        # 防火墙规则
        elif command == "firewall":
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
                if rule_type == "port":
                    port = rule.get('port', '')
                    protocol = rule.get('protocol', 'tcp')
                    strategy = rule.get('strategy', '')
                    desc = rule.get('description', '')
                    
                    icon = "✅" if strategy == "accept" else "🚫"
                    result += f"{icon} {port}/{protocol}"
                    if desc:
                        result += f" - {desc}"
                    result += "\n"
                else:  # address
                    addr = rule.get('address', '')
                    strategy = rule.get('strategy', '')
                    icon = "✅" if strategy == "accept" else "🚫"
                    result += f"{icon} {addr}\n"
            
            if total > 20:
                result += f"\n... 还有 {total - 20} 条规则"
            
            yield event.plain_result(result)
        
        # 定时任务
        elif command == "cron":
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
                name = job.get('name', '未知')
                job_type = job.get('type', '')
                status = job.get('status', '')
                spec = job.get('spec', '')
                
                status_icon = "🟢" if status == "Enable" else "🔴"
                result += f"{status_icon} {name}\n"
                result += f"   类型: {job_type} | {spec}\n"
            
            yield event.plain_result(result)
        
        # 调试命令 - 查看原始 API 响应
        elif command == "debug":
            sub_cmd = parts[2] if len(parts) > 2 else "base"
            
            if sub_cmd == "status":
                data = await self.panel_api.get_current_status()
            elif sub_cmd == "info":
                data = await self.panel_api.get_system_info()
            else:  # base
                data = await self.panel_api.get_dashboard_base()
            
            if data:
                import json
                data_str = json.dumps(data, ensure_ascii=False, indent=2)
                if len(data_str) > 1500:
                    data_str = data_str[:1500] + "\n..."
                yield event.plain_result(f"📋 API 响应 ({sub_cmd}):\n```\n{data_str}\n```\n\n💡 可用: /panel debug base|status|info")
            else:
                yield event.plain_result(f"❌ 获取 {sub_cmd} 失败")
        
        else:
            yield event.plain_result(f"❌ 未知命令: {command}\n使用 /panel 查看帮助")
    
    async def terminate(self):
        """插件卸载时调用"""
        logger.info("1Panel 监控插件已卸载")
