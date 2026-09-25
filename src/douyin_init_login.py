"""抖音初始化登录 - 通过 CDP 连接 CloakBrowser 远程浏览器，打开抖音聊天页面。

认证方式: 将 Bearer Token 通过 extra HTTP headers 传入 CDP 连接。
"""

import argparse
import asyncio

from playwright.async_api import async_playwright

from src.cdp_utils import connect_cdp_browser, new_page_and_close_others
from src.constants import DOUYIN_DOMAIN
from src.dy_utils import extract_douyin_id, wait_for_login_cookie
from src.session_utils import (
    build_session_data,
    extract_sessionid,
    get_session_filepath,
    save_session,
)
from src.storage_utils import clear_storage, dump_cookies, dump_local_storage


async def main(clear: bool = True) -> None:
    """通过 CDP 直接连接远程浏览器，清空存储后打开抖音聊天页面。

    Args:
        clear: 是否清空 douyin.com 相关存储数据。
    """
    async with async_playwright() as pw:
        browser = await connect_cdp_browser(pw)
        context = browser.contexts[0]

        page = await new_page_and_close_others(context)

        if clear:
            await clear_storage(page)
        else:
            print("跳过清空存储")

        # 重新导航到目标页面
        await page.goto(f"https://www.{DOUYIN_DOMAIN}/chat")
        print(f"页面标题: {await page.title()}")

        # 等待登录
        print("等待登录中（检测 passport_assist_user cookie）...")
        logged_in = await wait_for_login_cookie(context, max_wait=300, interval=2)
        if not logged_in:
            await browser.close()
            return

        # 跳转到个人主页，获取抖音号
        await page.goto(f"https://www.{DOUYIN_DOMAIN}/user/self", wait_until="domcontentloaded")

        # 重复提取抖音号，0.5Hz（每2秒一次），持续10秒
        douyin_id = None
        extract_interval = 2
        extract_duration = 10
        elapsed = 0

        while elapsed < extract_duration:
            douyin_id = await extract_douyin_id(page)

            if douyin_id:
                print(f"提取成功（耗时 {elapsed}s）")
                break

            print(
                f"未找到抖音号，{extract_interval}s 后重试..."
                f"（已等待 {elapsed + extract_interval}s/{extract_duration}s）"
            )
            await asyncio.sleep(extract_interval)
            elapsed += extract_interval

        print(f"抖音号: {douyin_id}")
        print(f"当前 URL: {page.url}")

        # 登录且抖音号获取成功后，自动保存 session
        if douyin_id:
            sessionid = await extract_sessionid(context)
            cookies = await dump_cookies(context)
            local_storage = await dump_local_storage(page)

            session_data = build_session_data(
                douyin_id=douyin_id,
                sessionid=sessionid,
                cookies=cookies,
                local_storage=local_storage,
            )

            filepath = get_session_filepath(douyin_id)
            save_session(session_data, filepath)
        else:
            print("抖音号未获取到，跳过保存 session")

        await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="抖音初始化登录")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="清空 douyin.com 相关存储数据",
    )
    args = parser.parse_args()
    asyncio.run(main(clear=args.clear))
