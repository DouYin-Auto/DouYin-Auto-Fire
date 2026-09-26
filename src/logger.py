"""日志系统 - 按分类开关 + 每日文件夹 + 大小轮转。

目录结构：
    logs/
      2026-09-23/
        all.log              # 总日志
        online_events.log    # 上线/下线事件
        send_result.log      # 发送结果
        schedule.log         # 调度决策
        session_save.log     # Session 保存
        browser_ops.log      # 浏览器操作
        status_check.log     # 在线状态获取

每个文件超过 1KB 后自动切换为新文件（如 all.log.1, all.log.2）。
"""

from __future__ import annotations

import os
from datetime import date, datetime, timedelta

from src.config import get_config

# 日志根目录
LOGS_DIR = str(get_config().sessions_dir.parent / "logs")

# 单文件大小上限（字节）
MAX_FILE_SIZE = get_config().logs.max_file_size

# 所有分类
ALL_CATEGORIES = (
    "online_events",
    "send_result",
    "schedule",
    "session_save",
    "browser_ops",
    "status_check",
    "chat_refresh",
)

# ANSI 颜色码
COLORS = {
    "online_events": "\033[36m",   # 青色
    "send_result": "\033[32m",      # 绿色
    "schedule": "\033[33m",         # 黄色
    "session_save": "\033[35m",     # 紫色
    "browser_ops": "\033[34m",      # 蓝色
    "status_check": "\033[90m",     # 灰色
    "chat_refresh": "\033[96m",     # 亮青色
}
RESET = "\033[0m"


class Logger:
    """分类日志器。

    Attributes:
        switches: 各分类的开关状态。
        enable_console: 是否输出到控制台。
        _date: 当前日志日期。
        _indexes: 各分类当前文件编号。
    """

    def __init__(
        self,
        enable_console: bool = True,
        switches: dict[str, bool] | None = None,
    ) -> None:
        """
        Args:
            enable_console: 是否输出到控制台（默认 True）。
            switches: 各分类的开关状态。未指定的使用配置文件中的设置。
        """
        self.enable_console = enable_console

        # 默认从配置文件读取
        config_categories = get_config().logs.categories.model_dump()
        self.switches: dict[str, bool] = {
            cat: config_categories.get(cat, True) for cat in ALL_CATEGORIES
        }
        if switches:
            self.switches.update(switches)

        self._date: date | None = None
        self._indexes: dict[str, int] = {}

    def _get_log_dir(self) -> str:
        """获取当日日志目录（如果不存在则创建）。"""
        today = datetime.now().date()
        if self._date != today:
            self._date = today
            self._indexes = {}
        log_dir = os.path.join(LOGS_DIR, today.strftime("%Y-%m-%d"))
        os.makedirs(log_dir, exist_ok=True)
        # 每次获取目录时清理旧日志
        self._cleanup_old_logs()
        return log_dir

    def _cleanup_old_logs(self) -> None:
        """删除超过保留天数的日志目录。"""
        retention_days = get_config().logs.retention_days
        if retention_days <= 0:
            return
        if not os.path.exists(LOGS_DIR):
            return
        cutoff = datetime.now().date() - timedelta(days=retention_days)
        import shutil

        for entry in os.listdir(LOGS_DIR):
            dir_path = os.path.join(LOGS_DIR, entry)
            if not os.path.isdir(dir_path):
                continue
            # 解析目录名（YYYY-MM-DD）
            try:
                dir_date = datetime.strptime(entry, "%Y-%m-%d").date()
            except ValueError:
                continue
            if dir_date < cutoff:
                try:
                    shutil.rmtree(dir_path)
                except Exception:
                    pass

    def _get_file_path(self, category: str) -> str:
        """获取当前写入的文件路径（考虑大小轮转）。"""
        log_dir = self._get_log_dir()
        base_path = os.path.join(log_dir, f"{category}.log")

        # 检查大小轮转：name.1.log, name.2.log...
        idx = self._indexes.get(category, 0)
        while True:
            if idx == 0:
                path = base_path
            else:
                path = os.path.join(log_dir, f"{category}.{idx}.log")
            if not os.path.exists(path):
                return path
            if os.path.getsize(path) < MAX_FILE_SIZE:
                return path
            idx += 1
            self._indexes[category] = idx

    def _raw_write(self, category: str, level: str, message: str) -> None:
        """直接写入日志文件（不经过开关检查，Caller 已检查）。"""
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        line = f"[{timestamp}] [{level:>5}] {message}"

        try:
            # 写入分类文件（行缓冲，每条立即刷盘）
            file_path = self._get_file_path(category)
            with open(file_path, "a", encoding="utf-8", buffering=1) as f:
                f.write(line + "\n")

            # 写入总文件
            all_path = self._get_file_path("all")
            with open(all_path, "a", encoding="utf-8", buffering=1) as f:
                f.write(line + " [" + category + "]\n")
        except Exception:
            pass  # 日志写入失败不影响主流程

    def _write(self, category: str, level: str, message: str) -> None:
        """写入日志（经过开关检查 + 控制台输出）。"""
        if not self.switches.get(category, True):
            return
        self._raw_write(category, level, message)

        # 控制台输出
        if self.enable_console:
            color = COLORS.get(category, "")
            now = datetime.now()
            timestamp = now.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            category_tag = f"[{category}]"
            print(f"{color}{timestamp} {category_tag:<16} {message}{RESET}")

    def info(self, category: str, message: str) -> None:
        """记录 INFO 级别日志。"""
        self._write(category, "INFO", message)

    def warning(self, category: str, message: str) -> None:
        """记录 WARNING 级别日志。"""
        self._write(category, "WARN", message)

    def error(self, category: str, message: str) -> None:
        """记录 ERROR 级别日志。"""
        self._write(category, "ERROR", message)

    # 便捷方法

    def online_events(self, message: str) -> None:
        self._write("online_events", "INFO", message)

    def send_result(self, message: str, success: bool = True) -> None:
        level = "INFO" if success else "ERROR"
        self._write("send_result", level, message)

    def log_status_json(self, statuses: list[dict]) -> None:
        """将全量在线状态以 JSON 行格式写入 status.jsonl。"""
        import json as _json

        log_dir = self._get_log_dir()
        file_path = os.path.join(log_dir, "status.jsonl")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        record = {"time": timestamp, "statuses": statuses}
        line = _json.dumps(record, ensure_ascii=False)
        with open(file_path, "a", encoding="utf-8", buffering=1) as f:
            f.write(line + "\n")

    def schedule(self, message: str) -> None:
        self._write("schedule", "INFO", message)

    def session_save(self, message: str, success: bool = True) -> None:
        level = "INFO" if success else "ERROR"
        self._write("session_save", level, message)

    def browser_ops(self, message: str) -> None:
        self._write("browser_ops", "INFO", message)

    def status_check(self, message: str, success: bool = True) -> None:
        level = "INFO" if success else "ERROR"
        self._write("status_check", level, message)

    def chat_refresh(self, message: str, success: bool = True) -> None:
        level = "INFO" if success else "ERROR"
        self._write("chat_refresh", level, message)


