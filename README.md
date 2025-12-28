# AstrBot 1Panel 面板监控插件

通过 AstrBot 管理和监控 1Panel 面板。

## 功能

- 📊 **系统监控** - CPU、内存、负载、磁盘使用率、网络流量
- 📋 **系统信息** - 主机名、操作系统、内核版本、运行时间
- 🐳 **容器管理** - 查看容器列表、启动/停止/重启容器
- 📦 **应用管理** - 查看已安装应用状态
- 🔐 **SSH 日志** - 查看 SSH 登录记录
- 🔥 **防火墙** - 查看端口规则
- ⏰ **定时任务** - 查看定时任务列表
- 👤 **权限管理** - 白名单用户控制 🆕

## 安装

1. 下载插件 zip 文件
2. 在 AstrBot 管理面板上传安装
3. 配置 1Panel 面板地址和 API 密钥

## 配置

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| panel_host | string | `http://localhost:10086` | 1Panel 面板地址 |
| panel_api_key | string | `""` | API 密钥 |
| verify_ssl | boolean | `false` | 是否验证 SSL 证书 |
| enable_whitelist | boolean | `false` | 是否启用白名单 🆕 |
| whitelist_users | array | `[]` | 白名单用户ID列表 🆕 |

### 配置示例

```json
{
  "panel_host": "http://192.168.1.1:10086",
  "panel_api_key": "Le7mny7s9DJrUP1pj6bbpGsqxHg6VJBG",
  "verify_ssl": false,
  "enable_whitelist": true,
  "whitelist_users": ["123456789", "987654321"]
}
```

### 获取 API 密钥

1. 登录 1Panel 面板
2. 进入 **面板设置** → **面板** → **API 接口**
3. 启用 API 接口
4. 复制生成的 API 密钥
5. **重要**: 将服务器 IP 添加到 **IP 白名单**
   - 同一服务器: `127.0.0.1`
   - 允许所有 IPv4: `0.0.0.0/0`
   - 允许所有 IPv6: `::/0`

### 权限管理配置 🆕

**1. 查看用户ID**

任何用户都可以使用此命令查看自己的ID：
```
/panel whoami
```

输出示例：
```
👤 用户信息

用户ID: 123456789
权限状态: ❌ 未授权

💡 如需使用此插件，请联系管理员将您的ID添加到白名单
```

**2. 配置白名单**

方式一：在插件配置中添加
```json
{
  "enable_whitelist": true,
  "whitelist_users": ["123456789", "987654321"]
}
```

方式二：通过指令管理（推荐）🆕
```
# 先让第一个管理员用户查看自己的ID
/panel whoami

# 在配置中手动添加第一个管理员ID后，该管理员可以通过指令添加其他用户
/panel whitelist add 123456789
/panel whitelist add 987654321

# 查看白名单
/panel whitelist list

# 移除用户
/panel whitelist remove 123456789
```

**3. 权限说明**

- `enable_whitelist: false` - 所有用户都可以使用（默认）
- `enable_whitelist: true` - 仅白名单用户可以使用
- 未授权用户会看到 "❌ 权限不足" 提示

## 命令

### 系统监控
```
/panel              # 显示帮助
/panel status       # 系统状态（CPU、内存、负载、磁盘）
/panel info         # 系统信息（主机名、版本、运行时间）
/panel all          # 全部信息
```

### 容器管理
```
/panel docker                    # 查看容器列表
/panel docker start <名称>       # 启动容器
/panel docker stop <名称>        # 停止容器
/panel docker restart <名称>     # 重启容器
```

### 应用管理
```
/panel apps         # 查看已安装应用
```

### 安全相关
```
/panel ssh          # SSH 登录日志
/panel ssh 2        # 查看第2页
/panel firewall     # 防火墙端口规则
```

### 定时任务
```
/panel cron         # 查看定时任务
```

### 权限管理 🆕
```
/panel whoami                    # 查看当前用户ID和权限状态
/panel whitelist list            # 查看白名单列表
/panel whitelist add <用户ID>    # 添加用户到白名单
/panel whitelist remove <用户ID> # 从白名单移除用户
```

**注意**: 白名单管理命令（add/remove）仅白名单用户可用

### 示例输出

#### /panel status
```
📊 系统状态

🔲 CPU: 1.55% (4 核)
💾 内存: 34.46% (1.25 GB / 3.64 GB)
⚡ 负载: 0.06 (运行流畅)
💿 磁盘 /: 38.63% (15.16 GB / 39.26 GB)

🌐 网络流量:
  ↓ 总接收: 85.01 GB
  ↑ 总发送: 127.64 GB
```

#### /panel info
```
📋 系统信息

🏠 主机名: VM-12-8-debian
🐧 系统: Debian GNU/Linux 12
🔧 内核: 6.1.0-40-amd64
🖥️ 架构: x86_64
🌐 IP: 10.1.12.8
⏱️ 运行时间: 2天 7小时 59分钟
```

## 注意事项

- 确保 1Panel API 的 **IP 白名单** 包含 AstrBot 运行的服务器 IP
- 如果 AstrBot 和 1Panel 在同一服务器，需添加 `127.0.0.1` 到白名单
- 容器操作（启动/停止/重启）需要一定时间，请耐心等待

## 开发说明

- 使用 `httpx` 异步 HTTP 客户端（符合 AstrBot 开发规范）
- 使用 1Panel 官方 API v2 接口
- Token 认证：`md5('1panel' + API-Key + UnixTimestamp)`
- 已适配 1Panel v2.x API 参数格式

## 许可

MIT License
