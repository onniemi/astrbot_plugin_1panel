#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import time
from datetime import datetime
from typing import Dict, Optional


logger = logging.getLogger(__name__)


def format_bytes(bytes_val: float) -> str:
    """格式化字节数为人类可读格式。"""
    if bytes_val < 1024:
        return f"{bytes_val:.2f} B"
    if bytes_val < 1024 ** 2:
        return f"{bytes_val / 1024:.2f} KB"
    if bytes_val < 1024 ** 3:
        return f"{bytes_val / 1024 ** 2:.2f} MB"
    return f"{bytes_val / 1024 ** 3:.2f} GB"


def format_uptime(seconds: int) -> str:
    """格式化运行时间。"""
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


def parse_runtime_value(value: object) -> Optional[int]:
    """将 API 返回的运行时间字段转换为正整数秒数。"""
    if isinstance(value, (int, float)):
        return int(value) if value > 0 else None

    if isinstance(value, str):
        try:
            parsed_value = int(float(value.strip()))
        except ValueError:
            return None
        return parsed_value if parsed_value > 0 else None

    return None


def extract_runtime_details(info: Dict) -> tuple[Optional[str], Optional[str]]:
    """提取启动时间和运行时长，兼容字符串/字典两种 virtualizationSystem 格式。"""
    virt_info = info.get("virtualizationSystem")
    virt_data: Dict = {}

    if isinstance(virt_info, str) and virt_info.strip():
        try:
            loaded_data = json.loads(virt_info)
        except json.JSONDecodeError:
            logger.warning("virtualizationSystem 字段不是合法 JSON，已跳过运行时间解析")
            loaded_data = None
        if isinstance(loaded_data, dict):
            virt_data = loaded_data
    elif isinstance(virt_info, dict):
        virt_data = virt_info

    boot_time = parse_runtime_value(virt_data.get("bootTime"))
    if boot_time:
        uptime_seconds = max(int(time.time() - boot_time), 0)
        boot_time_text = datetime.fromtimestamp(boot_time).strftime("%Y-%m-%d %H:%M:%S")
        return boot_time_text, format_uptime(uptime_seconds)

    uptime = parse_runtime_value(virt_data.get("uptime")) or parse_runtime_value(info.get("uptime"))
    if uptime:
        return None, format_uptime(uptime)

    return None, None


def build_system_info_lines(info: Dict, include_unknown: bool = True) -> list[str]:
    """构建系统信息文本，避免 info/all 两个命令重复拼接。"""
    os_info = info.get("prettyDistro") or f"{info.get('platform', '')} {info.get('platformVersion', '')}"
    os_info = os_info.strip() or "未知"

    lines = [
        f"🏠 主机名称: {info.get('hostname', '未知')}",
        f"🐧 发行版本: {os_info}",
    ]

    optional_fields = [
        ("kernelVersion", "🔧 内核版本"),
        ("kernelArch", "🖥️ 系统类型"),
        ("ipV4Addr", "🌐 主机地址"),
    ]
    for field_name, label in optional_fields:
        field_value = info.get(field_name)
        if include_unknown:
            lines.append(f"{label}: {field_value or '未知'}")
        elif field_value:
            lines.append(f"{label}: {field_value}")

    boot_time_text, uptime_text = extract_runtime_details(info)
    if boot_time_text:
        lines.append(f"📅 启动时间: {boot_time_text}")
    if uptime_text:
        lines.append(f"⏱️ 运行时间: {uptime_text}")

    return lines
