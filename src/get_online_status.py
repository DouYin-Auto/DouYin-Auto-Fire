"""抖音在线状态查询 - 通过 CDP 连接远程浏览器。

两种状态：明亮火花=今天已互发消息（已续），灰色火花=今天未互发消息（未续）。
"""

import argparse
import asyncio
import json
import os

from playwright.async_api import async_playwright

from src.cdp_utils import connect_cdp_browser
from src.logger import init_logger, install_print_redirect
from src.online_status import (
    OnlineStatus,
    get_attention_needed,
    get_friend_status,
    get_online_friends,
    get_online_status_from_list,
)
from src.send_message import _find_or_open_chat_page, _verify_douyin_id
from src.session_utils import get_session_filepath, load_session
from src.storage_utils import restore_session


def format_status_table(statuses: list[OnlineStatus]) -> str:
    """格式化输出在线状态和火花表格。"""
    if not statuses:
        return "未找到会话列表数据。"

    lines = [
        f"{'姓名':<12} {'在线':<10} {'火花文本':<14} {'状态':<8} {'正常':<6}",
        "-" * 56,
    ]
    for s in statuses:
        renewed = "✅已续" if s.renewed_today else "❌未续"
        normal = "是" if s.streak_text.isdigit() else "否"
        lines.append(
            f"{s.name:<12} {s.online_display:<10} "
            f"{s.streak_text or '-':<14} {renewed:<8} {normal:<6}"
        )
    lines.append("-" * 56)
    online_count = sum(1 for s in statuses if s.is_online)
    renewed_count = sum(1 for s in statuses if s.renewed_today)
    lines.append(
        f"共 {len(statuses)} 位好友 | {online_count} 位在线 | "
        f"已续 {renewed_count}/{len(statuses)}"
    )
    return "\n".join(lines)


def format_status_json(statuses: list[OnlineStatus]) -> str:
    """输出 JSON 格式。"""
    return json.dumps(
        [
            {
                "name": s.name,
                "is_online": s.is_online,
                "online_status_text": s.online_status_text,
                "last_msg_time": s.last_msg_time,
                "streak_text": s.streak_text,
                "renewed_today": s.renewed_today,
            }
            for s in statuses
        ],
        ensure_ascii=False,
        indent=2,
    )


async def main(
    douyin_id: str | None = None,
    friend_name: str | None = None,
    online_only: bool = False,
    attention_only: bool = False,
    output_json: bool = False,
) -> None:
    """获取抖音好友在线状态。"""
    if not douyin_id:
        print("错误：请通过 --douyin-id 指定抖音号")
        return

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

        print("\n检查浏览器当前登录态...")
        verified = await _verify_douyin_id(context, douyin_id)

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
                print("抖音号验证失败，终止查询")
                await browser.close()
                return

        print("\n查找私信页面...")
        chat_page = await _find_or_open_chat_page(context)
        await chat_page.wait_for_timeout(3_000)
        print(f"页面标题: {await chat_page.title()}")

        print("\n提取在线状态...")
        if friend_name:
            status = await get_friend_status(chat_page, friend_name)
            statuses = [status] if status else []
        elif online_only:
            statuses = await get_online_friends(chat_page)
        elif attention_only:
            statuses = await get_attention_needed(chat_page)
        else:
            statuses = await get_online_status_from_list(chat_page)

        print()
        if output_json:
            print(format_status_json(statuses))
        else:
            print(format_status_table(statuses))

        await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="查询抖音好友在线状态")
    parser.add_argument(
        "--douyin-id", type=str, required=True, help="抖音号"
    )
    parser.add_argument("--friend", type=str, default=None, help="仅查询特定好友")
    parser.add_argument(
        "--online-only", action="store_true", help="仅显示在线好友"
    )
    parser.add_argument(
        "--attention",
        action="store_true",
        help="仅显示需要关注的好友（今天未续）",
    )
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument(
        "--no-log-console", action="store_true", help="关闭控制台日志输出"
    )

    args = parser.parse_args()

    init_logger(enable_console=not args.no_log_console)
    install_print_redirect()

    try:
        asyncio.run(
            main(
                douyin_id=args.douyin_id,
                friend_name=args.friend,
                online_only=args.online_only,
                attention_only=args.attention,
                output_json=args.json,
            )
        )
    except Exception as exc:
        print(f"执行失败: {exc}")
