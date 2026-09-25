"""配置加载与校验。

从项目根目录的 config.yaml 加载配置，提供类型安全和校验。
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
# 配置文件路径
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"
# 示例配置路径
CONFIG_EXAMPLE_PATH = PROJECT_ROOT / "config" / "config.example.yaml"


class BrowserConfig(BaseModel):
    """浏览器 / CDP 配置。"""
    cdp_endpoint: str = Field(
        default="http://192.168.1.121:8087/api/profiles/7f92c439-a6ad-400b-8b37-3c0d48395a82/cdp",
        description="CloakBrowser CDP 端点",
    )
    auth_token: str = Field(
        default="CloakBrowser-Manager_AUTH_TOKEN",
        description="认证 Token",
    )
    douyin_domain: str = Field(
        default="douyin.com",
        description="抖音域名",
    )


class SessionsConfig(BaseModel):
    """Session 持久化配置。"""
    dir: str = Field(
        default="sessions",
        description="存储目录（相对项目根或绝对路径）",
    )


class LogCategoriesConfig(BaseModel):
    """日志分类开关。"""
    online_events: bool = True
    send_result: bool = True
    schedule: bool = True
    session_save: bool = True
    browser_ops: bool = True
    status_check: bool = True


class LogsConfig(BaseModel):
    """日志配置。"""
    enabled: bool = True
    console: bool = True
    max_file_size: int = Field(
        default=1048576, ge=256,
        description="单文件大小上限（字节），默认 1MB",
    )
    retention_days: int = Field(
        default=7, ge=1, le=365, description="日志保留天数",
    )
    categories: LogCategoriesConfig = Field(default_factory=LogCategoriesConfig)


class OfflineScheduleConfig(BaseModel):
    """离线调度参数。"""
    min_hours: int = Field(default=5, ge=1, le=24)
    max_hours: int = Field(default=10, ge=1, le=48)


class OnlineScheduleConfig(BaseModel):
    """在线调度参数。"""
    min_minutes: int = Field(default=15, ge=1, le=120)
    max_minutes: int = Field(default=50, ge=1, le=240)


class FullSendConfig(BaseModel):
    """每日全量发送时刻。"""
    hour: int = Field(default=0, ge=0, le=23)
    minute: int = Field(default=1, ge=0, le=59)
    tolerance_seconds: int = Field(default=120, ge=30, le=600)


class ScheduleConfig(BaseModel):
    """调度参数。"""
    offline: OfflineScheduleConfig = Field(default_factory=OfflineScheduleConfig)
    online: OnlineScheduleConfig = Field(default_factory=OnlineScheduleConfig)
    full_send: FullSendConfig = Field(default_factory=FullSendConfig)
    # 火花还有多少天以内算"即将消失"
    expiring_days: int = Field(default=3, ge=1, le=30)
    # 火花未续用户上线后的延迟秒数
    online_delay: int = Field(default=5, ge=0, le=300)
    # 启动时跳过最近 N 小时内已发送过的用户
    skip_hours: int = Field(default=1, ge=0, le=24)
    # 是否开启上线监控
    on_online: bool = True
    # 全量用户列表（指定用户发送，为空则从会话列表自动提取）
    full_mode_users: list[str] = Field(default_factory=list)


class AppConfig(BaseModel):
    """应用完整配置。"""
    browser: BrowserConfig = Field(default_factory=BrowserConfig)
    sessions: SessionsConfig = Field(default_factory=SessionsConfig)
    logs: LogsConfig = Field(default_factory=LogsConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)

    @property
    def sessions_dir(self) -> Path:
        """获取 Session 目录绝对路径。"""
        d = Path(self.sessions.dir)
        if d.is_absolute():
            return d
        return PROJECT_ROOT / d


def load_config(config_path: Path | None = None) -> AppConfig:
    """加载配置文件。

    优先从指定路径加载，否则从默认 config.yaml 加载。
    如果配置文件不存在，使用默认值。

    Args:
        config_path: 配置文件路径。None 则使用默认 config.yaml。

    Returns:
        AppConfig 实例。
    """
    path = config_path or CONFIG_PATH

    if not path.exists():
        if config_path is not None:
            raise FileNotFoundError(
                f"配置文件不存在: {path}\n"
                f"请复制 config/config.example.yaml 为 config/config.yaml 后修改"
            )
        # 默认配置不存在，直接返回默认值
        return AppConfig()

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    return AppConfig(**data)


# 全局配置单例
_config: AppConfig | None = None


def get_config() -> AppConfig:
    """获取全局配置单例。"""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def set_config(config: AppConfig) -> None:
    """手动设置全局配置（用于测试）。"""
    global _config
    _config = config
