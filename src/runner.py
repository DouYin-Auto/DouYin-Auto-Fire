"""续火花调度器 - XXHRunner 核心逻辑。"""

from __future__ import annotations

import asyncio
import os
import random
from datetime import datetime, timedelta

from src.browser_session import CHAT_URL, BrowserSession
from src.config import get_config
from src.logger import get_logger
from src.online_status import OnlineStatus
from src.sent_history import SentHistory
from src.xxh_utils import (
    FULL_SEND_HOUR,
    FULL_SEND_MINUTE,
    FULL_SEND_TOLERANCE,
    OFFLINE_MAX_INTERVAL,
    OFFLINE_MIN_INTERVAL,
    ONLINE_MAX_INTERVAL,
    ONLINE_MIN_INTERVAL,
)

# Chat 页面刷新时刻（每天凌晨）
CHAT_REFRESH_HOUR = 0
CHAT_REFRESH_MINUTE = 5
CHAT_REFRESH_TOLERANCE = 120  # 容差秒数


class UserSchedule:
    """单个用户的发送调度状态。"""

    def __init__(self, name: str) -> None:
        self.name = name
        self.last_sent: datetime | None = None
        self.next_send_at: datetime | None = None
        self.current_interval: timedelta = self._random_offline_interval()
        self.is_online: bool = False
        self.just_came_online: bool = False
        self.renewed_today: bool = False

    @staticmethod
    def _random_offline_interval() -> timedelta:
        return timedelta(seconds=random.randint(OFFLINE_MIN_INTERVAL, OFFLINE_MAX_INTERVAL))

    @staticmethod
    def _random_online_interval() -> timedelta:
        return timedelta(seconds=random.randint(ONLINE_MIN_INTERVAL, ONLINE_MAX_INTERVAL))

    def update_online_status(self, online: bool) -> str | None:
        was_offline = not self.is_online
        self.is_online = online
        if online and was_offline:
            self.just_came_online = True
            self.current_interval = self._random_online_interval()
            return "came_online"
        elif not online and not was_offline:
            self.current_interval = self._random_offline_interval()
            self.just_came_online = False
            return "went_offline"
        elif not online:
            self.just_came_online = False
        return None

    def schedule_next(self, base_time: datetime | None = None) -> None:
        base = base_time or datetime.now()
        self.next_send_at = base + self.current_interval
        self.just_came_online = False

    def should_send_now(self) -> bool:
        if self.next_send_at is None:
            return True
        return datetime.now() >= self.next_send_at

    def mark_sent(self) -> None:
        now = datetime.now()
        self.last_sent = now
        self.just_came_online = False
        if self.is_online:
            self.current_interval = self._random_online_interval()
        else:
            self.current_interval = self._random_offline_interval()
        self.next_send_at = now + self.current_interval

    @property
    def renewed_today_or_pending(self) -> bool:
        now = datetime.now()
        if self.last_sent and self.last_sent.date() == now.date():
            return True
        if self.next_send_at and self.next_send_at > now:
            return True
        return False