# 全局单例
_logger: Logger | None = None
_print_installed: bool = False
_original_print = print  # 在替换前保存原始 print


def _default_print(*args: object, **kwargs: object) -> None:
    """默认的 print 行为（不经过日志）。"""
    _original_print(*args, **kwargs)


def _logging_print(*args: object, **kwargs: object) -> None:
    """替换内置 print，使其同时写入日志。"""
    message = " ".join(str(a) for a in args)

    # 控制台输出（保留原行为）
    _default_print(*args, **kwargs)

    # 写入日志
    try:
        logger = get_logger()
        if logger.switches.get("browser_ops", True):
            logger._raw_write("browser_ops", "INFO", message)
    except Exception:
        pass  # 日志写入失败不影响主流程


def install_print_redirect() -> None:
    """将内置 print 替换为同时写入日志的版本。"""
    global _print_installed
    if _print_installed:
        return
    import builtins as _builtins

    _builtins.print = _logging_print
    _print_installed = True


def get_logger(
    enable_console: bool = True,
    switches: dict[str, bool] | None = None,
) -> Logger:
    """获取全局日志器（首次调用时初始化）。"""
    global _logger
    if _logger is None:
        _logger = Logger(enable_console=enable_console, switches=switches)
    return _logger


def init_logger(
    enable_console: bool = True,
    **kwargs: bool,
) -> Logger:
    """初始化全局日志器。

    Args:
        enable_console: 是否输出到控制台。
        **kwargs: 各分类开关，如 online_events=True, send_result=False。

    Returns:
        初始化后的 Logger 实例。

    Example:
        init_logger(online_events=True, send_result=True, schedule=False)
    """
    global _logger
    _logger = Logger(enable_console=enable_console, switches=kwargs)
    return _logger
