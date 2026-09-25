"""抖音在线状态检测。

在线状态 + 火花状态检测。
JS 负责取数据，Python 负责判断逻辑（火花是否正常、火花天数）。

两种状态：明亮火花=今天已互发消息（已续），灰色火花=今天未互发消息（未续）。
只对未续用户进行续火花。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from playwright.async_api import Page

from src.dy_utils import _load_js

# 重试参数
LIST_RETRY_FIRST_ROUND_SECONDS = 60
LIST_RETRY_SECOND_ROUND_SECONDS = 10
LIST_RETRY_INTERVAL_SECONDS = 2
MIN_CONVERSATIONS_FOR_SUCCESS = 1


@dataclass
class OnlineStatus:
    """单个用户在线状态和火花状态。"""

    name: str
    is_online: bool = False
    renewed_today: bool = False
    # 在线/最后消息
    online_status_text: str = ""  # "在线"/"昨天在线"/"30分钟前在线" 等
    last_msg_time: str = ""  # "58分钟前"/"19:31" 等
    # 火花信息
    streak_text: str = ""  # 前端实际文本："371"/"点亮中 1/3"/"重燃中 1/3"/""

    # 由 streak_text 推导的字段
    _streak_is_normal: bool = field(init=False, repr=False)
    _streak_days: int | None = field(init=False, repr=False)

    def __post_init__(self) -> None:
        """根据 streak_text 计算派生字段。"""
        # 火花正常 = 纯数字（如 "371"）
        if self.streak_text.isdigit():
            self._streak_is_normal = True
            self._streak_days = int(self.streak_text)
        else:
            self._streak_is_normal = False
            self._streak_days = None

    @property
    def streak_is_normal(self) -> bool:
        """火花是否正常（显示为数字天数）。"""
        return self._streak_is_normal

    @property
    def streak_days(self) -> int | None:
        """火花天数。正常时返回数字，异常时返回 None。"""
        return self._streak_days

    @property
    def has_streak(self) -> bool:
        """是否有火花。

        只要前端显示了火花文本（数字/X天后消失/重燃中/点亮中）都算有火花。
        只有完全无火花文本（空字符串）才算没有火花。
        """
        return len(self.streak_text) > 0

    @property
    def streak_display(self) -> str:
        """格式化的火花显示文本。"""
        state = "✅已续" if self.renewed_today else "❌未续"
        if self.streak_text:
            return f"{self.streak_text}{state}"
        return f"无火花{state}"

    @property
    def streak_display_without_renewed(self) -> str:
        """格式化的火花显示文本（不含续状态标记）。"""
        return self.streak_text if self.streak_text else "无火花"

    @property
    def needs_attention(self) -> bool:
        """是否需要关注（有火花且今天未续）。"""
        return self.has_streak and not self.renewed_today

    @property
    def online_display(self) -> str:
        """格式化的在线状态显示文本。"""
        if self.is_online:
            return "🟢在线"
        return f"⚪{self.online_status_text}" if self.online_status_text else "⚪离线"


async def get_online_status_from_list(page: Page) -> list[OnlineStatus]:
    """从会话列表提取所有可见好友的在线状态（带重试策略）。"""
    deadline = asyncio.get_running_loop().time() + LIST_RETRY_FIRST_ROUND_SECONDS
    last_result: list[OnlineStatus] = []
    attempt = 0

    while asyncio.get_running_loop().time() < deadline:
        attempt += 1
        last_result = await _extract_once(page)

        if len(last_result) >= MIN_CONVERSATIONS_FOR_SUCCESS:
            print(f"第 {attempt} 次尝试：提取到 {len(last_result)} 个会话项")
            return last_result

        remaining = deadline - asyncio.get_running_loop().time()
        if remaining > LIST_RETRY_INTERVAL_SECONDS:
            print(
                f"第 {attempt} 次尝试：仅提取到 {len(last_result)} 个会话项，"
                f"{LIST_RETRY_INTERVAL_SECONDS}s 后重试..."
            )
            await asyncio.sleep(LIST_RETRY_INTERVAL_SECONDS)

    print(
        f"\n{LIST_RETRY_FIRST_ROUND_SECONDS} 秒内未完成提取"
        f"（仅 {len(last_result)} 个会话项），刷新页面后重试..."
    )
    await page.reload(wait_until="domcontentloaded", timeout=45_000)
    await asyncio.sleep(3)

    deadline = asyncio.get_running_loop().time() + LIST_RETRY_SECOND_ROUND_SECONDS
    attempt = 0
    while asyncio.get_running_loop().time() < deadline:
        attempt += 1
        last_result = await _extract_once(page)

        if len(last_result) >= MIN_CONVERSATIONS_FOR_SUCCESS:
            print(f"刷新后第 {attempt} 次尝试：提取到 {len(last_result)} 个会话项")
            return last_result

        remaining = deadline - asyncio.get_running_loop().time()
        if remaining > LIST_RETRY_INTERVAL_SECONDS:
            print(
                f"刷新后第 {attempt} 次尝试：仅提取到 {len(last_result)} 个会话项，"
                f"{LIST_RETRY_INTERVAL_SECONDS}s 后重试..."
            )
            await asyncio.sleep(LIST_RETRY_INTERVAL_SECONDS)

    print(f"两轮尝试后共提取到 {len(last_result)} 个会话项")
    return last_result


async def get_online_friends(page: Page) -> list[OnlineStatus]:
    """仅返回当前在线的好友列表。"""
    return [s for s in await get_online_status_from_list(page) if s.is_online]


async def get_attention_needed(page: Page) -> list[OnlineStatus]:
    """返回需要关注的好友（今天未互发消息）。"""
    return [s for s in await get_online_status_from_list(page) if s.needs_attention]


async def get_friend_status(page: Page, friend_name: str) -> OnlineStatus | None:
    """从会话列表中查找指定好友的在线状态。"""
    for status in await get_online_status_from_list(page):
        if status.name == friend_name:
            return status
    return None


async def _extract_once(page: Page) -> list[OnlineStatus]:
    """单次执行 JS 提取在线状态。"""
    js = _load_js("extract_online_status.js")
    raw = await page.evaluate(js)
    return _parse_status_json(raw)


def _parse_status_json(raw_json: str) -> list[OnlineStatus]:
    """解析 JS 返回的 JSON。火花判断逻辑在 Python 端。"""
    import json

    try:
        data = json.loads(raw_json)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []

    results: list[OnlineStatus] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name", "") or ""
        if not name:
            continue

        results.append(
            OnlineStatus(
                name=name,
                is_online=bool(entry.get("is_online", False)),
                renewed_today=bool(entry.get("renewed_today", False)),
                online_status_text=entry.get("online_status_text", "") or "",
                last_msg_time=entry.get("last_msg_time", "") or "",
                streak_text=entry.get("streak_text", "") or "",
            )
        )
    return results
