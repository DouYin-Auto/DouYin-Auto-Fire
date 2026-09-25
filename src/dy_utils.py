"""抖音业务工具。

包含抖音登录检测（轮询 passport_assist_user cookie）和抖音号提取，
JS 脚本从 ``src/js/`` 目录下的独立 ``.js`` 文件加载。
"""

import asyncio
import os

from playwright.async_api import BrowserContext, Page

from src.constants import DOUYIN_DOMAIN

_JS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "js")


def _load_js(filename: str) -> str:
    """从 src/js/ 目录加载 JS 脚本文件内容。

    Args:
        filename: JS 文件名，如 ``"extract_douyin_id.js"``。

    Returns:
        JS 脚本字符串。
    """
    filepath = os.path.join(_JS_DIR, filename)
    with open(filepath, encoding="utf-8") as f:
        return f.read()


async def wait_for_login_cookie(
    context: BrowserContext,
    max_wait: int = 300,
    interval: int = 2,
) -> bool:
    """轮询检测 passport_assist_user cookie 是否存在，判断是否已登录。

    Args:
        context: Playwright BrowserContext。
        max_wait: 最长等待秒数，默认 300（5分钟）。
        interval: 检测间隔秒数，默认 2。

    Returns:
        True 表示检测到登录 cookie，False 表示超时未检测到。
    """
    elapsed = 0
    while elapsed < max_wait:
        cookies = await context.cookies()
        has_login_cookie = any(
            c["name"] == "passport_assist_user" and DOUYIN_DOMAIN in c.get("domain", "")
            for c in cookies
        )
        if has_login_cookie:
            print(f"检测到 passport_assist_user cookie，登录成功！（耗时 {elapsed}s）")
            return True

        await asyncio.sleep(interval)
        elapsed += interval

    print("等待超时，未检测到登录。")
    return False


async def extract_douyin_id(page: Page) -> str | None:
    """从抖音个人主页中提取抖音号。

    Args:
        page: 已导航到 ``https://www.douyin.com/user/self`` 的 Page 对象。

    Returns:
        抖音号字符串，提取失败返回 None。
    """
    js = _load_js("extract_douyin_id.js")
    return await page.evaluate(js)
