"""抖音私信页面操作。

提供搜索好友、打开聊天窗口、确认聊天已打开等核心页面操作。
从第三方项目 douyin-auto-fire-main 的 app/douyin.py 移植而来，
适配当前项目的 async Playwright + CDP 远程浏览器架构。
"""

import asyncio
import re

from playwright.async_api import Locator, Page

from src import selectors as S


class PageOperationError(RuntimeError):
    """页面操作异常。"""


RETRY_DELAY_MS = 3_000


class DouyinChat:
    """抖音私信页面操作器。

    封装了搜索好友、打开聊天、确认聊天等操作。
    """

    def __init__(
        self,
        page: Page,
        timeout_ms: int = 15_000,
        confirm_timeout_ms: int = 15_000,
    ) -> None:
        """初始化。

        Args:
            page: Playwright Page 对象，已导航到私信页面。
            timeout_ms: 页面元素等待超时（毫秒）。
            confirm_timeout_ms: 确认聊天已打开的超时（毫秒）。
        """
        self.page = page
        self.timeout_ms = timeout_ms
        self.confirm_timeout_ms = confirm_timeout_ms

    async def open_target(self, name: str, retries: int = 1) -> None:
        """搜索并打开指定好友的聊天窗口。

        Args:
            name: 好友名称。
            retries: 失败后重试次数。

        Raises:
            PageOperationError: 搜索不到好友或聊天未打开。
        """
        last_error: Exception | None = None
        for attempt in range(retries + 1):
            try:
                await self._open_target_once(name)
                return
            except Exception as exc:
                last_error = exc
                if attempt < retries:
                    await self.page.wait_for_timeout(RETRY_DELAY_MS)
        if last_error is not None:
            raise last_error
        raise PageOperationError("打开聊天失败")

    async def _open_target_once(self, name: str) -> None:
        """单次搜索并打开好友聊天。"""
        # 先关闭可能存在的模态弹窗（如"点亮聊天火花"提示）
        await self._dismiss_modal()

        search = await first_visible(self.page, S.SEARCH_INPUTS, self.timeout_ms)
        await search.click(force=True)
        await search.fill("")
        await search.fill(name)
        await self.page.wait_for_timeout(1_500)

        result = await self._search_result(name)
        if result is None:
            raise PageOperationError("搜索不到目标好友")
        await result.click(force=True)
        await self._confirm_opened(name)

    async def _dismiss_modal(self) -> None:
        """关闭可能存在的模态弹窗（如"点亮聊天火花"提示）。"""
        try:
            # 检查是否有 semi-modal-wrap 遮挡
            modal = self.page.locator(".semi-modal-wrap").first
            if await modal.count() and await modal.is_visible():
                # 按 Escape 关闭弹窗，或点击其他位置
                await self.page.keyboard.press("Escape")
                await self.page.wait_for_timeout(500)
        except Exception:
            pass

    async def _search_result(self, name: str) -> Locator | None:
        """在搜索结果中查找目标好友。

        两阶段优先匹配：先精确匹配好友名，再允许群聊名后缀（如 "4161(7)"）。
        """
        search_items = self.page.locator(
            ", ".join(S.SEARCH_ITEM_SELECTORS)
        )

        # Pass 1: 精确匹配好友名
        for index in range(await search_items.count()):
            item = search_items.nth(index)
            name_locator = await _visible_exact_text_locator(
                item, S.SEARCH_ITEM_TITLE_SELECTORS, name
            )
            if name_locator is None:
                continue
            button = item.locator(S.SEARCH_ITEM_CHAT_BTN).first
            try:
                if await button.count() and await button.is_visible():
                    return button
            except Exception:
                continue

        # Pass 2: 群聊名后缀匹配（如 "4161(7)"）
        for index in range(await search_items.count()):
            item = search_items.nth(index)
            name_locator = await _visible_group_text_locator(
                item, S.SEARCH_ITEM_TITLE_SELECTORS, name
            )
            if name_locator is None:
                continue
            button = item.locator(S.SEARCH_ITEM_CHAT_BTN).first
            try:
                if await button.count() and await button.is_visible():
                    return button
            except Exception:
                continue

        # Fallback: 在会话列表中查找
        for selector in S.CONVERSATION_ROW_SELECTORS:
            rows = self.page.locator(selector)
            for index in range(await rows.count()):
                row = rows.nth(index)
                # 精确匹配
                title_locator = await _visible_exact_text_locator(
                    row, S.CONVERSATION_TITLE_SELECTORS, name
                )
                if title_locator is None:
                    # 群聊后缀匹配
                    title_locator = await _visible_group_text_locator(
                        row, S.CONVERSATION_TITLE_SELECTORS, name
                    )
                if title_locator is None:
                    continue
                try:
                    if await row.is_visible():
                        return row
                except Exception:
                    continue

        # 隐藏标题 fallback
        hidden_titles = self.page.locator(
            "[class*='conversationConversationItemtitle']"
        )
        for index in range(await hidden_titles.count()):
            title = hidden_titles.nth(index)
            if not await _text_equals(title, name):
                continue
            row = title.locator(
                "xpath=ancestor::*[contains(@class, 'conversationConversationItem')][1]"
            )
            if await row.count() and await row.is_visible():
                return row

        return None

    async def message_input(self) -> Locator:
        """定位消息输入框。"""
        return await first_visible(self.page, S.MESSAGE_INPUTS, self.timeout_ms)

    async def _confirm_opened(self, name: str, timeout_ms: int | None = None) -> None:
        """确认聊天窗口已正确打开。

        通过检查聊天面板标题是否匹配好友名来确认。
        """
        timeout = timeout_ms if timeout_ms is not None else self.confirm_timeout_ms
        deadline = asyncio.get_running_loop().time() + timeout / 1000
        while True:
            last_error = await self._chat_open_error(name)
            if last_error is None:
                return
            if asyncio.get_running_loop().time() >= deadline:
                raise last_error
            await self.page.wait_for_timeout(500)

    async def _chat_open_error(self, name: str) -> PageOperationError | None:
        """检查聊天是否已打开，返回错误或 None。"""
        for selector in S.CHAT_PANEL_MARKERS[:3]:
            headers = self.page.locator(selector)
            for index in range(await headers.count()):
                header = headers.nth(index)
                try:
                    if not await header.is_visible():
                        continue
                except Exception:
                    continue
                if await _visible_exact_or_group_text_in(
                    header, S.CHAT_TITLE_SELECTORS, name
                ):
                    return None

        composer_visible = await self._composer_visible()
        return PageOperationError(
            f"点击搜索结果后无法确认聊天已打开（输入框: {'有' if composer_visible else '无'}）"
        )

    async def _composer_visible(self) -> bool:
        """检查消息输入框是否可见。"""
        for selector in S.MESSAGE_INPUTS:
            locator = self.page.locator(selector).first
            try:
                if await locator.count() and await locator.is_visible():
                    return True
            except Exception:
                continue
        return False


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------


