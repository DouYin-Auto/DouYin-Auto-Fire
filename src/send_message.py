"""抖音自动发送消息 - 通过 CDP 连接远程浏览器，恢复 session 后向指定好友发送文字/表情。

流程:
    1. CDP 连接远程浏览器
    2. 先检查浏览器当前登录态（新标签页验证抖音号）
    3. 如果抖音号不匹配，恢复 session 后再次验证
    4. 切换到已打开的 chat 页面（或新开一个）
    5. 搜索好友（重复尝试 60 秒），失败后刷新 chat 重试 10 秒
    6. 发送文字 / 表情
    7. 更新保存 session

用法:
    # 向好友发送一条文字
    uv run python -m src.send_message <抖音号> <好友名> --text "你好"

    # 向好友发送一个原生表情
    uv run python -m src.send_message <抖音号> <好友名> --sticker 比心

    # 同时发送文字 + 表情
    uv run python -m src.send_message <抖音号> <好友名> --text "今天也要开心" --sticker 比心

    # 指定表情分类和无障碍名称
    uv run python -m src.send_message <抖音号> <好友名> \\
        --sticker 比心 --sticker-category 常用 --sticker-label 比心
"""

import argparse
import asyncio
import os

from playwright.async_api import BrowserContext, Page, async_playwright

from src.cdp_utils import connect_cdp_browser
from src.constants import DOUYIN_DOMAIN
from src.douyin_chat import DouyinChat, PageOperationError
from src.dy_utils import extract_douyin_id
from src.message_sender import Sticker, send_douyin_sticker, send_text
from src.session_utils import (
    build_session_data,
    extract_sessionid,
    get_session_filepath,
    load_session,
    save_session,
)
from src.storage_utils import dump_cookies, dump_local_storage, restore_session

# 抖音号提取的重试窗口（秒）
VERIFY_RETRY_SECONDS = 10
# 进入 chat 页面后第一轮搜索好友的重试窗口（秒）
# chat 是 SPA，搜索框等元素异步挂载，冷启动时可能较慢
SEARCH_RETRY_FIRST_ROUND_SECONDS = 60
# 刷新 chat 后第二轮搜索好友的重试窗口（秒）
SEARCH_RETRY_SECOND_ROUND_SECONDS = 10
# 每次重试间隔（秒）
RETRY_INTERVAL_SECONDS = 2


async def _verify_douyin_id(context: BrowserContext, expected_id: str) -> bool:
    """新开标签页导航到 user/self，验证页面提取的抖音号与期望值一致。

    在 RETRY_DURATION_SECONDS 窗口内重复尝试提取，每隔 RETRY_INTERVAL_SECONDS 秒一次。

    Args:
        context: BrowserContext。
        expected_id: 期望的抖音号。

    Returns:
        True 表示验证通过，False 表示超时未提取到或不一致。
    """
    page = await context.new_page()
    try:
        await page.goto(
            f"https://www.{DOUYIN_DOMAIN}/user/self", wait_until="domcontentloaded"
        )

        elapsed = 0
        verified_id = None
        while elapsed < VERIFY_RETRY_SECONDS:
            verified_id = await extract_douyin_id(page)
            if verified_id:
                print(f"提取成功（耗时 {elapsed}s）")
                break
            print(
                f"未找到抖音号，{RETRY_INTERVAL_SECONDS}s 后重试..."
                f"（已等待 {elapsed + RETRY_INTERVAL_SECONDS}s/{VERIFY_RETRY_SECONDS}s）"
            )
            await asyncio.sleep(RETRY_INTERVAL_SECONDS)
            elapsed += RETRY_INTERVAL_SECONDS

        print(f"期望抖音号: {expected_id}")
        print(f"页面提取抖音号: {verified_id}")

        if verified_id == expected_id:
            print("✅ 抖音号验证一致！")
            return True
        elif verified_id:
            print(f"⚠️ 抖音号不一致！期望: {expected_id}, 实际: {verified_id}")
            return False
        else:
            print("❌ 未能从页面提取到抖音号")
            return False
    finally:
        await page.close()


