#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from formatters import build_system_info_lines, format_bytes


def normalize_user_id(user_id: object) -> str:
    """统一用户 ID 格式，避免字符串/整数混用导致权限判断失效。"""
    return str(user_id).strip()


def normalize_user_ids(user_ids: object) -> list[str]:
    """归一化白名单并去重，同时保持原有顺序。"""
    normalized_users: list[str] = []
    seen: set[str] = set()

    for user_id in user_ids or []:
        normalized_user_id = normalize_user_id(user_id)
        if normalized_user_id and normalized_user_id not in seen:
            seen.add(normalized_user_id)
            normalized_users.append(normalized_user_id)

    return normalized_users


class PanelCommandHandlers:
    """命令处理与权限逻辑。"""

    def __init__(self, plugin: Any):
        self.plugin = plugin

    def _get_user_id(self, event: AstrMessageEvent) -> str:
        return normalize_user_id(event.get_sender_id())

    def _is_whitelisted(self, user_id: str) -> bool:
        return user_id in self.plugin._whitelist_lookup

    def _refresh_whitelist_cache(self):
        self.plugin.whitelist_users = normalize_user_ids(self.plugin.whitelist_users)
        self.plugin._whitelist_lookup = set(self.plugin.whitelist_users)

    def _check_permission(self, event: AstrMessageEvent) -> tuple[bool, str]:
        if not self.plugin.enable_whitelist:
            return True, ""

        user_id = self._get_user_id(event)
        if self._is_whitelisted(user_id):
            return True, ""

        return False, f"❌ 权限不足\n\n您的ID: {user_id}\n此命令仅限授权用户使用"

    def _save_whitelist(self):
        try:
            self._refresh_whitelist_cache()
            self.plugin.config["whitelist_users"] = list(self.plugin.whitelist_users)
            self.plugin.context.update_config(self.plugin.config)
            logger.info(f"白名单已更新，当前用户数: {len(self.plugin.whitelist_users)}")
        except Exception as e:
            logger.error(f"保存白名单失败: {e}")

    async def handle_panel_command(self, event: AstrMessageEvent):
        parts = event.message_str.strip().split()
        command = parts[1].lower() if len(parts) > 1 else "help"

        commands_without_global_permission = {"help", "whoami", "whitelist"}
        commands_without_api_key = {"help", "whoami", "whitelist"}

        if command not in commands_without_global_permission:
            has_permission, error_msg = self._check_permission(event)
            if not has_permission:
                yield event.plain_result(error_msg)
                return

        if command not in commands_without_api_key and not self.plugin.panel_api.api_key:
            yield event.plain_result("❌ 插件未配置 API 密钥，请在插件设置中配置")
            return

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
            return

        yield event.plain_result(f"❌ 未知命令: {command}\n使用 /panel 查看帮助")

    async def _handle_help(self, event: AstrMessageEvent, parts: list[str]):
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

        if self.plugin.enable_whitelist:
            user_id = self._get_user_id(event)
            if self._is_whitelisted(user_id):
                help_text += "\n\n✅ 您已获得授权"
            else:
                help_text += f"\n\n⚠️ 您的ID: {user_id}\n请联系管理员添加到白名单"

        yield event.plain_result(help_text)

    async def _handle_status(self, event: AstrMessageEvent, parts: list[str]):
        status = await self.plugin.panel_api.get_current_status(with_net_speed=True)
        if not status:
            yield event.plain_result("❌ 获取系统状态失败，请检查配置")
            return

        result = "📊 系统状态\n\n"
        result += f"🔲 CPU: {status.get('cpuUsedPercent', 0):.2f}% ({status.get('cpuCores', 0)} 核)\n"

        mem_used = status.get("memoryUsedPercent", 0)
        mem_total = status.get("memoryTotal", 0)
        mem_used_bytes = status.get("memoryUsed", 0)
        result += f"💾 内存: {mem_used:.2f}% ({format_bytes(mem_used_bytes)} / {format_bytes(mem_total)})\n"

        load = status.get("load1", 0)
        load_status = "运行流畅" if load < 1 else ("负载较高" if load < 2 else "负载过高")
        result += f"⚡ 负载: {load:.2f} ({load_status})\n"

        for disk in status.get("diskData", []):
            path = disk.get("path", "/")
            result += (
                f"💿 磁盘 {path}: {disk.get('usedPercent', 0):.2f}% "
                f"({format_bytes(disk.get('used', 0))} / {format_bytes(disk.get('total', 0))})\n"
            )

        result += "\n🌐 网络流量:\n"
        result += f"  ↑ 上行: {format_bytes(status.get('netSentSpeed', 0))}/s | 总发送: {format_bytes(status.get('netBytesSent', 0))}\n"
        result += f"  ↓ 下行: {format_bytes(status.get('netRecvSpeed', 0))}/s | 总接收: {format_bytes(status.get('netBytesRecv', 0))}\n"

        yield event.plain_result(result)

    async def _handle_info(self, event: AstrMessageEvent, parts: list[str]):
        info = await self.plugin.panel_api.get_dashboard_base()
        if not info:
            yield event.plain_result("❌ 获取系统信息失败，请检查配置")
            return

        yield event.plain_result("📋 系统信息\n\n" + "\n".join(build_system_info_lines(info)))

    async def _handle_all(self, event: AstrMessageEvent, parts: list[str]):
        status, info = await asyncio.gather(
            self.plugin.panel_api.get_current_status(with_net_speed=True),
            self.plugin.panel_api.get_dashboard_base(),
        )

        if not status and not info:
            yield event.plain_result("❌ 获取服务器信息失败，请检查配置")
            return

        result = "🖥️ 1Panel 服务器概览\n" + "=" * 20 + "\n\n"

        if info:
            result += "\n".join(build_system_info_lines(info, include_unknown=False)) + "\n\n"

        if status:
            load = status.get("load1", 0)
            cpu_cores = status.get("cpuCores") or (info.get("cpuCores") if info else 0) or 1
            load_percent = (load / cpu_cores * 100) if cpu_cores > 0 else 0
            load_status = "运行流畅" if load < 1 else ("负载较高" if load < 2 else "负载过高")

            result += "📊 状态\n"
            result += f"  ⚡ 负载: {load_percent:.2f}% ({load_status})\n"
            result += f"  🔲 CPU: {status.get('cpuUsedPercent', 0):.2f}% ({cpu_cores} 核)\n"
            result += f"  💾 内存: {status.get('memoryUsedPercent', 0):.2f}% ({format_bytes(status.get('memoryUsed', 0))} / {format_bytes(status.get('memoryTotal', 0))})\n"

            for disk in status.get("diskData", []):
                result += (
                    f"  💿 磁盘 {disk.get('path', '/')}: {disk.get('usedPercent', 0):.2f}% "
                    f"({format_bytes(disk.get('used', 0))} / {format_bytes(disk.get('total', 0))})\n"
                )

            result += "\n🌐 网络流量\n"
            result += f"  ↑ 上行: {format_bytes(status.get('netSentSpeed', 0))}/s | 总发送: {format_bytes(status.get('netBytesSent', 0))}\n"
            result += f"  ↓ 下行: {format_bytes(status.get('netRecvSpeed', 0))}/s | 总接收: {format_bytes(status.get('netBytesRecv', 0))}\n"

        yield event.plain_result(result)

    async def _handle_docker(self, event: AstrMessageEvent, parts: list[str]):
        sub_cmd = parts[2] if len(parts) > 2 else "list"

        if sub_cmd in ["start", "stop", "restart", "pause", "unpause"]:
            if len(parts) < 4:
                yield event.plain_result(f"❌ 请指定容器名称\n用法: /panel docker {sub_cmd} <容器名称>")
                return

            container_name = parts[3]
            success, message = await self.plugin.panel_api.operate_container(container_name, sub_cmd)
            if success:
                op_text = {
                    "start": "启动",
                    "stop": "停止",
                    "restart": "重启",
                    "pause": "暂停",
                    "unpause": "恢复",
                }
                yield event.plain_result(f"✅ 容器 {container_name} {op_text.get(sub_cmd, sub_cmd)}成功")
            else:
                yield event.plain_result(f"❌ 操作失败: {message}")
            return

        data = await self.plugin.panel_api.get_containers()
        if not data:
            yield event.plain_result("❌ 获取容器列表失败")
            return

        items = data.get("items", [])
        total = data.get("total", 0)
        if not items:
            yield event.plain_result("📦 暂无容器")
            return

        result = f"🐳 容器列表 (共 {total} 个)\n\n"
        state_icons = {"running": "🟢", "exited": "🔴", "paused": "🟡", "created": "⚪"}

        for container in items[:15]:
            state = container.get("state", "未知")
            result += f"{state_icons.get(state, '⚪')} {container.get('name', '未知')}\n"
            result += f"   镜像: {container.get('imageName', '').split('/')[-1][:20]}\n"

        if total > 15:
            result += f"\n... 还有 {total - 15} 个容器"

        result += "\n\n💡 操作容器:\n"
        result += "/panel docker start <名称>\n"
        result += "/panel docker stop <名称>\n"
        result += "/panel docker restart <名称>"
        yield event.plain_result(result)

    async def _handle_apps(self, event: AstrMessageEvent, parts: list[str]):
        data = await self.plugin.panel_api.get_installed_apps()
        if not data:
            yield event.plain_result("❌ 获取应用列表失败")
            return

        items = data.get("items", [])
        total = data.get("total", 0)
        if not items:
            yield event.plain_result("📦 暂无已安装应用")
            return

        result = f"📦 已安装应用 (共 {total} 个)\n\n"
        status_icons = {"Running": "🟢", "Stopped": "🔴", "Installing": "🟡", "Error": "❌"}

        for app in items:
            name = app.get("name", "未知")
            app_name = app.get("app", {}).get("name", "") or app.get("appName", "")
            status = app.get("status", "未知")
            version = app.get("version", "")

            result += f"{status_icons.get(status, '⚪')} {name}"
            if app_name and app_name != name:
                result += f" ({app_name})"
            if version:
                result += f" v{version}"
            result += "\n"

        yield event.plain_result(result)

    async def _handle_ssh(self, event: AstrMessageEvent, parts: list[str]):
        page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 1
        status_filter = parts[3] if len(parts) > 3 else "All"

        data = await self.plugin.panel_api.get_ssh_logs(page=page, page_size=10, status=status_filter)
        if not data:
            yield event.plain_result("❌ 获取 SSH 日志失败")
            return

        logs = data.get("logs", [])
        total = data.get("total", 0)
        if not logs:
            yield event.plain_result("📋 暂无 SSH 登录记录")
            return

        result = f"🔐 SSH 登录日志 (第 {page} 页，共 {total} 条)\n\n"
        for log_entry in logs:
            status_icon = "✅" if log_entry.get("status") == "Success" else "❌"
            result += f"{status_icon} {log_entry.get('date', '')}\n"
            result += f"   {log_entry.get('user', 'root')}@{log_entry.get('address', '未知')}\n"

        result += "\n💡 翻页: /panel ssh <页码>"
        yield event.plain_result(result)

    async def _handle_firewall(self, event: AstrMessageEvent, parts: list[str]):
        rule_type = parts[2] if len(parts) > 2 else "port"

        data = await self.plugin.panel_api.get_firewall_rules(rule_type=rule_type)
        if not data:
            yield event.plain_result("❌ 获取防火墙规则失败")
            return

        items = data.get("items", [])
        total = data.get("total", 0)
        if not items:
            yield event.plain_result("🧱 暂无防火墙规则")
            return

        result = f"🧱 防火墙规则 (共 {total} 条)\n\n"
        for rule in items[:20]:
            strategy = rule.get("strategy", "")
            icon = "✅" if strategy == "accept" else "🚫"

            if rule_type == "port":
                port = rule.get("port", "")
                protocol = rule.get("protocol", "tcp")
                desc = rule.get("description", "")
                result += f"{icon} {port}/{protocol}"
                if desc:
                    result += f" - {desc}"
                result += "\n"
            else:
                result += f"{icon} {rule.get('address', '')}\n"

        if total > 20:
            result += f"\n... 还有 {total - 20} 条规则"

        yield event.plain_result(result)

    async def _handle_cron(self, event: AstrMessageEvent, parts: list[str]):
        data = await self.plugin.panel_api.get_cronjobs()
        if not data:
            yield event.plain_result("❌ 获取定时任务失败")
            return

        items = data.get("items", [])
        total = data.get("total", 0)
        if not items:
            yield event.plain_result("⏰ 暂无定时任务")
            return

        result = f"⏰ 定时任务 (共 {total} 个)\n\n"
        for job in items:
            status_icon = "🟢" if job.get("status") == "Enable" else "🔴"
            result += f"{status_icon} {job.get('name', '未知')}\n"
            result += f"   类型: {job.get('type', '')} | {job.get('spec', '')}\n"

        yield event.plain_result(result)

    async def _handle_whoami(self, event: AstrMessageEvent, parts: list[str]):
        user_id = self._get_user_id(event)

        result = "👤 用户信息\n\n"
        result += f"用户ID: {user_id}\n"

        if self.plugin.enable_whitelist:
            if self._is_whitelisted(user_id):
                result += "权限状态: ✅ 已授权\n"
                result += f"白名单用户数: {len(self.plugin.whitelist_users)}个"
            else:
                result += "权限状态: ❌ 未授权\n"
                result += "\n💡 如需使用此插件，请联系管理员将您的ID添加到白名单"
        else:
            result += "权限状态: ✅ 所有用户可用\n"
            result += "（管理员未启用白名单）"

        yield event.plain_result(result)

    async def _handle_whitelist(self, event: AstrMessageEvent, parts: list[str]):
        if len(parts) < 3:
            yield event.plain_result(
                "❌ 请指定子命令\n\n"
                "用法:\n"
                "/panel whitelist list - 查看白名单\n"
                "/panel whitelist add <用户ID> - 添加用户\n"
                "/panel whitelist remove <用户ID> - 移除用户"
            )
            return

        sub_cmd = parts[2].lower()

        if sub_cmd == "list":
            if not self.plugin.enable_whitelist:
                yield event.plain_result("ℹ️ 白名单功能未启用\n\n所有用户都可以使用此插件")
                return

            if not self.plugin.whitelist_users:
                yield event.plain_result("📋 白名单列表\n\n当前白名单为空")
                return

            result = f"📋 白名单列表 (共 {len(self.plugin.whitelist_users)} 个用户)\n\n"
            for idx, uid in enumerate(self.plugin.whitelist_users, 1):
                result += f"{idx}. {uid}\n"

            yield event.plain_result(result)
            return

        if sub_cmd in ["add", "remove"]:
            operator_id = self._get_user_id(event)
            if self.plugin.enable_whitelist and not self._is_whitelisted(operator_id):
                yield event.plain_result(
                    f"❌ 权限不足\n\n只有白名单用户才能管理白名单\n您的ID: {operator_id}"
                )
                return

            if len(parts) < 4:
                yield event.plain_result(f"❌ 请指定用户ID\n\n用法: /panel whitelist {sub_cmd} <用户ID>")
                return

            target_user_id = normalize_user_id(parts[3])
            if not target_user_id:
                yield event.plain_result(f"❌ 用户ID不能为空\n\n用法: /panel whitelist {sub_cmd} <用户ID>")
                return

            if sub_cmd == "add":
                if self._is_whitelisted(target_user_id):
                    yield event.plain_result(f"ℹ️ 用户 {target_user_id} 已在白名单中")
                    return

                self.plugin.whitelist_users.append(target_user_id)
                self._refresh_whitelist_cache()
                self._save_whitelist()
                yield event.plain_result(
                    f"✅ 已将用户 {target_user_id} 添加到白名单\n\n当前白名单用户数: {len(self.plugin.whitelist_users)}个"
                )
                return

            if not self._is_whitelisted(target_user_id):
                yield event.plain_result(f"ℹ️ 用户 {target_user_id} 不在白名单中")
                return

            if target_user_id == operator_id:
                yield event.plain_result("❌ 不能移除自己")
                return

            self.plugin.whitelist_users.remove(target_user_id)
            self._refresh_whitelist_cache()
            self._save_whitelist()
            yield event.plain_result(
                f"✅ 已将用户 {target_user_id} 从白名单移除\n\n当前白名单用户数: {len(self.plugin.whitelist_users)}个"
            )
            return

        yield event.plain_result(f"❌ 未知子命令: {sub_cmd}\n\n可用命令: list, add, remove")
