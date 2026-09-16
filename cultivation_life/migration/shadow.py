from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState
from cultivation_life.v2 import V2GameEngine


@dataclass(frozen=True, slots=True)
class ShadowCharacterSpec:
    name: str = "影子修士"
    seed: int = 1
    gender: str = "male"
    spirit_root: str = "supreme_wood"
    path: str = "dao"
    start_world: str = "human"


@dataclass(frozen=True, slots=True)
class ShadowCommand:
    """A command in the currently shared V1/V2 behavior surface."""

    action: str
    units: int = 1

    def __post_init__(self) -> None:
        if self.action not in {"cultivate", "rest"}:
            raise ValueError("影子运行当前只支持cultivate/rest")
        if isinstance(self.units, bool) or not 1 <= self.units <= 10:
            raise ValueError("影子运行行动单位必须为1至10")


@dataclass(frozen=True, slots=True)
class ShadowDifference:
    step: int
    command: str
    path: str
    v1: Any
    v2: Any
    severity: str
    category: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ShadowStep:
    index: int
    command: str
    v1: dict[str, Any] | None
    v2: dict[str, Any] | None
    v1_error: str | None = None
    v2_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ShadowReport:
    spec: ShadowCharacterSpec
    commands: tuple[ShadowCommand, ...]
    steps: list[ShadowStep] = field(default_factory=list)
    differences: list[ShadowDifference] = field(default_factory=list)

    @property
    def status(self) -> str:
        if any(step.v1_error or step.v2_error for step in self.steps):
            return "execution_error"
        return "matched" if not self.differences else "diverged"

    def to_dict(self) -> dict[str, Any]:
        severity_counts: dict[str, int] = {}
        category_counts: dict[str, int] = {}
        for difference in self.differences:
            severity_counts[difference.severity] = severity_counts.get(difference.severity, 0) + 1
            category_counts[difference.category] = category_counts.get(difference.category, 0) + 1
        return {
            "status": self.status,
            "spec": asdict(self.spec),
            "commands": [asdict(command) for command in self.commands],
            "summary": {
                "steps": len(self.steps),
                "differences": len(self.differences),
                "by_severity": severity_counts,
                "by_category": category_counts,
            },
            "steps": [step.to_dict() for step in self.steps],
            "differences": [difference.to_dict() for difference in self.differences],
        }


_COMPARISON_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("player.name", "error", "identity"),
    ("player.gender", "error", "identity"),
    ("player.race", "warning", "identity"),
    ("player.age", "error", "time"),
    ("player.alive", "error", "life"),
    ("player.death_reason", "error", "life"),
    ("player.lifespan", "warning", "life"),
    ("cultivation.path", "error", "cultivation"),
    ("cultivation.spirit_root", "error", "cultivation"),
    ("cultivation.realm_index", "error", "cultivation"),
    ("cultivation.layer", "error", "cultivation"),
    ("cultivation.opportunity", "warning", "balance"),
    ("world.world_id", "error", "world"),
    ("world.location_id", "warning", "world"),
    ("inventory", "warning", "economy"),
    ("relationships", "warning", "relations"),
    ("faction", "warning", "factions"),
    ("pending_event", "warning", "events"),
)


def _at(value: dict[str, Any], path: str) -> Any:
    current: Any = value
    for part in path.split("."):
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _number(value: Any) -> Any:
    if isinstance(value, float):
        return round(value, 6)
    return value