async def _find_or_open_chat_page(context: BrowserContext) -> Page:
    """查找已打开的抖音私信页面，找不到则新开一个。

    Args:
        context: BrowserContext。

    Returns:
        已导航到 /chat 的 Page 对象。
    """
    chat_url = f"https://www.{DOUYIN_DOMAIN}/chat"
    for page in context.pages:
        if chat_url in page.url:
            print(f"发现已打开的私信页面，直接切换: {page.url}")
            await page.bring_to_front()
            return page

    print("未发现已打开的私信页面，新开标签页...")
    page = await context.new_page()
    await page.goto(chat_url, wait_until="domcontentloaded")
    return page


async def _open_target_with_retry(
    chat: DouyinChat, friend_name: str
) -> None:
    """在 60 秒窗口内重复尝试搜索好友，失败后刷新 chat 页面再试 10 秒。

    chat 是 SPA，首次进入时搜索框等元素异步挂载，冷启动可能较慢。
    第一轮给 60 秒窗口让页面充分渲染；第一轮全部失败后刷新页面，
    第二轮再给 10 秒窗口重试。

    Args:
        chat: DouyinChat 实例。
        friend_name: 目标好友名称。

    Raises:
        PageOperationError: 两轮尝试后仍然失败。
    """
    # 第一轮：在 60 秒窗口内重复尝试搜索（SPA 冷启动需要时间）
    deadline = asyncio.get_running_loop().time() + SEARCH_RETRY_FIRST_ROUND_SECONDS
    attempt = 0
    last_error: Exception | None = None

    while asyncio.get_running_loop().time() < deadline:
        attempt += 1
        try:
            print(f"搜索好友 [{friend_name}]（第 {attempt} 次尝试）...")
            await chat.open_target(friend_name, retries=0)
            print("聊天窗口已打开")
            return
        except Exception as exc:
            last_error = exc
            print(f"第 {attempt} 次搜索失败: {exc}")
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining > RETRY_INTERVAL_SECONDS:
                await asyncio.sleep(RETRY_INTERVAL_SECONDS)

    # 第二轮：刷新 chat 页面后重试 10 秒
    print(f"\n{SEARCH_RETRY_FIRST_ROUND_SECONDS} 秒内搜索失败，刷新私信页面后重试...")
    page = chat.page
    await page.reload(wait_until="domcontentloaded", timeout=45_000)
    await page.wait_for_timeout(3_000)

    deadline = asyncio.get_running_loop().time() + SEARCH_RETRY_SECOND_ROUND_SECONDS
    attempt = 0
    while asyncio.get_running_loop().time() < deadline:
        attempt += 1
        try:
            print(f"刷新后搜索好友 [{friend_name}]（第 {attempt} 次尝试）...")
            await chat.open_target(friend_name, retries=0)
            print("聊天窗口已打开")
            return
        except Exception as exc:
            last_error = exc
            print(f"刷新后第 {attempt} 次搜索失败: {exc}")
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining > RETRY_INTERVAL_SECONDS:
                await asyncio.sleep(RETRY_INTERVAL_SECONDS)

    if last_error is not None:
        raise last_error
    raise PageOperationError(f"搜索好友 [{friend_name}] 两轮尝试后仍然失败")


async def _save_updated_session(
    context: BrowserContext, chat_page: Page, douyin_id: str
) -> None:
    """发送完成后更新保存 session（Cookie + LocalStorage）。

    Args:
        context: BrowserContext。
        chat_page: 私信页面（用于导出 LocalStorage）。
        douyin_id: 抖音号。
    """
    print("\n更新保存 session...")
    sessionid = await extract_sessionid(context)
    cookies = await dump_cookies(context)
    local_storage = await dump_local_storage(chat_page)

    session_data = build_session_data(
        douyin_id=douyin_id,
        sessionid=sessionid,
        cookies=cookies,
        local_storage=local_storage,
    )

    filepath = get_session_filepath(douyin_id)
    save_session(session_data, filepath)


