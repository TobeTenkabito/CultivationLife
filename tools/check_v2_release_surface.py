from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cultivation_life.v2.release_audit import assess_release_surface  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="检查V2冻结功能能否从HTTP与正式客户端实际到达"
    )
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = assess_release_surface(args.root)
    rendered = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered)
    return 0 if report.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