async def first_visible(
    page: Page, selectors: tuple[str, ...], timeout_ms: int = 15_000
) -> Locator:
    """按顺序尝试多个选择器，返回第一个可见的元素。

    Args:
        page: Playwright Page 对象。
        selectors: CSS 选择器元组，按优先级排列。
        timeout_ms: 总超时时间（毫秒）。

    Returns:
        第一个可见的 Locator。

    Raises:
        PageOperationError: 所有选择器都未匹配到可见元素。
    """
    per_selector = max(500, timeout_ms // max(1, len(selectors)))
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            await locator.wait_for(state="visible", timeout=per_selector)
            return locator
        except Exception:
            continue
    raise PageOperationError(f"找不到页面元素，已尝试: {', '.join(selectors)}")


async def _visible_exact_text_locator(
    container: Locator, selectors: tuple[str, ...], expected: str
) -> Locator | None:
    """在容器中查找文本精确匹配且可见的元素。"""
    for selector in selectors:
        nodes = container.locator(selector)
        for index in range(await nodes.count()):
            node = nodes.nth(index)
            if await _text_equals(node, expected):
                try:
                    if await node.is_visible():
                        return node
                except Exception:
                    continue
    return None


async def _visible_group_text_locator(
    container: Locator, selectors: tuple[str, ...], expected: str
) -> Locator | None:
    """在容器中查找群聊名匹配（允许 (N) 后缀）且可见的元素。"""
    for selector in selectors:
        nodes = container.locator(selector)
        for index in range(await nodes.count()):
            node = nodes.nth(index)
            if await _group_name_matches(node, expected):
                try:
                    if await node.is_visible():
                        return node
                except Exception:
                    continue
    return None


async def _visible_exact_or_group_text_in(
    container: Locator, selectors: tuple[str, ...], expected: str
) -> bool:
    """检查容器中是否存在精确匹配或群聊后缀匹配的可见元素。"""
    if await _visible_exact_text_locator(container, selectors, expected) is not None:
        return True
    return await _visible_group_text_locator(container, selectors, expected) is not None


async def _text_equals(locator: Locator, expected: str) -> bool:
    """判断元素的 inner_text 是否与 expected 精确匹配。"""
    try:
        return (await locator.inner_text(timeout=500)).strip() == expected
    except Exception:
        return False


# 群聊名后缀正则模板：如 "4161" / "4161(7)" / "4161（123）"
_GROUP_COUNT_SUFFIX_RE_TEMPLATE = r"{name}\s*[\(（]\s*\d+\s*[\)）]"


def _group_count_suffix_matches(actual: str, expected: str) -> bool:
    """检查 actual 是否匹配 expected 或 expected(N) 的群聊名格式。"""
    actual = actual.strip()
    expected = expected.strip()
    if actual == expected:
        return True
    pattern = _GROUP_COUNT_SUFFIX_RE_TEMPLATE.format(name=re.escape(expected))
    return re.fullmatch(pattern, actual) is not None


async def _group_name_matches(locator: Locator, expected: str) -> bool:
    """判断元素的 inner_text 是否匹配群聊名格式。"""
    try:
        return _group_count_suffix_matches(
            await locator.inner_text(timeout=500), expected
        )
    except Exception:
        return False
