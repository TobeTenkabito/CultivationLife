from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cultivation_life.v2 import V2GameEngine


def main() -> int:
    parser = argparse.ArgumentParser(description="将一个V1 JSON存档单向导入V2 SQLite")
    parser.add_argument("source", type=Path, help="V1 JSON存档")
    parser.add_argument("--database", type=Path, default=Path("data/v2/saves.sqlite3"))
    parser.add_argument("--content", type=Path, default=Path("content"))
    parser.add_argument("--target-id", default=None)
    parser.add_argument("--report", type=Path, default=None, help="可选的JSON导入报告输出路径")
    args = parser.parse_args()

    engine = V2GameEngine(args.database, content_directory=args.content)
    result = engine.import_v1_save(args.source, target_game_id=args.target_id)
    payload = json.dumps(result.report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(payload, encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