class ShadowRunner:
    """Execute the same seed and shared commands against V1 and V2.

    The runner compares a deliberately small semantic projection.  Internal
    entity IDs, event IDs, revisions, timestamps and RNG serialization are not
    compared because they are implementation details rather than game rules.
    """

    def __init__(
        self,
        project_root: Path,
        *,
        v1_save_directory: Path,
        v2_database_path: Path,
        content_directory: Path | None = None,
    ):
        self.project_root = Path(project_root)
        self.v1 = GameEngine(self.project_root, Path(v1_save_directory))
        self.v2 = V2GameEngine(
            Path(v2_database_path),
            content_directory=content_directory or self.project_root / "content",
        )

    def run(
        self,
        spec: ShadowCharacterSpec,
        commands: list[ShadowCommand] | tuple[ShadowCommand, ...],
    ) -> ShadowReport:
        sequence = tuple(commands)
        report = ShadowReport(spec=spec, commands=sequence)
        v1_created: dict[str, Any] | None = None
        v2_created: dict[str, Any] | None = None
        v1_create_error: str | None = None
        v2_create_error: str | None = None
        try:
            v1_created = self.v1.create_game(
                spec.name,
                spec.spirit_root,
                spec.path,
                seed=spec.seed,
                start_world=spec.start_world,
                gender=spec.gender,
            )
        except Exception as error:
            v1_create_error = f"{type(error).__name__}: {error}"
        try:
            v2_created = self.v2.create_game(
                spec.name,
                seed=spec.seed,
                gender=spec.gender,
                race="monster" if spec.path == "monster" else "human",
                spirit_root=spec.spirit_root,
                path=spec.path,
                start_world=spec.start_world,
            )
        except Exception as error:
            v2_create_error = f"{type(error).__name__}: {error}"
        if v1_create_error or v2_create_error:
            report.steps.append(ShadowStep(
                index=0,
                command="create",
                v1=(
                    self._v1_snapshot(self.v1.store.load(str(v1_created["id"])))
                    if v1_created else None
                ),
                v2=self._v2_snapshot(v2_created) if v2_created else None,
                v1_error=v1_create_error,
                v2_error=v2_create_error,
            ))
            report.differences.append(ShadowDifference(
                step=0,
                command="create",
                path="execution",
                v1=v1_create_error,
                v2=v2_create_error,
                severity="error",
                category="execution",
            ))
            return report
        assert v1_created is not None and v2_created is not None
        v1_id = str(v1_created["id"])
        v2_id = str(v2_created["id"])
        self._record(report, 0, "create", v1_id, v2_id)
        for index, command in enumerate(sequence, start=1):
            v1_error: str | None = None
            v2_error: str | None = None
            try:
                self.v1.advance(v1_id, command.action, command.units)
            except Exception as error:  # Integration harness must record either runtime's failure.
                v1_error = f"{type(error).__name__}: {error}"
            try:
                self.v2.perform_action(v2_id, command.action, command.units)
            except Exception as error:  # See above: the mismatch is report data, not a harness crash.
                v2_error = f"{type(error).__name__}: {error}"
            self._record(
                report,
                index,
                f"{command.action}:{command.units}",
                v1_id,
                v2_id,
                v1_error=v1_error,
                v2_error=v2_error,
            )
            if v1_error or v2_error:
                break
        return report

    def _record(
        self,
        report: ShadowReport,
        index: int,
        command: str,
        v1_id: str,
        v2_id: str,
        *,
        v1_error: str | None = None,
        v2_error: str | None = None,
    ) -> None:
        v1_snapshot = self._v1_snapshot(self.v1.store.load(v1_id))
        v2_snapshot = self._v2_snapshot(self.v2.get_game(v2_id))
        report.steps.append(ShadowStep(
            index=index,
            command=command,
            v1=v1_snapshot,
            v2=v2_snapshot,
            v1_error=v1_error,
            v2_error=v2_error,
        ))
        if v1_error != v2_error and (v1_error or v2_error):
            report.differences.append(ShadowDifference(
                step=index,
                command=command,
                path="execution",
                v1=v1_error,
                v2=v2_error,
                severity="error",
                category="execution",
            ))
        for path, severity, category in _COMPARISON_FIELDS:
            left = _number(_at(v1_snapshot, path))
            right = _number(_at(v2_snapshot, path))
            if left != right:
                report.differences.append(ShadowDifference(
                    step=index,
                    command=command,
                    path=path,
                    v1=copy.deepcopy(left),
                    v2=copy.deepcopy(right),
                    severity=severity,
                    category=category,
                ))

    @staticmethod
    def _v1_snapshot(game: GameState) -> dict[str, Any]:
        player = game.player
        inventory: dict[str, int] = {}
        for item in player.inventory:
            inventory[item.id] = inventory.get(item.id, 0) + int(item.quantity)
        relationships = {
            "dao_companion": 1 if player.dao_companion else 0,
            "friend": len(player.dao_friends),
            "master_disciple": (1 if player.master else 0) + len(player.disciples),
            "concubine": len(player.concubines),
        }
        return {
            "player": {
                "name": player.name,
                "gender": player.gender,
                "race": player.race,
                "age": player.age,
                "lifespan": player.lifespan,
                "alive": player.alive,
                "death_reason": player.death_reason,
            },
            "cultivation": {
                "path": player.path,
                "spirit_root": player.spirit_root,
                "realm_index": player.realm_index,
                "layer": player.layer,
                "opportunity": round(float(player.opportunity), 6),
            },
            "world": {"world_id": player.world, "location_id": player.location_id},
            "inventory": dict(sorted(inventory.items())),
            "relationships": relationships,
            "faction": (
                {
                    "external_id": player.faction_id,
                    "contribution": int(player.faction_contribution),
                }
                if player.faction_id else None
            ),
            "pending_event": bool(game.pending_event),
        }

    @staticmethod
    def _v2_snapshot(game: dict[str, Any]) -> dict[str, Any]:
        cultivation = dict(game["player"]["cultivation"])
        relationships: dict[str, int] = {
            "dao_companion": 0,
            "friend": 0,
            "master_disciple": 0,
            "concubine": 0,
        }
        for row in game["relationships"]:
            kind = str(row["kind"])
            relationships[kind] = relationships.get(kind, 0) + 1
        return {
            "player": {
                "name": game["player"]["name"],
                "gender": game["player"]["gender"],
                "race": game["player"]["race"],
                "age": game["player"]["age"],
                "lifespan": game["player"]["lifespan"],
                "alive": game["player"]["alive"],
                "death_reason": game["player"]["death_reason"],
            },
            "cultivation": {
                "path": cultivation["path"],
                "spirit_root": cultivation["spirit_root"],
                "realm_index": cultivation["realm_index"],
                "layer": cultivation["layer"],
                "opportunity": round(float(cultivation["opportunity"]), 6),
            },
            "world": {
                "world_id": game["world"]["world_id"],
                "location_id": game["world"]["location_id"],
            },
            "inventory": {
                str(row["id"]): int(row["quantity"])
                for row in game["inventory"]
            },
            "relationships": relationships,
            "faction": (
                {
                    "external_id": game["faction"]["external_id"],
                    "contribution": int(game["faction"]["contribution"]),
                }
                if game["faction"] else None
            ),
            "pending_event": False,
        }
