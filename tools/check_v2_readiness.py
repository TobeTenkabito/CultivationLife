from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cultivation_life.migration import (  # noqa: E402
    CutoverBlockedError,
    assess_default_matrix,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="检查V2功能矩阵与正式切换条件")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--report", type=Path, default=None)
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="矩阵未全绿时返回非零状态，供正式切换和CI门禁使用",
    )
    args = parser.parse_args()
    report = assess_default_matrix(args.root)
    payload = report.to_dict()
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered)
    if args.require_ready:
        try:
            report.require_ready()
        except CutoverBlockedError as error:
            print(str(error), file=sys.stderr)
            return 2
    return 0 if not report.structural_errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
