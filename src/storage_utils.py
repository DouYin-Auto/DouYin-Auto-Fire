"""浏览器存储操作工具。

包含清空存储、导出 / 恢复 Cookie 和 LocalStorage 等共享函数。
所有 JS 脚本从 ``src/js/`` 目录下的独立 ``.js`` 文件加载。
"""

from src.constants import DOUYIN_DOMAIN
from src.dy_utils import _load_js


async def clear_storage(page) -> None:
    """清空 douyin.com 相关的 Cookie、LocalStorage、IndexedDB 和缓存。

    需要先导航到目标域名下，否则 localStorage / IndexedDB 无法操作对应源。

    Args:
        page: Playwright Page 对象。
    """
    # 1. 导航到抖音页面，确保可以操作该源的存储
    await page.goto(f"https://www.{DOUYIN_DOMAIN}/chat", wait_until="domcontentloaded")

    # 2. 清空 LocalStorage 和 SessionStorage
    await page.evaluate(_load_js("clear_local_session_storage.js"))

    # 3. 清空 IndexedDB（删除该域名下所有数据库）
    await page.evaluate(_load_js("clear_indexeddb.js"))

    # 4. 通过 CDP 清除 Service Worker 注册
    cdp = await page.context.new_cdp_session(page)
    await cdp.send(
        "Storage.clearDataForOrigin",
        {
            "origin": f"https://www.{DOUYIN_DOMAIN}",
            "storageTypes": "all",
        },
    )

    # 5. 清除 Cookie（通过 context 按 domain 过滤）
    cookies = await page.context.cookies()
    douyin_cookies = [c for c in cookies if DOUYIN_DOMAIN in c.get("domain", "")]
    if douyin_cookies:
        await page.context.clear_cookies()

    print(f"已清空 {DOUYIN_DOMAIN} 相关存储数据")


async def dump_cookies(context) -> list[dict]:
    """导出 douyin.com 相关的 Cookie。

    Args:
        context: Playwright BrowserContext。

    Returns:
        抖音相关的 Cookie 列表。
    """
    cookies = await context.cookies()
    douyin_cookies = [c for c in cookies if DOUYIN_DOMAIN in c.get("domain", "")]
    print(f"导出 Cookie: {len(douyin_cookies)} 条")
    return douyin_cookies


async def dump_local_storage(page) -> dict[str, str]:
    """导出当前页面的 LocalStorage。

    Args:
        page: Playwright Page 对象。

    Returns:
        LocalStorage 键值对字典。
    """
    data = await page.evaluate(_load_js("dump_local_storage.js"))
    print(f"导出 LocalStorage: {len(data)} 项")
    return data


async def restore_session(page, context, session_data: dict) -> None:
    """加载 session 数据（Cookie + LocalStorage）到浏览器。

    Args:
        page: Playwright Page 对象。
        context: Playwright BrowserContext。
        session_data: 包含 cookies 和 local_storage 的 session 字典。
    """
    # 1. 导航到抖音域名下，确保能操作该源的存储
    await page.goto(f"https://www.{DOUYIN_DOMAIN}/chat", wait_until="domcontentloaded")

    # 2. 恢复 Cookie
    cookies = session_data.get("cookies", [])
    if cookies:
        await context.add_cookies(cookies)
        print(f"已恢复 Cookie: {len(cookies)} 条")

    # 3. 恢复 LocalStorage
    local_storage = session_data.get("local_storage", {})
    if local_storage:
        await page.evaluate(_load_js("restore_local_storage.js"), local_storage)
        print(f"已恢复 LocalStorage: {len(local_storage)} 项")
