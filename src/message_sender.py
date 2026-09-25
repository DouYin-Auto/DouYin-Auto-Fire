"""抖音私信消息发送。

支持发送文字和抖音原生表情，包含完整的发送状态确认状态机。
从第三方项目 douyin-auto-fire-main 的 app/sender.py 移植而来，
适配当前项目的 async Playwright + CDP 远程浏览器架构。

核心设计：消息气泡出现 ≠ 发送成功。抖音会先渲染气泡，再异步挂载
spinner 或重试标记。必须等待终态（成功/失败）而非仅检测气泡出现。
"""

import asyncio
import secrets
from dataclasses import dataclass
from urllib.parse import urlsplit

from playwright.async_api import Locator, Page

from src import selectors as S
from src.douyin_chat import DouyinChat, PageOperationError, first_visible

# ---------------------------------------------------------------------------
# 发送状态确认超时参数
# ---------------------------------------------------------------------------

# 单条消息确认终态的总预算（毫秒）
SEND_CONFIRM_TIMEOUT_MS = 15_000
# 轮询间隔
SEND_POLL_INTERVAL_MS = 300
# spinner 消失后的稳定窗口
SEND_STABLE_INTERVAL_MS = 500
# 新气泡初始观察窗口：气泡出现后 spinner/retry 可能延迟挂载
SEND_INITIAL_CLEAN_GRACE_MS = 2_000


# ---------------------------------------------------------------------------
# 表情数据模型
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Sticker:
    """抖音原生表情配置。

    Attributes:
        name: 表情名称（配置中的键）。
        category: 表情分类标签，可选。
        accessible_name: 无障碍名称，可选。
        fallback_index: 按索引选择的 fallback 位置，可选。
    """

    name: str
    category: str | None = None
    accessible_name: str | None = None
    fallback_index: int | None = None


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------


async def send_text(chat: DouyinChat, content: str) -> None:
    """向当前打开的聊天发送一条文字消息。

    Args:
        chat: DouyinChat 实例。
        content: 消息文本内容。

    Raises:
        PageOperationError: 文字未能写入输入框或发送状态未能确认。
    """
    editor = await chat.message_input()
    page = editor.page
    await editor.click()
    await page.keyboard.insert_text(content)

    # 确认文字已写入输入框
    try:
        await page.wait_for_function(
            """([txt]) => {
                const es = [...document.querySelectorAll(
                    '[class*=messageEditor] [contenteditable=true], '
                    + '.messageEditorinputArea'
                )];
                return es.some(e => (e.innerText || '').includes(txt));
            }""",
            arg=[content],
            timeout=5_000,
        )
    except Exception as exc:
        raise PageOperationError("文字未能写入聊天输入框") from exc

    before = await _mark_latest_outgoing_message(page)
    await page.wait_for_timeout(300)
    await _trigger_send(page)
    await _confirm_outgoing_message(page, before, label="文字", expected_text=content)


async def send_douyin_sticker(page: Page, sticker: Sticker) -> None:
    """向当前打开的聊天发送一个抖音原生表情。

    Args:
        page: Playwright Page 对象。
        sticker: 表情配置。

    Raises:
        PageOperationError: 找不到表情面板或表情项。
    """
    before = await _mark_latest_outgoing_message(page)
    try:
        button = await first_visible(page, S.STICKER_BUTTONS)
        await button.click(force=True)
        panel = await first_visible(page, S.STICKER_PANELS)

        # 切换表情分类
        if sticker.category:
            category = panel.get_by_text(sticker.category, exact=True)
            if await category.count() and await category.first.is_visible():
                await category.first.click()

        # 按描述文本精确匹配表情项
        name = sticker.accessible_name or sticker.name
        item = panel.locator(S.STICKER_ITEM_SELECTOR).filter(has_text=name)
        for index in range(await item.count()):
            candidate = item.nth(index)
            description = candidate.locator(S.STICKER_ITEM_DESC_SELECTOR)
            if await description.count() and (
                await description.first.inner_text()
            ).strip() == name:
                await _click_and_confirm_sticker(page, candidate, before, name)
                return

        # 按 aria-label / title / alt 匹配
        candidates = (
            panel.get_by_role("img", name=name, exact=True),
            panel.get_by_role("button", name=name, exact=True),
            panel.locator(f'[aria-label="{_css_escape(name)}"]'),
            panel.locator(f'[title="{_css_escape(name)}"]'),
            panel.locator(f'[alt="{_css_escape(name)}"]'),
        )
        for candidate in candidates:
            if await candidate.count() and await candidate.first.is_visible():
                await _click_and_confirm_sticker(page, candidate.first, before, name)
                return

        # 按索引 fallback
        if sticker.fallback_index is not None:
            items = panel.locator("[role='button'], img, [aria-label], [title]")
            if await items.count() > sticker.fallback_index:
                await _click_and_confirm_sticker(
                    page, items.nth(sticker.fallback_index), before, name
                )
                return

        raise PageOperationError(f"在抖音表情面板中找不到原生表情: {sticker.name}")
    finally:
        await _restore_composer(page)


