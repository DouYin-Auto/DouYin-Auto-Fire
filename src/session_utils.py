"""Session 文件读写工具。

提供加载、保存 session JSON 文件的共享函数，以及从 context 中提取
sessionid 等辅助操作。
"""

import json
import os
from datetime import datetime

from src.constants import DOUYIN_DOMAIN, SESSIONS_DIR
from src.logger import get_logger


def load_session(filepath: str) -> dict:
    """加载单个 session JSON 文件。

    Args:
        filepath: session 文件路径。

    Returns:
        session 数据字典。
    """
    with open(filepath, encoding="utf-8") as f:
        return json.load(f)


def save_session(session_data: dict, filepath: str) -> None:
    """保存 session 数据到 JSON 文件。

    Args:
        session_data: session 数据字典。
        filepath: 目标文件路径。
    """
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(session_data, f, ensure_ascii=False, indent=2)
    get_logger().session_save(f"Session 已保存到: {filepath}")


def get_session_filepath(douyin_id: str) -> str:
    """根据抖音号生成 session 文件路径。

    Args:
        douyin_id: 抖音号。

    Returns:
        形如 ``sessions/dycn_<douyin_id>.json`` 的路径。
    """
    return os.path.join(SESSIONS_DIR, f"dycn_{douyin_id}.json")


def get_session_filepath_timestamp() -> str:
    """生成带时间戳的 session 文件路径。

    Returns:
        形如 ``sessions/dy_session_20250101_120000.json`` 的路径。
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(SESSIONS_DIR, f"dy_session_{timestamp}.json")


async def extract_sessionid(context) -> str:
    """从 BrowserContext 的 Cookie 中提取 sessionid。

    Args:
        context: Playwright BrowserContext。

    Returns:
        sessionid 值，未找到则返回空字符串。
    """
    cookies = await context.cookies()
    for c in cookies:
        if c["name"] == "sessionid" and DOUYIN_DOMAIN in c.get("domain", ""):
            return c["value"]
    return ""


def build_session_data(
    douyin_id: str | None = None,
    sessionid: str = "",
    cookies: list[dict] | None = None,
    local_storage: dict | None = None,
) -> dict:
    """构建 session 数据字典。

    Args:
        douyin_id: 抖音号，可选。
        sessionid: sessionid 值。
        cookies: Cookie 列表。
        local_storage: LocalStorage 键值对。

    Returns:
        完整的 session 数据字典。
    """
    data: dict = {
        "domain": DOUYIN_DOMAIN,
        "dumped_at": datetime.now().isoformat(),
        "cookies": cookies or [],
        "local_storage": local_storage or {},
    }
    if douyin_id is not None:
        data["douyin_id"] = douyin_id
    if sessionid:
        data["sessionid"] = sessionid
    return data
