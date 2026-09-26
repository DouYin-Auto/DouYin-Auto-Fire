"""续火花（XXH）命令行入口。

一次性续火花：
    uv run python -m src.run_xxh --douyin-id 66212456650
    uv run python -m src.run_xxh --douyin-id 66212456650 --target inc
    uv run python -m src.run_xxh --douyin-id 66212456650 --sticker 比心

持续模式（参数在 config.yaml 配置）：
    uv run python -m src.run_xxh --douyin-id 66212456650 --loop
"""

import argparse
import asyncio

from src.logger import init_logger, install_print_redirect
from src.runner import XXHRunner

DEFAULT_STICKER = "续火花"

# 日志分类列表（用于生成 CLI 参数）
LOG_CATEGORIES = [
    "online-events",
    "send-result",
    "schedule",
    "session-save",
    "browser-ops",
    "status-check",
    "chat-refresh",
]


def build_log_switches(args: argparse.Namespace) -> dict[str, bool]:
    """根据 CLI 参数构建日志开关字典。"""
    switches: dict[str, bool] = {}
    for cat in LOG_CATEGORIES:
        # 参数名格式：--no-log-xxx / --log-xxx
        no_log_attr = f"no_log_{cat.replace('-', '_')}"
        log_attr = f"log_{cat.replace('-', '_')}"
        # 如果设置了 --no-log-xxx，则关闭；如果设置了 --log-xxx，则开启
        if hasattr(args, no_log_attr) and getattr(args, no_log_attr):
            switches[cat.replace("-", "_")] = False
        elif hasattr(args, log_attr) and getattr(args, log_attr):
            switches[cat.replace("-", "_")] = True
    return switches


def add_log_arguments(parser: argparse.ArgumentParser) -> None:
    """为 parser 添加日志开关参数。"""
    log_group = parser.add_argument_group("日志开关（默认全部开启）")
    for cat in LOG_CATEGORIES:
        underscore_cat = cat.replace("-", "_")
        log_group.add_argument(
            f"--no-log-{cat}",
            dest=f"no_log_{underscore_cat}",
            action="store_true",
            default=False,
            help=f"关闭 {cat} 日志",
        )
        log_group.add_argument(
            f"--log-{cat}",
            dest=f"log_{underscore_cat}",
            action="store_true",
            default=False,
            help=f"开启 {cat} 日志（默认已开启）",
        )
    log_group.add_argument(
        "--no-log-console",
        dest="no_log_console",
        action="store_true",
        default=False,
        help="关闭控制台日志输出",
    )


async def main(
    douyin_id: str,
    message: str | None = None,
    sticker: str | None = None,
    target: str = "inc",
    loop_mode: bool = False,
    dry_run: bool = False,
    log_switches: dict[str, bool] | None = None,
    log_console: bool = True,
) -> None:
    """续火花执行入口。调度参数均在 config.yaml 中配置。"""
    # 初始化日志
    init_logger(enable_console=log_console, **(log_switches or {}))
    # 让所有 print() 同时写入日志
    install_print_redirect()

    actual_sticker = sticker if sticker is not None else DEFAULT_STICKER

    runner = XXHRunner(douyin_id=douyin_id, target=target)

    if dry_run:
        await _dry_run(runner, actual_sticker)
        return

    print(f"开始续火花，目标模式: {target}，表情: {actual_sticker}")
    if message:
        print(f"附加文字: {message}")

    if loop_mode:
        await runner.run_loop(message=message, sticker=actual_sticker)
    else:
        sent = await runner.run_once(
            message=message,
            sticker=actual_sticker,
        )
        if sent:
            print(f"\n续火花完成，共发送 {len(sent)} 人: {', '.join(sent)}")
        else:
            print("\n没有发送任何消息")


async def _dry_run(runner: XXHRunner, sticker: str) -> None:
    """预览要发送的用户列表。"""

    print("=== 续火花预览模式 ===")
    print(f"默认发送表情: {sticker}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="抖音续火花（XXH）- 自动维持聊天火花",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
调度参数在 config.yaml 的 schedule 节点配置。

日志开关（默认 See config.yaml categories）：
  --no-log-online-events    关闭上线/下线事件日志
  --no-log-send-result      关闭发送结果日志
  --no-log-schedule         关闭调度决策日志
  --no-log-session-save     关闭 Session 保存日志（默认关闭）
  --no-log-browser-ops      关闭浏览器操作日志（默认关闭）
  --no-log-status-check     关闭在线状态获取日志
  --no-log-chat-refresh     关闭聊天页面刷新日志
  --no-log-console          关闭控制台输出
        """.strip(),
    )
    parser.add_argument(
        "--douyin-id", type=str, required=True, help="抖音号"
    )
    parser.add_argument(
        "--message", "-m", type=str, default=None,
        help="附加的文字消息（可选）",
    )
    parser.add_argument(
        "--sticker", "-s", type=str, default=None,
        help=f"自定义原生表情名（默认: {DEFAULT_STICKER}）",
    )
    parser.add_argument(
        "--target",
        choices=["full", "inc"],
        default="inc",
        help="目标模式: full=所有用户, inc=今天未续用户 (默认: inc)",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="持续模式：智能调度续火花",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印要发送的用户列表，不实际发送",
    )

    # 添加日志开关
    add_log_arguments(parser)

    args = parser.parse_args()

    # 构建日志开关
    log_switches = build_log_switches(args)
    log_console = not args.no_log_console

    try:
        asyncio.run(
            main(
                douyin_id=args.douyin_id,
                message=args.message,
                sticker=args.sticker,
                target=args.target,
                loop_mode=args.loop,
                dry_run=args.dry_run,
                log_switches=log_switches,
                log_console=log_console,
            )
        )
    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as exc:
        print(f"\n执行失败: {exc}")
