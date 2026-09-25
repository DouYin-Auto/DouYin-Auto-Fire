# dy-auto

抖音自动化项目 - 基于 Playwright + CDP 远程浏览器。支持消息发送、在线状态检测、火花管理和自动续火花。

## ⚠️ 免责声明

本项目仅供学习与研究使用。使用本项目可能违反抖音（Douyin）的服务条款和用户协议，存在账号被封禁、限制或其他处罚风险。使用者需自行承担因使用本项目而产生的一切后果，包括但不限于：

- 账号被临时或永久封禁
- 账号功能受限（如无法发送消息、无法使用私信等）
- 设备或网络被封禁
- 因违反抖音协议而导致的其他损失

开发者不对因使用本项目造成的任何直接或间接损失负责。请谨慎使用，并遵守相关法律法规和平台规则。

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置

复制示例配置文件并修改：

```bash
cp config/config.example.yaml config/config.yaml
```

编辑 `config/config.yaml`，设置 CDP 端点、Token 等。

### 3. 初始化登录

```bash
# 通过 CDP 连接远程浏览器，登录后自动保存 session
uv run python -m src.douyin_init_login
```

### 4. 运行命令

#### 消息发送

```bash
# 发送文字消息
uv run python -m src.send_message <抖音号> <好友名> --text "你好"

# 发送原生表情
uv run python -m src.send_message <抖音号> <好友名> --sticker 比心

# 文字 + 表情
uv run python -m src.send_message <抖音号> <好友名> --text "在吗" --sticker 比心
```

#### 在线状态查询

```bash
# 查看所有好友状态（在线 + 火花）
uv run python -m src.get_online_status --douyin-id <抖音号>

# 只看在线好友
uv run python -m src.get_online_status --douyin-id <抖音号> --online-only

# 只看需要续火花的（今天未互发消息）
uv run python -m src.get_online_status --douyin-id <抖音号> --attention

# JSON 格式输出
uv run python -m src.get_online_status --douyin-id <抖音号> --json
```

#### 续火花（XXH）

```bash
# 一次性续火花（默认发送"续火花"表情）
uv run python -m src.run_xxh --douyin-id <抖音号>

# 只给今天未续火花的用户发送
uv run python -m src.run_xxh --douyin-id <抖音号> --target inc

# 自定义表情 / 附带文字
uv run python -m src.run_xxh --douyin-id <抖音号> --sticker 比心 --message "在吗"

# 预览目标（不发送）
uv run python -m src.run_xxh --douyin-id <抖音号> --dry-run

# 持续模式（智能调度）
uv run python -m src.run_xxh --douyin-id <抖音号> --loop
```

## 配置

配置文件 `config/config.yaml`：

```yaml
# 浏览器 / CDP 配置
browser:
  cdp_endpoint: "http://192.168.1.121:8087/api/profiles/xxx/cdp"
  auth_token: "CloakBrowser-Manager_AUTH_TOKEN"

# Session 存储目录
sessions:
  dir: "sessions"

# 日志配置
logs:
  enabled: true
  console: true           # 控制台输出
  max_file_size: 1048576  # 单文件 1MB，超过轮转
  retention_days: 7       # 保留 7 天，过期自动删除
  categories:             # 分类开关
    online_events: true
    send_result: true
    schedule: true
    session_save: true
    browser_ops: true
    status_check: true

# 调度参数
schedule:
  offline:
    min_hours: 5          # 离线用户最小间隔
    max_hours: 10         # 离线用户最大间隔
  online:
    min_minutes: 15       # 在线用户最小间隔
    max_minutes: 50       # 在线用户最大间隔
  full_send:
    hour: 0
    minute: 1             # 每日 00:01 全量发送
    tolerance_seconds: 120
  expiring_days: 3
  online_delay: 5         # 火花未续用户上线后延迟秒数
  skip_hours: 1           # 启动时跳过 N 小时内已发送过的用户
  on_online: true         # 上线监控开关
  full_mode_users:        # 全量模式用户列表（跳过状态检查）
    - "张三"
    - "李四"
```

## 日志

日志写入 `logs/YYYY-MM-DD/` 目录，按分类存储：

```
logs/2026-09-24/
  all.log               # 总日志（所有分类）
  all.1.log             # 轮转文件
  status.jsonl          # 全量状态 JSON（每行一条）
  online_events.log     # 上线/下线事件
  send_result.log       # 发送结果（目标/内容/触发条件）
  schedule.log          # 调度决策
  session_save.log      # Session 保存
  browser_ops.log       # 浏览器操作
  status_check.log      # 状态获取
```

### 日志开关

```bash
# 关闭指定分类日志
uv run python -m src.run_xxh --douyin-id <抖音号> --loop --no-log-schedule

# 关闭控制台输出（保留文件）
uv run python -m src.run_xxh --douyin-id <抖音号> --loop --no-log-console
```

## 项目结构

```
dy-auto/
├── config/
│   ├── config.example.yaml       # 示例配置
│   └── config.yaml               # 实际配置（git 忽略）
├── src/
│   ├── config.py                 # 配置加载（Pydantic 校验）
│   ├── logger.py                 # 日志系统
│   ├── constants.py              # 共享常量
│   ├── cdp_utils.py              # CDP 连接管理
│   ├── storage_utils.py          # 存储操作
│   ├── session_utils.py          # Session 读写
│   ├── dy_utils.py               # 抖音业务工具
│   ├── selectors.py              # CSS 选择器
│   ├── douyin_chat.py            # 私信页面操作
│   ├── message_sender.py         # 消息发送 + 状态确认
│   ├── online_status.py          # 在线状态检测
│   ├── get_online_status.py      # 状态查询入口
│   ├── xxh.py                    # 续火花核心逻辑
│   ├── run_xxh.py                # 续火花 CLI 入口
│   ├── send_message.py           # 自动发送入口
│   ├── douyin_init_login.py      # 初始化登录
│   ├── dy_dump_session.py        # Session 导出
│   ├── login_by_session.py       # Session 恢复
│   ├── dy_analyze_session.py     # Session 分析
│   └── js/                       # 浏览器端 JS 脚本
│       ├── extract_online_status.js
│       ├── extract_douyin_id.js
│       ├── dump_local_storage.js
│       ├── restore_local_storage.js
│       ├── clear_local_session_storage.js
│       └── clear_indexeddb.js
├── sessions/                     # Session 文件目录
├── pyproject.toml
└── .gitignore
```

## 状态模型

**统一二元状态：**

| 状态 | 判断依据 | 操作 |
|------|---------|------|
| 已续（明亮火花） | 火花文字为亮色（如 `rgb(255, 94, 0)`） | 跳过 |
| 未续（灰色火花） | 火花文字为灰色（`var(--color-TextTertiary)`） | 续火花 |

有火花的用户（无论天数、X天后消失、重燃中、点亮中）都参与续火花；无火花用户忽略。

## 调度策略（持续模式）

| 场景 | 行为 |
|------|------|
| 用户上线 + 未续 | 5 秒后发送 |
| 用户上线 + 已续 | 随机 15-50 分钟后发送 |
| 未上线用户 | 随机 5-10 小时发送 |
| 每日 00:01 | 全量发送一次 |
| 启动时 | 跳过 1 小时内已发送过的用户 |