# ---------------------------------------------------------------------------
# 发送触发与状态确认
# ---------------------------------------------------------------------------


async def _trigger_send(page: Page) -> None:
    """点击发送按钮，找不到则按 Enter 键。"""
    button = None
    for selector in S.SEND_BUTTONS:
        candidate = page.locator(selector).first
        try:
            if await candidate.count() and await candidate.is_visible():
                button = candidate
                break
        except Exception:
            continue
    if button is not None:
        await button.click()
    else:
        await page.keyboard.press("Enter")


async def _publish_ready(page: Page) -> bool:
    """检查发送按钮是否可见可用。"""
    for selector in S.SEND_BUTTONS:
        candidate = page.locator(selector).first
        try:
            if await candidate.count() and await candidate.is_visible():
                return True
        except Exception:
            continue
    return False


def _monotonic() -> float:
    """单调时钟，用于发送状态确认的超时控制。"""
    return asyncio.get_running_loop().time()


async def _mark_latest_outgoing_message(page: Page) -> tuple[str, str]:
    """给当前最新的已发送消息打上唯一锚点标记。

    Returns:
        (anchor, before_content): 锚点值和标记前的消息内容 HTML。
    """
    anchor = secrets.token_hex(8)
    latest = page.locator(S.LATEST_OUTGOING_MESSAGE).first
    if not await latest.count():
        return anchor, ""

    content = latest.locator('[data-e2e="msg-item-content"]').first
    before_content = (
        await content.inner_html()
        if await content.count()
        else await latest.inner_html()
    )
    await latest.evaluate(
        "(element, value) => element.setAttribute('data-douyin-sender-anchor', value)",
        anchor,
    )
    return anchor, before_content


async def _confirm_outgoing_message(
    page: Page,
    before: tuple[str, str],
    label: str,
    resource_key: str = "",
    expected_text: str = "",
) -> None:
    """确认消息已成功发送到终态。

    Args:
        page: Playwright Page 对象。
        before: (anchor, before_content) 标记前的状态。
        label: 消息类型标签（用于错误信息）。
        resource_key: 表情图片资源键，可选。
        expected_text: 预期文本内容，可选。

    Raises:
        PageOperationError: 发送超时、发送失败或未检测到新消息。
    """
    anchor, before_content = before
    try:
        await page.wait_for_function(
            """([selector, anchor, previousContent, expectedResource, expectedText]) => {
                const message = document.querySelector(selector);
                if (!message) return false;
                const content = message.querySelector(
                    '[data-e2e="msg-item-content"]'
                ) || message;
                const isNewMessage =
                    message.getAttribute('data-douyin-sender-anchor') !== anchor ||
                    content.innerHTML !== previousContent;
                if (!isNewMessage) return false;
                if (expectedText) {
                    const normalize = value => (value || '').replace(
                        /[\\s\\u200B\\u200C\\u200D\\uFEFF]+/g, ' '
                    ).trim();
                    return normalize(content.innerText).includes(
                        normalize(expectedText)
                    );
                }
                if (!expectedResource) return true;
                const images = [...content.querySelectorAll('img')];
                return images.some(
                    image => (image.src || '').includes(expectedResource)
                ) || images.length > 0;
            }""",
            arg=[
                S.LATEST_OUTGOING_MESSAGE,
                anchor,
                before_content,
                resource_key,
                expected_text,
            ],
            timeout=15_000,
        )
        latest = page.locator(S.LATEST_OUTGOING_MESSAGE).first
        await _await_send_terminal_state(page, latest, label)
    except PageOperationError:
        raise
    except Exception as exc:
        raise PageOperationError(f"{label}已发送，但没有检测到新的已发送消息") from exc
    finally:
        anchors = page.locator("[data-douyin-sender-anchor]")
        try:
            await anchors.evaluate_all(
                "elements => elements.forEach(element => "
                "element.removeAttribute('data-douyin-sender-anchor'))"
            )
        except Exception:
            pass