class XXHRunner:
    """续火花执行器。"""

    def __init__(
        self,
        douyin_id: str,
        target: str = "inc",
    ) -> None:
        if target not in ("full", "inc"):
            raise ValueError(f"target 必须是 'full' 或 'inc'，得到: {target}")
        self.douyin_id = douyin_id
        self.target = target
        self._user_sched: dict[str, UserSchedule] = {}
        self._last_full_send_date: datetime.date | None = None
        self._last_chat_refresh_date: datetime.date | None = None
        self._sent_this_cycle: set[str] = set()
        self._browser: BrowserSession | None = None
        self._sent_history = SentHistory(douyin_id, hours=get_config().schedule.skip_hours)

    async def run_once(
        self,
        message: str | None = None,
        sticker: str | None = None,
    ) -> list[str]:
        """一次性续火花。

        如果配置了 full_mode_users 且 target=full，则跳过状态检查直接按列表发送。
        """
        configured_users = get_config().schedule.full_mode_users
        if self.target == "full" and configured_users:
            return await self._run_full_with_users(configured_users, message, sticker)

        sent: list[str] = []

        self._browser = BrowserSession(self.douyin_id)
        await self._browser.connect()

        statuses = await self._browser.get_statuses()
        targets = self._filter_targets(statuses)
        if not targets:
            log = get_logger()
            log.schedule("没有需要续火花的用户")
            await self._browser.close()
            return sent

        print(f"\n续火花目标 {len(targets)} 人:")
        for t in targets:
            print(f"  - {t.name} ({t.streak_text or '无火花'})")

        for friend in targets:
            print(f"\n发送给: {friend.name} ...")
            try:
                trigger = f"一次性续火花 火花={friend.streak_text or '无'}"
                await self._browser.send_to(
                    friend.name, text=message, sticker=sticker, trigger=trigger,
                )
                sent.append(friend.name)
                print(f"发送成功: {friend.name}")
            except Exception as exc:
                print(f"发送失败: {friend.name}: {exc}")

            wait = 2 + random.randint(0, 2)
            await asyncio.sleep(wait)

        print(f"\n续火花完成，共发送 {len(sent)} 人")
        await self._browser.close()
        return sent

    async def _run_full_with_users(
        self,
        users: list[str],
        message: str | None = None,
        sticker: str | None = None,
    ) -> list[str]:
        """按用户列表强制发送（跳过状态检查）。"""
        sent: list[str] = []

        self._browser = BrowserSession(self.douyin_id)
        await self._browser.connect()

        # 使用会话列表自动补充
        if not users:
            users = await self._browser.get_all_user_names()

        if not users:
            print("未获取到用户列表")
            await self._browser.close()
            return sent

        print(f"全量强制发送 {len(users)} 人:")
        for name in users:
            print(f"  - {name}")

        for name in users:
            if self._sent_history.was_sent_recently(name):
                print(f"跳过（已发送过）: {name}")
                continue

            try:
                await self._browser.search_and_send(
                    name, text=message, sticker=sticker,
                )
                sent.append(name)
                self._sent_history.record(name)
            except Exception as exc:
                print(f"发送失败: {name}: {exc}")

            wait = 2 + random.randint(0, 2)
            await asyncio.sleep(wait)

        print(f"\n全量强制发送完成，共 {len(sent)} 人")
        await self._browser.close()
        return sent

    async def run_loop(
        self,
        message: str | None = None,
        sticker: str | None = None,
    ) -> None:
        """持续运行续火花（智能调度）。"""
        _cfg = get_config().schedule
        on_online = _cfg.on_online
        on_online_delay = _cfg.online_delay

        print("续火花持续模式启动")
        print(f"  目标模式: {self.target}")
        print(f"  上线监控: {'开启' if on_online else '关闭'}")

        self._browser = BrowserSession(self.douyin_id)
        await self._browser.connect()

        try:
            while True:
                now = datetime.now()

                if self._should_full_send(now):
                    sent_ok = await self._execute_full_send(message, sticker)
                    if sent_ok:
                        self._last_full_send_date = now.date()
                        for sched in self._user_sched.values():
                            sched.schedule_next()
                        await asyncio.sleep(60)
                    else:
                        # chat 页面异常，不标记完成，延后重试
                        await asyncio.sleep(30)
                    continue

                if self._should_refresh_chat(now):
                    await self._refresh_chat_page()
                    self._last_chat_refresh_date = now.date()
                    await asyncio.sleep(60)
                    continue

                logged_in = await self._browser.ensure_logged_in()
                if not logged_in:
                    print("登录态失效，尝试重新连接...")
                    await self._browser.close()
                    await asyncio.sleep(10)
                    try:
                        self._browser = BrowserSession(self.douyin_id)
                        await self._browser.connect()
                    except RuntimeError as exc:
                        print(f"重新连接失败: {exc}")
                        await asyncio.sleep(60)
                        continue

                statuses = await self._browser.get_statuses()
                if not statuses:
                    await asyncio.sleep(60)
                    continue

                await asyncio.sleep(1)

                current_targets = {s.name for s in self._filter_targets(statuses)}
                on_offline = get_config().schedule.on_offline

                online_events: list[str] = []
                offline_events: list[str] = []

                for s in statuses:
                    if s.name not in current_targets:
                        continue
                    if s.name not in self._user_sched:
                        self._user_sched[s.name] = UserSchedule(s.name)
                    sched = self._user_sched[s.name]
                    sched.renewed_today = s.renewed_today

                    change = sched.update_online_status(s.is_online)
                    if change == "came_online":
                        online_events.append(s.name)
                    elif change == "went_offline":
                        offline_events.append(s.name)

                log = get_logger()
                online_names = [s.name for s in statuses if s.is_online]
                renewed_count = sum(1 for s in statuses if s.renewed_today)
                not_renewed_names = [s.name for s in statuses if s.needs_attention]
                total = len(statuses)
                log.status_check(
                    f"获取{total}个会话，在线{len(online_names)}人"
                    f"，已续{renewed_count}人"
                    f"，{len(not_renewed_names)}人未续: {', '.join(not_renewed_names)}"
                )

                status_dicts = [
                    {
                        "name": s.name,
                        "is_online": s.is_online,
                        "renewed_today": s.renewed_today,
                    }
                    for s in statuses
                ]
                log.log_status_json(status_dicts)

                if on_online and online_events:
                    for name in online_events:
                        sched = self._user_sched[name]
                        if sched.renewed_today_or_pending:
                            log.online_events(f"{name} 上线（已续/待发），跳过")
                            continue
                        if self._sent_history.was_sent_recently(name):
                            log.online_events(
                                f"{name} 上线（{self._sent_history.hours}h内已发送），跳过"
                            )
                            continue
                        if sched.renewed_today:
                            delay = random.randint(ONLINE_MIN_INTERVAL, ONLINE_MAX_INTERVAL)
                            sched.next_send_at = datetime.now() + timedelta(seconds=delay)
                            sched.current_interval = timedelta(seconds=delay)
                            log.online_events(
                                f"{name} 上线（已续），{delay/60:.1f}分钟后续火花"
                            )
                        else:
                            delay = on_online_delay
                            sched.next_send_at = datetime.now() + timedelta(seconds=delay)
                            sched.current_interval = timedelta(seconds=delay)
                            log.online_events(
                                f"{name} 上线（未续），{delay}s后续火花"
                            )

                if on_offline and offline_events:
                    for name in offline_events:
                        sched = self._user_sched[name]
                        if sched.renewed_today_or_pending:
                            log.online_events(f"{name} 下线（已续/待发），跳过")
                        else:
                            log.online_events(f"{name} 下线（未续），已记录提醒")

                due_users = [
                    name for name, sched in self._user_sched.items()
                    if name in current_targets and sched.should_send_now()
                ]
                for name in due_users:
                    if self._sent_history.was_sent_recently(name):
                        log.schedule(f"{name} 跳过：{self._sent_history.hours}小时内已发送过")
                        continue
                    try:
                        sched = self._user_sched[name]
                        status_str = "在线" if sched.is_online else "离线"
                        trigger = f"到期自动续火花 状态={status_str} 间隔={sched.current_interval}"
                        await self._browser.send_to(
                            name, text=message, sticker=sticker, trigger=trigger,
                        )
                        self._user_sched[name].mark_sent()
                        self._sent_history.record(name)
                    except Exception as exc:
                        log.send_result(f"目标={name} | 错误={exc}", success=False)
                        self._user_sched[name].next_send_at = datetime.now() + timedelta(minutes=5)

                    await asyncio.sleep(1)

                await asyncio.sleep(5)

        except KeyboardInterrupt:
            print("\n用户中断")
        finally:
            if self._browser:
                await self._browser.close()

    async def _execute_full_send(
        self,
        message: str | None,
        sticker: str | None,
    ) -> bool:
        """执行每日全量发送。发送前确保 chat 页面正常。

        Returns:
            True 表示发送完成，False 表示 chat 页面异常需要延后重试。
        """
        print(f"\n===== 每日全量续火花 {datetime.now().strftime('%H:%M')} =====")

        # 验证 chat 页面：搜索框 + 用户列表
        if self._browser and self._browser.is_connected:
            try:
                await self._browser._verify_chat_page(self._browser.chat_page)
                log = get_logger()
                log.browser_ops("全量发送前 chat 页面验证通过")
            except RuntimeError as exc:
                log = get_logger()
                log.browser_ops(f"全量发送前 chat 页面异常: {exc}，延后重试")
                print(f"⚠️ chat 页面验证失败，延后重试: {exc}")
                return False

        statuses = await self._browser.get_statuses()
        targets = self._filter_targets(statuses)
        if not targets:
            print("没有需要续火花的用户")
            return True

        print(f"全量发送 {len(targets)} 人:")
        for friend in targets:
            try:
                trigger = f"每日全量续火花 时间={datetime.now().strftime('%H:%M')}"
                await self._browser.send_to(
                    friend.name, text=message, sticker= sticker, trigger=trigger,
                )
                self._user_sched[friend.name].mark_sent()
                self._sent_history.record(friend.name)
                print(f"  ✅ {friend.name}")
            except Exception as exc:
                print(f"  ❌ {friend.name}: {exc}")
            await asyncio.sleep(1)
        return True

    def _should_full_send(self, now: datetime) -> bool:
        if self._last_full_send_date == now.date():
            return False
        target_time = now.replace(
            hour=FULL_SEND_HOUR, minute=FULL_SEND_MINUTE,
            second=0, microsecond=0,
        )
        diff = abs((now - target_time).total_seconds())
        return diff <= FULL_SEND_TOLERANCE

    def _should_refresh_chat(self, now: datetime) -> bool:
        """判断是否需要刷新 chat 页面（每天一次）。"""
        if self._last_chat_refresh_date == now.date():
            return False
        target_time = now.replace(
            hour=CHAT_REFRESH_HOUR, minute=CHAT_REFRESH_MINUTE,
            second=0, microsecond=0,
        )
        diff = abs((now - target_time).total_seconds())
        return diff <= CHAT_REFRESH_TOLERANCE

    async def _refresh_chat_page(self) -> None:
        """刷新 chat 页面：打开新的 → 走首次打开检查 → 关闭旧的。"""
        log = get_logger()
        if not self._browser or not self._browser.is_connected:
            log.browser_ops("浏览器未连接，跳过 chat 刷新")
            return

        log.browser_ops("=== 每日刷新 chat 页面 ===")
        context = self._browser.context
        if not context:
            log.browser_ops("浏览器上下文不可用，跳过")
            return

        # 找到旧的 chat 页面
        old_chat_page = None
        for page in context.pages:
            if CHAT_URL in page.url:
                old_chat_page = page
                break

        # 创建新的 chat 标签页
        new_page = await context.new_page()
        log.browser_ops(f"新建 chat 标签页，导航到 {CHAT_URL}")
        await new_page.goto(CHAT_URL, wait_until="domcontentloaded", timeout=15_000)
        await new_page.bring_to_front()

        try:
            # 走首次打开检查：验证搜索框 + 用户列表
            await self._browser._verify_chat_page(new_page)
            log.browser_ops("新 chat 页面验证通过")
        except RuntimeError as exc:
            log.browser_ops(f"新 chat 页面验证失败: {exc}")
            # 验证失败，关闭新页面，保持旧页面
            try:
                await new_page.close()
            except Exception:
                pass
            return

        # 验证通过，关闭旧的 chat 页面
        if old_chat_page and not old_chat_page.is_closed():
            try:
                await old_chat_page.close()
                log.browser_ops("旧 chat 页面已关闭")
            except Exception as exc:
                log.browser_ops(f"关闭旧页面出错: {exc}")

        # 重置 DouyinChat 缓存
        self._browser.chat = None

        page_count = len(context.pages)
        log.browser_ops(f"刷新完成，当前 {page_count} 个标签页")

    def _filter_targets(self, statuses: list[OnlineStatus]) -> list[OnlineStatus]:
        """筛选目标用户：有火花且未续。"""
        return [s for s in statuses if s.has_streak and s.needs_attention]


