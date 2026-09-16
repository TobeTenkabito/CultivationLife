from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cultivation_life.migration import ShadowCharacterSpec, ShadowCommand, ShadowRunner


def _command(value: str) -> ShadowCommand:
    action, separator, raw_units = value.partition(":")
    if not separator:
        raw_units = "1"
    try:
        return ShadowCommand(action=action, units=int(raw_units))
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def main() -> int:
    parser = argparse.ArgumentParser(description="以相同种子和命令序列影子运行V1/V2")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--name", default="影子修士")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--gender", choices=("male", "female"), default="male")
    parser.add_argument("--root-id", dest="spirit_root", default="supreme_wood")
    parser.add_argument("--path", default="dao")
    parser.add_argument("--world", default="human")
    parser.add_argument(
        "--command", action="append", type=_command, default=[],
        help="共享命令，格式cultivate:单位或rest:单位；可重复",
    )
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="cultivation-shadow-") as temporary:
        temp = Path(temporary)
        runner = ShadowRunner(
            args.root,
            v1_save_directory=temp / "v1",
            v2_database_path=temp / "v2.sqlite3",
        )
        report = runner.run(
            ShadowCharacterSpec(
                name=args.name,
                seed=args.seed,
                gender=args.gender,
                spirit_root=args.spirit_root,
                path=args.path,
                start_world=args.world,
            ),
            args.command,
        )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report.to_dict()["summary"], ensure_ascii=False))
    return 0 if report.status != "execution_error" else 2


if __name__ == "__main__":
    raise SystemExit(main())