async def _await_send_terminal_state(
    page: Page,
    scope: Locator,
    label: str,
    timeout_ms: int = SEND_CONFIRM_TIMEOUT_MS,
) -> None:
    """等待单条消息到达发送终态（成功或失败）。

    状态机:

        MATCHED
           ↓
        OBSERVING_INITIAL  (气泡已匹配，状态未定)
           |  失败标记可见        -> FAILED
           |  pending spinner 可见 -> WAITING_PENDING
           |  整个 grace 窗口 clean -> SUCCESS
           ↓
        WAITING_PENDING  (spinner 可见)
           |  失败标记可见        -> FAILED
           |  spinner 消失        -> STABILIZING
           ↓
        STABILIZING  (spinner 刚消失)
           |  失败标记可见        -> FAILED
           |  spinner 再次出现    -> WAITING_PENDING
           |  稳定 clean 窗口保持  -> SUCCESS
    """
    deadline = _monotonic() + timeout_ms / 1000

    # Phase 1: 观察新气泡
    grace_deadline = _monotonic() + SEND_INITIAL_CLEAN_GRACE_MS / 1000
    while _monotonic() < grace_deadline:
        if _monotonic() >= deadline:
            raise PageOperationError(
                f"{label}发送状态未能确认（发送超时或状态不确定），为避免重复不会自动重试"
            )
        if await _marker_visible(scope, S.SEND_FAILURE_MARKERS):
            raise PageOperationError(f"{label}发送失败，页面提示可以重试")
        if await _marker_visible(scope, S.SEND_PENDING_MARKERS):
            break  # -> Phase 2
        await page.wait_for_timeout(SEND_POLL_INTERVAL_MS)
    else:
        # grace 窗口全程 clean -> 快速成功
        return

    # Phase 2: 等待 spinner 消失并稳定
    while True:
        if _monotonic() >= deadline:
            raise PageOperationError(
                f"{label}发送状态未能确认（发送超时或状态不确定），为避免重复不会自动重试"
            )
        if await _marker_visible(scope, S.SEND_FAILURE_MARKERS):
            raise PageOperationError(f"{label}发送失败，页面提示可以重试")
        if not await _marker_visible(scope, S.SEND_PENDING_MARKERS):
            # spinner 消失，要求稳定窗口内保持 clean
            await page.wait_for_timeout(SEND_STABLE_INTERVAL_MS)
            if await _marker_visible(scope, S.SEND_FAILURE_MARKERS):
                raise PageOperationError(f"{label}发送失败，页面提示可以重试")
            if not await _marker_visible(scope, S.SEND_PENDING_MARKERS):
                return  # 终态: 成功
        await page.wait_for_timeout(SEND_POLL_INTERVAL_MS)


# ---------------------------------------------------------------------------
# 表情发送辅助
# ---------------------------------------------------------------------------


async def _click_and_confirm_sticker(
    page: Page, item: Locator, before: tuple[str, str], name: str
) -> None:
    """点击表情项并确认发送成功，失败时尝试重试。"""
    resource_key = await _sticker_resource_key(item)
    await item.click(force=True)
    try:
        await _confirm_sticker_sent(page, before, name, resource_key)
    except PageOperationError as exc:
        if "页面提示可以重试" in str(exc) and await _click_retry_on_latest_failed_message(page):
            await _confirm_sticker_sent(page, before, name, resource_key)
            return
        if await _publish_ready(page):
            await _trigger_send(page)
            await _confirm_sticker_sent(page, before, name, resource_key)
        else:
            raise


async def _sticker_resource_key(item: Locator) -> str:
    """提取表情图片的资源键（URL 路径最后一段）。"""
    src = await item.get_attribute("src")
    if not src:
        image = item.locator("img").first
        if await image.count():
            src = await image.get_attribute("src")
    if not src:
        return ""
    return urlsplit(src).path.rsplit("/", 1)[-1]


async def _confirm_sticker_sent(
    page: Page,
    before: tuple[str, str],
    name: str,
    resource_key: str = "",
) -> None:
    """确认表情已成功发送。"""
    await _confirm_outgoing_message(
        page, before, f'原生表情"{name}"', resource_key=resource_key
    )


async def _click_retry_on_latest_failed_message(page: Page) -> bool:
    """点击最新失败消息的重试按钮。"""
    latest = page.locator(S.LATEST_OUTGOING_MESSAGE).first
    for selector in S.SEND_RETRY_MARKERS:
        marker = latest.locator(selector).first
        try:
            if await marker.count() and await marker.is_visible():
                await marker.click(force=True)
                return True
        except Exception:
            continue
    return False


async def _restore_composer(page: Page, timeout_ms: int = 10_000) -> None:
    """恢复输入框焦点（发送表情后输入框可能失焦）。"""
    try:
        await page.keyboard.press("Escape")
    except Exception:
        pass
    try:
        editor = await first_visible(page, S.MESSAGE_INPUTS, timeout_ms)
    except Exception:
        return
    try:
        await editor.click(timeout=timeout_ms)
        await editor.focus()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 通用辅助
# ---------------------------------------------------------------------------


async def _marker_visible(scope: Locator, selectors: tuple[str, ...]) -> bool:
    """检查作用域内是否有任何选择器匹配到可见元素。"""
    for selector in selectors:
        marker = scope.locator(selector).first
        try:
            if await marker.count() and await marker.is_visible():
                return True
        except Exception:
            continue
    return False


def _css_escape(value: str) -> str:
    """转义 CSS 选择器中的特殊字符。"""
    return value.replace("\\", "\\\\").replace('"', '\\"')