async def get_online_status_from_list_from_id(
    douyin_id: str,
) -> list[OnlineStatus]:
    """从远程浏览器获取会话列表状态（便捷函数）。"""
    from playwright.async_api import async_playwright

    from src.cdp_utils import connect_cdp_browser
    from src.dy_utils import _load_js
    from src.send_message import _find_or_open_chat_page, _verify_douyin_id
    from src.session_utils import get_session_filepath, load_session
    from src.storage_utils import restore_session

    session_file = get_session_filepath(douyin_id)
    if not os.path.exists(session_file):
        print(f"Session 文件不存在: {session_file}")
        return []

    session_data = load_session(session_file)

    async with async_playwright() as pw:
        browser = await connect_cdp_browser(pw)
        context = browser.contexts[0]

        verified = await _verify_douyin_id(context, douyin_id)

        if not verified:
            if context.pages:
                session_page = context.pages[0]
                await session_page.bring_to_front()
            else:
                session_page = await context.new_page()
            await restore_session(session_page, context, session_data)
            verified = await _verify_douyin_id(context, douyin_id)
            if not verified:
                print("登录态验证失败，终止查询")
                await browser.close()
                return []

        chat_page = await _find_or_open_chat_page(context)
        await chat_page.wait_for_timeout(2_000)

        statuses = await chat_page.evaluate(_load_js("extract_online_status.js"))
        result = _parse_status_json_str(statuses) if statuses else []

        await browser.close()
        return result


def _parse_status_json_str(raw: str) -> list[OnlineStatus]:
    """解析 JSON 字符串。"""
    import json
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []
    if not isinstance(data, list):
        return []
    return [
        OnlineStatus(
            name=e.get("name", ""),
            is_online=bool(e.get("is_online", False)),
            renewed_today=bool(e.get("renewed_today", False)),
            online_status_text=e.get("online_status_text", "") or "",
            last_msg_time=e.get("last_msg_time", "") or "",
            streak_text=e.get("streak_text", "") or "",
        )
        for e in data
        if isinstance(e, dict) and e.get("name")
    ]
