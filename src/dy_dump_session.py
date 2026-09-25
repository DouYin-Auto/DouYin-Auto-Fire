"""抖音 Session 导出 - 通过 CDP 连接远程浏览器，导出 douyin.com 的 Cookie、LocalStorage。

导出文件保存到项目根目录 sessions/ 下，格式为 JSON。
"""

import asyncio

from playwright.async_api import async_playwright

from src.cdp_utils import connect_cdp_browser, new_page_and_close_others
from src.constants import DOUYIN_DOMAIN
from src.session_utils import (
    build_session_data,
    get_session_filepath_timestamp,
    save_session,
)
from src.storage_utils import dump_cookies, dump_local_storage


async def main() -> None:
    """通过 CDP 连接远程浏览器，导出 douyin.com 的所有会话数据。"""
    async with async_playwright() as pw:
        browser = await connect_cdp_browser(pw)
        context = browser.contexts[0]

        page = await new_page_and_close_others(context)

        # 导航到抖音页面，确保能访问该源的存储
        await page.goto(f"https://www.{DOUYIN_DOMAIN}/chat", wait_until="domcontentloaded")

        # 导出各项数据
        cookies = await dump_cookies(context)
        local_storage = await dump_local_storage(page)

        # 汇总保存
        session_data = build_session_data(cookies=cookies, local_storage=local_storage)
        filepath = get_session_filepath_timestamp()
        save_session(session_data, filepath)

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
