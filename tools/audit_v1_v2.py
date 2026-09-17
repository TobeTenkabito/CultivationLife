from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tempfile
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from cultivation_life.migration import (  # noqa: E402
    ShadowCharacterSpec,
    ShadowCommand,
    ShadowRunner,
    assess_default_matrix,
)


BLOCKER_GROUPS: dict[str, tuple[str, ...]] = {
    "shared_runtime": (
        "core.action_loop",
        "story.interactive_events",
        "verification.shadow_coverage",
        "interface.http_frontend",
    ),
    "dlc_depth": (
        "ghost.reincarnation",
        "ghost.soul_ecology",
        "ghost.attachment_possession",
        "monster.evolution_lineage",
        "celestial.court",
        "intrigue.personnel",
        "intrigue.guests_decisions",
    ),
}

GROUP_CAUSES = {
    "shared_runtime": "通用行动与交互内核已经建立，但领域专属效果、完整行动适配器、全操作影子覆盖及正式HTTP入口尚未完成。",
    "dlc_depth": "扩展加载和首层状态存在，DLC专属状态机及交互命令仍缺失。",
}


def _frozen_operations(root: Path) -> tuple[list[str], list[str]]:
    inventory = json.loads(
        (root / "docs" / "v2" / "v1_behavior_inventory.json").read_text(encoding="utf-8")
    )
    expected = sorted(map(str, inventory["public_operations"]))
    server = (root / "cultivation_life" / "server.py").read_text(encoding="utf-8")
    actual = sorted(set(re.findall(r'operation == "([^"]+)"', server)))
    return expected, actual


def _v2_boundary_violations(root: Path) -> list[str]:
    forbidden = {
        "cultivation_life.engine",
        "cultivation_life.models",
        "cultivation_life.storage",
    }
    violations: list[str] = []
    for path in (root / "cultivation_life" / "v2").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules = {alias.name for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                modules = {node.module or ""}
            else:
                continue
            if modules & forbidden:
                violations.append(f"{path.relative_to(root)}:{node.lineno}")
    return violations


def _blocker_audit(readiness: dict[str, Any]) -> list[dict[str, Any]]:
    group_for = {
        feature_id: group
        for group, feature_ids in BLOCKER_GROUPS.items()
        for feature_id in feature_ids
    }
    rows = []
    for blocker in readiness["blockers"]:
        feature_id = str(blocker["id"])
        group = group_for.get(feature_id, "unclassified")
        rows.append({
            **blocker,
            "cause_group": group,
            "root_cause": GROUP_CAUSES.get(group, "阻断项尚未分类；审计必须失败。"),
        })
    return rows


def _shadow_matrix(root: Path) -> list[dict[str, Any]]:
    scenarios = (
        ShadowCharacterSpec(name="影子道修", seed=1, path="dao", start_world="human"),
        ShadowCharacterSpec(name="影子道修", seed=123, path="dao", start_world="human"),
        ShadowCharacterSpec(
            name="影子魔修", seed=23, spirit_root="supreme_fire",
            path="demonic", start_world="demon",
        ),
        ShadowCharacterSpec(
            name="影子妖修", seed=37, spirit_root="supreme_wood",
            path="monster", start_world="monster_realm",
        ),
        ShadowCharacterSpec(
            name="影子鬼修", seed=51, spirit_root="supreme_water",
            path="ghost", start_world="hell",
        ),
    )
    commands = (ShadowCommand("rest", 1), ShadowCommand("cultivate", 1))
    rows: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="cultivation-full-audit-") as temporary:
        base = Path(temporary)
        scenario_index = 0
        # Each shared command starts from a fresh identical save.  A random V1
        # event after one action must not turn the following action into a
        # misleading execution failure; the event itself remains a reported
        # semantic divergence.
        for spec in scenarios:
            for command in commands:
                scenario_index += 1
                runner = ShadowRunner(
                    root,
                    v1_save_directory=base / f"v1-{scenario_index}",
                    v2_database_path=base / f"v2-{scenario_index}.sqlite3",
                )
                report = runner.run(spec, (command,))
                payload = report.to_dict()
                rows.append({
                    "name": spec.name,
                    "seed": spec.seed,
                    "path": spec.path,
                    "start_world": spec.start_world,
                    "command": f"{command.action}:{command.units}",
                    "status": payload["status"],
                    "summary": payload["summary"],
                    "difference_paths": sorted({row["path"] for row in payload["differences"]}),
                    "execution_errors": [
                        {"step": row["index"], "v1": row["v1_error"], "v2": row["v2_error"]}
                        for row in payload["steps"]
                        if row["v1_error"] or row["v2_error"]
                    ],
                })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="全面审计V1冻结面、V2门禁与共享影子行为")
    parser.add_argument("--root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()

    readiness = assess_default_matrix(root).to_dict()
    expected, actual = _frozen_operations(root)
    blockers = _blocker_audit(readiness)
    shadow = _shadow_matrix(root)
    classified_ids = {row["id"] for row in blockers if row["cause_group"] != "unclassified"}
    payload = {
        "v1_public_surface": {
            "expected_count": len(expected),
            "actual_count": len(actual),
            "missing_from_server": sorted(set(expected) - set(actual)),
            "unfrozen_in_server": sorted(set(actual) - set(expected)),
            "matched": expected == actual,
        },
        "v2_architecture_boundary": {
            "forbidden_imports": _v2_boundary_violations(root),
        },
        "readiness": readiness,
        "blocker_audit": {
            "count": len(blockers),
            "classified_count": len(classified_ids),
            "groups": {
                group: sum(row["cause_group"] == group for row in blockers)
                for group in (*BLOCKER_GROUPS, "unclassified")
            },
            "items": blockers,
        },
        "shadow_validation": {
            "shared_operations": ["advance:rest", "advance:cultivate"],
            "scenario_count": len(shadow),
            "scenarios": shadow,
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "v1_operations_matched": payload["v1_public_surface"]["matched"],
        "structural_errors": len(readiness["structural_errors"]),
        "blockers": len(blockers),
        "classified_blockers": len(classified_ids),
        "shadow_execution_errors": sum(
            bool(row["execution_errors"]) for row in shadow
        ),
        "shadow_diverged": sum(row["status"] == "diverged" for row in shadow),
    }, ensure_ascii=False))
    failed = (
        not payload["v1_public_surface"]["matched"]
        or bool(payload["v2_architecture_boundary"]["forbidden_imports"])
        or bool(readiness["structural_errors"])
        or len(classified_ids) != len(blockers)
        or any(row["execution_errors"] for row in shadow)
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
