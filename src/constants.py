"""项目共享常量（从配置文件加载）。"""

from src.config import get_config

# 加载配置（只调用一次）
_config = get_config()

# Session 目录
SESSIONS_DIR = str(_config.sessions_dir)

# CloakBrowser 配置
CDP_ENDPOINT = _config.browser.cdp_endpoint
AUTH_TOKEN = _config.browser.auth_token

# 抖音域名
DOUYIN_DOMAIN = _config.browser.douyin_domain

# 日志配置
LOGS_DIR = str(_config.sessions_dir.parent / "logs")
