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

import sys
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register


CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))


from command_handlers import PanelCommandHandlers, normalize_user_ids
from panel_api import OnePanelAPI


@register("astrbot_plugin_1panel", "Haitun", "1Panel 面板监控插件", "1.0.3")
class OnePanelPlugin(Star):
    """AstrBot 1Panel 插件主类。"""

    def __init__(self, context: Context, config: dict):
        super().__init__(context)
        self.config = config

        panel_host = config.get("panel_host", "http://localhost:10086")
        panel_api_key = config.get("panel_api_key", "")
        verify_ssl = config.get("verify_ssl", False)

        self.enable_whitelist = config.get("enable_whitelist", False)
        self.whitelist_users = normalize_user_ids(config.get("whitelist_users", []))
        self._whitelist_lookup = set(self.whitelist_users)
        self.config["whitelist_users"] = list(self.whitelist_users)

        self.panel_api = OnePanelAPI(panel_host, panel_api_key, verify_ssl)
        self.command_handlers = PanelCommandHandlers(self)

        logger.info("1Panel 监控插件已加载")
        logger.info(f"  Host: {panel_host}")
        if self.enable_whitelist:
            logger.info(f"  权限管理: 已启用 (白名单用户: {len(self.whitelist_users)}个)")
        else:
            logger.info("  权限管理: 未启用 (所有用户可用)")

    @filter.command("panel")
    async def panel_command(self, event: AstrMessageEvent):
        """1Panel 面板监控命令，查看服务器状态和系统信息。"""
        async for result in self.command_handlers.handle_panel_command(event):
            yield result

    async def terminate(self):
        await self.panel_api.close()
        logger.info("1Panel 监控插件已卸载")
