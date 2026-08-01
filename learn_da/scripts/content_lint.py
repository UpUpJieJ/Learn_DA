"""内容 lint CLI（阶段 4 Task 1）。

对 ``content/`` 目录做发布前校验：字段级 schema、引用图、catalog 一致性。
有错误时非零退出并逐条输出 ``[file:field] message``，供发布前本地检查。

用法::

    python scripts/content_lint.py                    # 校验默认 content 目录
    python scripts/content_lint.py --content-dir PATH # 校验指定目录
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.content_loader import lint_content  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="校验课程内容（发布前 lint）")
    parser.add_argument(
        "--content-dir",
        type=Path,
        default=None,
        help="内容目录（默认 learn_da/content）",
    )
    args = parser.parse_args()

    errors = lint_content(args.content_dir)
    for error in errors:
        print(error)
    if errors:
        print(f"\n内容校验失败：{len(errors)} 个问题")
        return 1
    print("内容校验通过：课程、示例与 catalog 一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
