"""Session 分析器 - 对比多个 session JSON 文件之间的 Cookie 差异。

用法:
    uv run python -m src.dy_analyze_session \\
        sessions/dy_session_xxx.json sessions/dy_session_yyy.json
    uv run python -m src.dy_analyze_session sessions/  # 对比目录下所有 session 文件
"""

import glob
import os
import sys


def extract_cookies_map(session: dict) -> dict[str, dict]:
    """将 session 中的 cookies 列表转为 {name: cookie_dict} 映射。"""
    cookies = session.get("cookies", [])
    return {c["name"]: c for c in cookies}


def diff_cookies(sessions: list[tuple[str, dict]]) -> None:
    """对比多个 session 之间的 cookie 差异。

    Args:
        sessions: [(文件名, session数据), ...]
    """
    names = [(label, extract_cookies_map(data)) for label, data in sessions]
    all_cookie_names = set()
    for _, cookies_map in names:
        all_cookie_names.update(cookies_map.keys())

    # 按出现情况分类
    added = []  # 后续有但前面没有
    removed = []  # 前面有但后续没有
    changed = []  # 值发生变化
    same = []  # 完全相同

    if len(names) == 2:
        label_a, map_a = names[0]
        label_b, map_b = names[1]
        all_keys = sorted(all_cookie_names)

        for key in all_keys:
            in_a = key in map_a
            in_b = key in map_b
            if in_a and not in_b:
                removed.append(key)
            elif not in_a and in_b:
                added.append(key)
            elif in_a and in_b:
                val_a = map_a[key]
                val_b = map_b[key]
                if val_a != val_b:
                    changed.append(key)
                else:
                    same.append(key)

        print(f"对比: {label_a}  vs  {label_b}")
        print(f"{'=' * 80}")
        print(f"总 Cookie 数: A={len(map_a)}, B={len(map_b)}")
        print()

        if added:
            print(f"[新增] B 有 A 没有 ({len(added)}):")
            for k in added:
                print(f"  + {k}: {map_b[k].get('value', '')[:80]}")
            print()

        if removed:
            print(f"[删除] A 有 B 没有 ({len(removed)}):")
            for k in removed:
                print(f"  - {k}: {map_a[k].get('value', '')[:80]}")
            print()

        if changed:
            print(f"[变化] 值不同 ({len(changed)}):")
            for k in changed:
                va = map_a[k].get("value", "")
                vb = map_b[k].get("value", "")
                print(f"  * {k}:")
                print(f"      A: {va[:80]}")
                print(f"      B: {vb[:80]}")
            print()

        if same:
            print(f"[相同] 值一致 ({len(same)}):")
            for k in same:
                print(f"  = {k}")
            print()

    elif len(names) > 2:
        # 多文件对比：列出每个 cookie 在各 session 中的存在性
        print(f"对比 {len(names)} 个 session 文件:")
        print(f"{'=' * 80}")

        # 表头
        header = f"{'Cookie Name':<40} " + " ".join(f"{label[-12:]:<14}" for label, _ in names)
        print(header)
        print("-" * len(header))

        for key in sorted(all_cookie_names):
            row = f"{key:<40} "
            for _, cookies_map in names:
                if key in cookies_map:
                    val = cookies_map[key].get("value", "")[:12]
                    row += f"{val:<14} "
                else:
                    row += f"{'(无)':<14} "
            print(row)

    else:
        print("至少需要 2 个 session 文件进行对比")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        print("用法: uv run python -m src.dy_analyze_session <session文件...> 或 <session目录>")
        print("示例: uv run python -m src.dy_analyze_session sessions/")
        sys.exit(1)

    # 如果是目录，加载目录下所有 JSON 文件
    if len(args) == 1 and os.path.isdir(args[0]):
        files = sorted(glob.glob(os.path.join(args[0], "*.json")))
    else:
        files = args

    if len(files) < 2:
        print("至少需要 2 个 session 文件进行对比")
        sys.exit(1)

    # 延迟导入，避免在命令行入口处就加载 playwright 依赖
    from src.session_utils import load_session

    sessions = []
    for f in files:
        if not os.path.exists(f):
            print(f"文件不存在: {f}")
            sys.exit(1)
        label = os.path.basename(f)
        data = load_session(f)
        sessions.append((label, data))
        print(f"已加载: {label} (cookies: {len(data.get('cookies', []))})")

    print()
    diff_cookies(sessions)


if __name__ == "__main__":
    main()
