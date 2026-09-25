"""XXH 共享常量（从配置加载）。"""

from src.config import get_config

_cfg = get_config().schedule
OFFLINE_MIN_INTERVAL = _cfg.offline.min_hours * 3600
OFFLINE_MAX_INTERVAL = _cfg.offline.max_hours * 3600
ONLINE_MIN_INTERVAL = _cfg.online.min_minutes * 60
ONLINE_MAX_INTERVAL = _cfg.online.max_minutes * 60
FULL_SEND_HOUR = _cfg.full_send.hour
FULL_SEND_MINUTE = _cfg.full_send.minute
FULL_SEND_TOLERANCE = _cfg.full_send.tolerance_seconds
