"""CDP 连接与浏览器上下文管理工具。

提供通过 CDP 连接 CloakBrowser 远程浏览器、创建新标签页并关闭旧标签页等共享操作。
"""

from playwright.async_api import Browser, BrowserContext, Page

from src.constants import AUTH_TOKEN, CDP_ENDPOINT
from src.logger import get_logger


async def connect_cdp_browser(pw) -> Browser:
    """通过 CDP 连接远程浏览器，返回 Browser 实例。"""
    log = get_logger()
    log.browser_ops(f"CDP 连接: {CDP_ENDPOINT}")
    browser = await pw.chromium.connect_over_cdp(
        CDP_ENDPOINT,
        headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
    )
    context = browser.contexts[0]
    pages = context.pages
    log.browser_ops(f"CDP 连接成功，当前 {len(pages)} 个标签页")
    return browser


async def new_page_and_close_others(context: BrowserContext) -> Page:
    """创建新标签页，关闭所有旧标签页。"""
    log = get_logger()
    old_count = len(context.pages)
    page = await context.new_page()
    closed = 0
    for old_page in context.pages:
        if old_page is not page:
            await old_page.close()
            closed += 1
    log.browser_ops(f"新建标签页，关闭 {closed}/{old_count} 个旧标签页")
    return page
