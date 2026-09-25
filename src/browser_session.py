"""浏览器会话管理 - 维护单一 CDP 浏览器连接。"""

from __future__ import annotations

import asyncio

from playwright.async_api import Browser, BrowserContext, Page

from src.cdp_utils import connect_cdp_browser
from src.config import get_config
from src.constants import DOUYIN_DOMAIN
from src.douyin_chat import DouyinChat
from src.dy_utils import _load_js, extract_douyin_id
from src.logger import get_logger
from src.message_sender import Sticker, send_douyin_sticker, send_text
from src.online_status import OnlineStatus, _parse_status_json
from src.session_utils import (
    build_session_data,
    extract_sessionid,
    get_session_filepath,
    save_session,
)
from src.storage_utils import dump_cookies, dump_local_storage

# 配置参数
_cfg = get_config().schedule
CHAT_URL = f"https://www.{DOUYIN_DOMAIN}/chat"
USER_URL = f"https://www.{DOUYIN_DOMAIN}/user/self"
VERIFY_TIMEOUT = 300
SEARCH_RECOVER_TIMEOUT = 300
MAX_VERIFY_RETRIES = 3
MAX_SEARCH_RETRIES = 3
SAVE_INTERVAL = 120


class BrowserSession:
    """管理单个浏览器连接，运行期间复用。"""

    def __init__(self, douyin_id: str) -> None:
        self.douyin_id = douyin_id
        self.browser: Browser | None = None
        self.context: BrowserContext | None = None
        self.chat_page: Page | None = None
        self.chat: DouyinChat | None = None
        self._save_task: asyncio.Task | None = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def _cdp_eval(self, page: Page, script: str, label: str = "") -> any:
        """执行 JS 并记录 CDP 指令日志。"""
        log = get_logger()
        short = script.strip().split("\n")[0][:60]
        log.browser_ops(f"CDP evaluate[{label}]: {short}")
        return await page.evaluate(script)

    async def _cdp_goto(self, page: Page, url: str) -> None:
        """导航并记录 CDP 指令日志。"""
        log = get_logger()
        log.browser_ops(f"CDP goto: {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=15_000)

    async def _cdp_click(self, page: Page, selector: str) -> None:
        """点击并记录 CDP 指令日志。"""
        log = get_logger()
        log.browser_ops(f"CDP click: {selector}")
        el = await page.query_selector(selector)
        if el:
            await el.click(force=True)

    async def _cdp_esc(self, page: Page) -> None:
        """模拟 ESC 并记录 CDP 指令日志。"""
        log = get_logger()
        log.browser_ops("CDP press: Escape")
        await page.keyboard.press("Escape")

    async def connect(self) -> None:
        """连接浏览器并验证抖音号。

        流程：
        1. 关闭其他标签页，最多保留 1 个 chat 页面
        2. 切换到 user/self 核对抖音号（1Hz，最多 120 秒）
        3. 正确 → 切回 chat
        4. 查找失败 → 开启新 chat 标签页，关闭旧的
        """
        if self._connected:
            return

        log = get_logger()
        from playwright.async_api import async_playwright

        self._pw = async_playwright()
        self._playwright = await self._pw.start()
        self.browser = await connect_cdp_browser(self._playwright)
        self.context = self.browser.contexts[0]

        # === 步骤 1: 关闭其他标签页，最多保留 1 个 chat ===
        await self._cleanup_tabs(keep_one_chat=True)

        # === 步骤 2: 开启/切换到 user/self 核对抖音号 ===
        verified_id = None
        for retry in range(MAX_VERIFY_RETRIES):
            # 查找已有 user/self 页面或创建新的
            user_page = None
            for p in self.context.pages:
                if USER_URL in p.url:
                    user_page = p
                    break

            if user_page is None:
                # 不超过 2 标签限制
                if len(self.context.pages) >= 2:
                    for p in self.context.pages:
                        if CHAT_URL in p.url:
                            await p.close()
                            break
                user_page = await self.context.new_page()
                log.browser_ops("CDP new_page: user/self")
                await self._cdp_goto(user_page, USER_URL)
            else:
                # 切换到已有页面
                if USER_URL not in user_page.url:
                    await self._cdp_goto(user_page, USER_URL)

            # 切换到 user/self（激活）
            await user_page.bring_to_front()

            # 1Hz 轮询，最多 120 秒
            verified_id = None
            for i in range(VERIFY_TIMEOUT):
                if retry > 0 and i == 0:
                    await user_page.reload(wait_until="domcontentloaded", timeout=15_000)
                verified_id = await extract_douyin_id(user_page)
                if verified_id:
                    break
                await asyncio.sleep(1)

            if verified_id == self.douyin_id:
                log.browser_ops("抖音号验证通过")
                break
            if retry < MAX_VERIFY_RETRIES - 1:
                log.browser_ops(f"抖音号不匹配（{verified_id}），刷新重试")

        log.browser_ops(f"期望抖音号: {self.douyin_id}, 实际: {verified_id}")

        if verified_id != self.douyin_id:
            raise RuntimeError(f"抖音号验证失败: 期望 {self.douyin_id}, 实际 {verified_id}")

        # === 步骤 3: 关闭 user/self，切回 chat ===
        for p in self.context.pages:
            if USER_URL in p.url:
                await p.close()
                break

        # 查找剩余的 chat 页面
        chat_page = None
        for p in self.context.pages:
            if CHAT_URL in p.url:
                chat_page = p
                break

        # 如果没有 chat 页面，创建新的
        if chat_page is None:
            chat_page = await self.context.new_page()
            await chat_page.goto(CHAT_URL, wait_until="domcontentloaded", timeout=15_000)

        self.chat_page = chat_page
        await self.chat_page.bring_to_front()

        # === 步骤 4: 检查搜索框 + 用户列表 ===
        for retry in range(MAX_SEARCH_RETRIES):
            # 1Hz 轮询，最多 120 秒
            success = False
            for _ in range(SEARCH_RECOVER_TIMEOUT):
                check = await self._cdp_eval(self.chat_page, """() => {
                  const search = document.querySelector('input[placeholder*="搜索"]');
                  const items = document.querySelectorAll('[data-e2e="conversation-item"]');
                  return {hasSearch: !!search, itemCount: items.length};
                }""", label="check_search")
                if check["hasSearch"] and check["itemCount"] > 0:
                    success = True
                    break
                await self._cdp_esc(self.chat_page)
                await asyncio.sleep(1)

            if success:
                break

            # 失败 → 开启新 chat 标签页，关闭旧的
            if retry < MAX_SEARCH_RETRIES - 1:
                log.browser_ops(
                    f"搜索框/用户列表缺失，"
                    f"开新 chat 标签页（第 {retry + 1}/{MAX_SEARCH_RETRIES} 次）"
                )
                old_chat = self.chat_page
                new_chat = await self.context.new_page()
                await new_chat.goto(CHAT_URL, wait_until="domcontentloaded", timeout=15_000)
                await new_chat.bring_to_front()
                self.chat_page = new_chat
                try:
                    await old_chat.close()
                except Exception:
                    pass

        # 最终确认
        check = await self.chat_page.evaluate("""() => {
          const search = document.querySelector('input[placeholder*="搜索"]');
          const items = document.querySelectorAll('[data-e2e="conversation-item"]');
          return {hasSearch: !!search, itemCount: items.length};
        }""")

        if not check["hasSearch"] or check["itemCount"] == 0:
            raise RuntimeError(
                f"搜索框/用户列表无法恢复: search={check['hasSearch']}, "
                f"items={check['itemCount']}"
            )

        self._connected = True
        self._start_auto_save()
        log.browser_ops(f"浏览器连接成功，获取 {check['itemCount']} 个会话")

    async def _cleanup_tabs(self, keep_one_chat: bool = True) -> None:
        """关闭多余标签页（安全顺序：先确保有目标页面，再关闭其他）。"""
        # 先检查是否有 chat 页面，没有则先打开一个
        has_chat = any(CHAT_URL in p.url for p in self.context.pages)
        if keep_one_chat and not has_chat:
            # 先打开 chat 页面，确保浏览器不会关闭
            new_page = await self.context.new_page()
            await self._cdp_goto(new_page, CHAT_URL)

        # 现在可以安全关闭其他页面
        if keep_one_chat:
            chat_pages = [p for p in self.context.pages if CHAT_URL in p.url]
            # 保留最后一个 chat，关闭其他
            for p in chat_pages[:-1]:
                await p.close()
            # 关闭所有非 chat 页面
            non_chat = [p for p in self.context.pages if CHAT_URL not in p.url]
            for p in non_chat:
                await p.close()

    async def ensure_logged_in(self) -> bool:
        """检查是否仍然登录（搜索框检测）。"""
        if not self.chat_page or self.chat_page.is_closed():
            return False
        try:
            search = await self.chat_page.query_selector('input[placeholder*="搜索"]')
            return bool(search and await search.is_visible())
        except Exception:
            return False

    async def get_statuses(self, retry_attempts: int = 3) -> list[OnlineStatus]:
        """获取在线状态列表。"""
        if not self.chat_page or self.chat_page.is_closed():
            return []
        for attempt in range(retry_attempts):
            if attempt > 0:
                # 只有失败后才刷新页面
                await self._refresh_chat_page()
            js = _load_js("extract_online_status.js")
            raw = await self._cdp_eval(self.chat_page, js, label="extract_status")
            statuses = _parse_status_json(raw)
            if len(statuses) >= 1:
                return statuses
            if attempt < retry_attempts - 1:
                await asyncio.sleep(2)
        raise RuntimeError("获取会话列表失败，请检查登录态")

    async def send_to(
        self,
        friend_name: str,
        text: str | None = None,
        sticker: str | None = None,
        trigger: str = "",
    ) -> None:
        """发送消息给指定好友。"""
        log = get_logger()
        content_parts = []
        if text:
            content_parts.append(f"文字={text}")
        if sticker:
            content_parts.append(f"表情={sticker}")
        content = " ".join(content_parts) if content_parts else "(无内容)"
        log.send_result(f"目标={friend_name} | 内容={content} | 触发={trigger}", success=True)

        if not self.chat_page or self.chat_page.is_closed():
            raise RuntimeError("chat 页面未就绪")

        if self.chat is None or self.chat.page != self.chat_page:
            self.chat = DouyinChat(self.chat_page, timeout_ms=15_000)

        await self.chat.open_target(friend_name, retries=1)

        if text:
            await send_text(self.chat, text)
            await self.chat_page.wait_for_timeout(1_000)

        if sticker:
            await send_douyin_sticker(self.chat_page, Sticker(name=sticker))

        # 发送后退出搜索框
        await self._exit_search()

    async def _exit_search(self) -> None:
        """退出搜索框（按 Escape + 点击空白区域）。"""
        if not self.chat_page or self.chat_page.is_closed():
            return
        await self._cdp_esc(self.chat_page)
        await self._cdp_eval(self.chat_page, """() => {
          const content = document.querySelector('[class*="ChatContent"], [class*="message-list"]');
          if (content) { content.click(); }
        }""", label="exit_search")

    async def search_and_send(
        self,
        friend_name: str,
        text: str | None = None,
        sticker: str | None = None,
        trigger: str = "全量强制发送",
    ) -> None:
        """搜索并发送（跳过在线状态检查）。"""
        log = get_logger()
        content_parts = []
        if text:
            content_parts.append(f"文字={text}")
        if sticker:
            content_parts.append(f"表情={sticker}")
        content = " ".join(content_parts) if content_parts else "(无内容)"
        log.send_result(f"目标={friend_name} | 内容={content} | 触发={trigger}", success=True)

        if not self.chat_page or self.chat_page.is_closed():
            raise RuntimeError("chat 页面未就绪")

        if self.chat is None or self.chat.page != self.chat_page:
            self.chat = DouyinChat(self.chat_page, timeout_ms=15_000)

        await self.chat.open_target(friend_name, retries=2)

        if text:
            await send_text(self.chat, text)
            await self.chat_page.wait_for_timeout(1_000)

        if sticker:
            await send_douyin_sticker(self.chat_page, Sticker(name=sticker))

        # 发送后退出搜索框
        await self._exit_search()

    async def get_all_user_names(self) -> list[str]:
        """从会话列表提取所有用户昵称。"""
        if not self.chat_page or self.chat_page.is_closed():
            return []
        result = await self.chat_page.evaluate("""() => {
          const items = document.querySelectorAll('[data-e2e="conversation-item"]');
          const names = [];
          for (const item of items) {
            const titleEl = item.querySelector('[class="conversationConversationItemtitle"]');
            if (titleEl) {
              const name = titleEl.textContent.trim();
              if (name) names.push(name);
            }
          }
          return names;
        }""")
        return result if isinstance(result, list) else []

    def _start_auto_save(self) -> None:
        """启动自动保存任务。"""
        if self._save_task and not self._save_task.done():
            return
        self._save_task = asyncio.create_task(self._auto_save_loop())

    async def _auto_save_loop(self) -> None:
        """自动保存 session 的后台任务。"""
        while self._connected:
            await asyncio.sleep(SAVE_INTERVAL)
            try:
                await self.save_session()
            except Exception:
                pass

    async def save_session(self) -> None:
        """保存当前 session。"""
        if not self.context or not self.chat_page:
            return
        sessionid = await extract_sessionid(self.context)
        cookies = await dump_cookies(self.context)
        local_storage = await dump_local_storage(self.chat_page)
        session_data = build_session_data(
            douyin_id=self.douyin_id,
            sessionid=sessionid,
            cookies=cookies,
            local_storage=local_storage,
        )
        filepath = get_session_filepath(self.douyin_id)
        save_session(session_data, filepath)

    async def _refresh_chat_page(self) -> None:
        """刷新聊天页面数据。"""
        if not self.chat_page or self.chat_page.is_closed():
            return
        await self.chat_page.reload(wait_until="domcontentloaded", timeout=30_000)
        await self.chat_page.wait_for_timeout(3_000)

    async def close(self) -> None:
        """关闭浏览器连接。"""
        self._connected = False
        if self._save_task:
            self._save_task.cancel()
        try:
            await self.save_session()
        except Exception:
            pass
        if self.browser:
            await self.browser.close()
        if hasattr(self, '_playwright'):
            await self._playwright.stop()
