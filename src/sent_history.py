"""发送历史持久化 - 当日发送记录。"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta

from src.constants import SESSIONS_DIR


class SentHistory:
    """当日发送记录持久化。

    使用 JSON 文件记录每次发送，启动时加载，
    若某用户在过去 N 小时内被发送过消息，则离线自动发送时跳过。
    """

    def __init__(self, douyin_id: str, hours: int = 1) -> None:
        """
        Args:
            douyin_id: 抖音号（用于文件路径）。
            hours: 避战时间窗口（小时），默认 1 小时。
        """
        self.douyin_id = douyin_id
        self.hours = hours
        self._records: list[dict] = []  # [{name, time}, ...]
        self._filepath = get_sent_history_filepath(douyin_id)
        self._load()

    def _load(self) -> None:
        """从文件加载历史记录。"""
        if not os.path.exists(self._filepath):
            return
        try:
            with open(self._filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    self._records = data
        except Exception:
            self._records = []
        self._cleanup()

    def _cleanup(self) -> None:
        """清理窗口期外的旧记录。"""
        cutoff = datetime.now() - timedelta(hours=self.hours)
        self._records = [
            r for r in self._records
            if datetime.fromisoformat(r["time"]) > cutoff
        ]

    def _save(self) -> None:
        """保存记录到文件。"""
        os.makedirs(os.path.dirname(self._filepath), exist_ok=True)
        with open(self._filepath, "w", encoding="utf-8") as f:
            json.dump(self._records, f, ensure_ascii=False, indent=2)

    def record(self, friend_name: str) -> None:
        """记录一次发送。"""
        now = datetime.now()
        self._records.append({"name": friend_name, "time": now.isoformat()})
        self._save()

    def was_sent_recently(self, friend_name: str) -> bool:
        """判断某用户在过去 N 小时内是否已发送过消息。"""
        cutoff = datetime.now() - timedelta(hours=self.hours)
        for record in reversed(self._records):
            if record["name"] != friend_name:
                continue
            record_time = datetime.fromisoformat(record["time"])
            if record_time > cutoff:
                return True
            break  # 只检查最近一条
        return False

    def get_recent_names(self) -> set[str]:
        """获取过去 N 小时内被发送过的用户名集合。"""
        return {r["name"] for r in self._records}


def get_sent_history_filepath(douyin_id: str) -> str:
    """获取发送历史文件路径。"""
    return os.path.join(SESSIONS_DIR, f"xxh_sent_history_{douyin_id}.json")