async def send_message_to_friend(
    douyin_id: str,
    friend_name: str,
    text: str | None = None,
    sticker: Sticker | None = None,
) -> None:
    """通过 CDP 连接远程浏览器，恢复 session 后向好友发送消息。

    流程:
        1. 先检查浏览器当前登录态（新标签页验证抖音号）
        2. 如果抖音号不匹配，恢复 session 后再次验证
        3. 切换到已打开的 chat 页面（或新开）
        4. 搜索好友（60 秒重试 + 刷新重试 10 秒）
        5. 发送文字 / 表情
        6. 更新保存 session

    Args:
        douyin_id: 抖音号（用于加载 session 文件）。
        friend_name: 目标好友名称。
        text: 要发送的文字内容，可选。
        sticker: 要发送的表情配置，可选。
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

        # 1. 先检查浏览器当前登录态（不恢复 session，直接验证抖音号）
        print("\n检查浏览器当前登录态...")
        verified = await _verify_douyin_id(context, douyin_id)

        # 2. 如果抖音号不匹配，恢复 session 后再次验证
        if not verified:
            print("\n当前登录态不匹配，恢复 session...")
            if context.pages:
                session_page = context.pages[0]
                await session_page.bring_to_front()
            else:
                session_page = await context.new_page()
            await restore_session(session_page, context, session_data)

            print("\n恢复 session 后再次验证抖音号...")
            verified = await _verify_douyin_id(context, douyin_id)
            if not verified:
                print("抖音号验证失败，终止发送")
                await browser.close()
                return

        # 3. 查找或打开 chat 页面
        print("\n查找私信页面...")
        chat_page = await _find_or_open_chat_page(context)
        await chat_page.wait_for_timeout(3_000)
        print(f"页面标题: {await chat_page.title()}")

        # 4. 搜索好友（60 秒重试 + 刷新重试 10 秒）
        chat = DouyinChat(chat_page, timeout_ms=15_000)
        await _open_target_with_retry(chat, friend_name)

        # 5. 发送文字
        if text:
            print(f"\n发送文字: {text}")
            await send_text(chat, text)
            print("文字发送成功")
            await chat_page.wait_for_timeout(1_000)

        # 6. 发送表情
        if sticker:
            print(f"发送表情: {sticker.name}")
            await send_douyin_sticker(chat_page, sticker)
            print("表情发送成功")

        print("\n所有消息发送完成")

        # 7. 更新保存 session
        await _save_updated_session(context, chat_page, douyin_id)

        await browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="向抖音好友发送文字/表情消息")
    parser.add_argument("douyin_id", type=str, help="抖音号（用于加载 session）")
    parser.add_argument("friend_name", type=str, help="目标好友名称")
    parser.add_argument("--text", type=str, default=None, help="要发送的文字内容")
    parser.add_argument("--sticker", type=str, default=None, help="表情名称")
    parser.add_argument(
        "--sticker-category", type=str, default=None, help="表情分类（如: 常用）"
    )
    parser.add_argument(
        "--sticker-label",
        type=str,
        default=None,
        help="表情无障碍名称（aria-label），默认与表情名称相同",
    )
    parser.add_argument(
        "--sticker-fallback-index",
        type=int,
        default=None,
        help="表情 fallback 索引（按面板中的位置选择）",
    )

    args = parser.parse_args()

    if not args.text and not args.sticker:
        parser.error("至少指定 --text 或 --sticker 之一")

    sticker = None
    if args.sticker:
        sticker = Sticker(
            name=args.sticker,
            category=args.sticker_category,
            accessible_name=args.sticker_label,
            fallback_index=args.sticker_fallback_index,
        )

    try:
        asyncio.run(
            send_message_to_friend(
                douyin_id=args.douyin_id,
                friend_name=args.friend_name,
                text=args.text,
                sticker=sticker,
            )
        )
    except PageOperationError as exc:
        print(f"页面操作失败: {exc}")
    except Exception as exc:
        print(f"执行失败: {exc}")


if __name__ == "__main__":
    main()
