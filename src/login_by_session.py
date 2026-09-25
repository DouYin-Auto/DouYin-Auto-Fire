"""通过 Session 恢复登录 - 清空浏览器后加载指定抖音号的 session，验证并跳转聊天页面。

用法:
    uv run python -m src.login_by_session 抖音号
"""

import argparse
import asyncio
import os

from playwright.async_api import async_playwright

from src.cdp_utils import connect_cdp_browser, new_page_and_close_others
from src.constants import DOUYIN_DOMAIN
from src.dy_utils import extract_douyin_id
from src.session_utils import get_session_filepath, load_session
from src.storage_utils import clear_storage, restore_session


async def main(douyin_id: str) -> None:
    """通过 session 恢复登录，验证抖音号后跳转聊天页面。

    Args:
        douyin_id: 抖音号。
    """
    # 加载 session 文件
    session_file = get_session_filepath(douyin_id)
    if not os.path.exists(session_file):
        print(f"Session 文件不存在: {session_file}")
        return

    session_data = load_session(session_file)
    print(f"已加载 session: {session_file}")
    print(f"  抖音号: {session_data.get('douyin_id')}")
    print(f"  保存时间: {session_data.get('dumped_at')}")

    async with async_playwright() as pw:
        browser = await connect_cdp_browser(pw)
        context = browser.contexts[0]

        page = await new_page_and_close_others(context)

        # 1. 清空浏览器存储
        await clear_storage(page)

        # 2. 加载 session
        await restore_session(page, context, session_data)

        # 3. 跳转 user/self 确认抖音号
        print("\n跳转到个人主页验证抖音号...")
        await page.goto(f"https://www.{DOUYIN_DOMAIN}/user/self", wait_until="domcontentloaded")

        # 重复提取抖音号，0.5Hz（每2秒一次），持续10秒
        verified_id = None
        extract_interval = 2
        extract_duration = 10
        elapsed = 0

        while elapsed < extract_duration:
            verified_id = await extract_douyin_id(page)

            if verified_id:
                print(f"提取成功（耗时 {elapsed}s）")
                break

            print(
                f"未找到抖音号，{extract_interval}s 后重试..."
                f"（已等待 {elapsed + extract_interval}s/{extract_duration}s）"
            )
            await asyncio.sleep(extract_interval)
            elapsed += extract_interval

        print(f"Session 中抖音号: {douyin_id}")
        print(f"页面提取抖音号: {verified_id}")

        if verified_id == douyin_id:
            print("✅ 抖音号验证一致！")
        elif verified_id:
            print(f"⚠️ 抖音号不一致！期望: {douyin_id}, 实际: {verified_id}")
        else:
            print("❌ 未能从页面提取到抖音号")

        # 4. 跳转聊天页面
        print("\n跳转到聊天页面...")
        await page.goto(f"https://www.{DOUYIN_DOMAIN}/chat", wait_until="domcontentloaded")
        print(f"页面标题: {await page.title()}")
        print(f"当前 URL: {page.url}")

        await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="通过 Session 恢复抖音登录")
    parser.add_argument(
        "douyin_id",
        type=str,
        help="抖音号",
    )
    args = parser.parse_args()
    asyncio.run(main(args.douyin_id))
