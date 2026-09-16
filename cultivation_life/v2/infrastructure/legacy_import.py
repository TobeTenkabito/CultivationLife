from __future__ import annotations

import ast
import copy
import hashlib
import json
import math
import os
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..domain.character import ACTIVITY, IDENTITY, LIFE, BootstrapGame, LIFESPAN_DUE
from ..domain.combat import CONDITION, combat_snapshot
from ..domain.cultivation import CULTIVATION, PRACTICE, QI_SOURCES
from ..domain.definitions import GameDefinitions
from ..domain.economy import INVENTORY, MARKET
from ..domain.extensions import GHOST_SOUL, MONSTER_BLOODLINE
from ..domain.factions import FACTION_GOVERNANCE, FACTION_PROFILE, MEMBERSHIP
from ..domain.world import LOCATION
from ..kernel.bus import CommandBus, SimulationContext
from ..kernel.model import EventEnvelope, EventScope, WorldState


SUPPORTED_V1_SAVE_VERSIONS = frozenset({2, 3, 4, 5})
MAX_LEGACY_SAVE_BYTES = 64 * 1024 * 1024
LEGACY_AUDIT = "migration.legacy_v1"


@dataclass(frozen=True, slots=True)
class LegacyImportIssue:
    code: str
    path: str
    message: str
    severity: str = "warning"

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "path": self.path,
            "message": self.message,
            "severity": self.severity,
        }


@dataclass(slots=True)
class LegacyImportReport:
    source_name: str
    source_sha256: str
    source_version: int
    source_game_id: str
    target_game_id: str
    backup_path: str | None = None
    backup_sha256: str | None = None
    backup_created: bool = False
    status: str = "imported"
    imported_counts: dict[str, int] = field(default_factory=dict)
    issues: list[LegacyImportIssue] = field(default_factory=list)

    def warn(self, code: str, path: str, message: str) -> None:
        self.issues.append(LegacyImportIssue(code=code, path=path, message=message))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "source_sha256": self.source_sha256,
            "source_version": self.source_version,
            "source_game_id": self.source_game_id,
            "target_game_id": self.target_game_id,
            "backup_path": self.backup_path,
            "backup_sha256": self.backup_sha256,
            "backup_created": self.backup_created,
            "status": self.status,
            "imported_counts": dict(self.imported_counts),
            "issues": [issue.to_dict() for issue in self.issues],
        }


@dataclass(frozen=True, slots=True)
class LegacyImportResult:
    state: WorldState
    events: tuple[EventEnvelope, ...]
    report: LegacyImportReport


@dataclass(frozen=True, slots=True)
class LegacyBackup:
    path: Path
    sha256: str
    created: bool


class LegacyImportError(ValueError):
    """The source is not a supported, structurally valid V1 save."""


class LegacyImportBlockedError(LegacyImportError):
    """The source contains live state which V2 cannot preserve safely."""

    def __init__(self, issues: list[LegacyImportIssue]):
        self.issues = tuple(issues)
        detail = "；".join(f"{issue.path}: {issue.message}" for issue in issues)
        super().__init__(f"旧存档包含当前无法安全迁移的进行中状态：{detail}")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise LegacyImportError(f"旧存档存在重复JSON键：{key}")
        result[key] = value
    return result


def _invalid_json_constant(value: str) -> None:
    raise LegacyImportError(f"旧存档包含非法数值：{value}")


def load_legacy_save(path: Path) -> tuple[dict[str, Any], str]:
    """Read a V1 JSON save without importing or instantiating the V1 runtime."""
    source = Path(path)
    if not source.is_file():
        raise LegacyImportError("旧存档文件不存在")
    size = source.stat().st_size
    if size <= 0 or size > MAX_LEGACY_SAVE_BYTES:
        raise LegacyImportError("旧存档为空或超过64 MiB安全上限")
    payload = source.read_bytes()
    try:
        text = payload.decode("utf-8")
        document = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_invalid_json_constant,
        )
    except UnicodeDecodeError as error:
        raise LegacyImportError("旧存档不是UTF-8文本") from error
    except json.JSONDecodeError as error:
        raise LegacyImportError(f"旧存档JSON损坏：{error.msg}") from error
    if not isinstance(document, dict):
        raise LegacyImportError("旧存档根节点必须是对象")
    return document, hashlib.sha256(payload).hexdigest()


def backup_legacy_save(
    source_path: Path,
    backup_directory: Path,
    *,
    expected_sha256: str,
) -> LegacyBackup:
    """Create or verify an immutable content-addressed V1 backup.

    The source is read again immediately before backup so a concurrent edit
    cannot make the validated document differ from the preserved bytes.
    """
    source = Path(source_path)
    if not source.is_file() or not 0 < source.stat().st_size <= MAX_LEGACY_SAVE_BYTES:
        raise LegacyImportError("旧存档在备份前消失、变空或超过64 MiB安全上限")
    payload = source.read_bytes()
    actual_sha256 = hashlib.sha256(payload).hexdigest()
    if actual_sha256 != expected_sha256:
        raise LegacyImportError("旧存档在校验后发生变化，已停止导入")
    destination_directory = Path(backup_directory)
    destination_directory.mkdir(parents=True, exist_ok=True)
    safe_stem = (
        re.sub(r"[^0-9A-Za-z._-]+", "_", source.stem).strip("._")[:80]
        or "legacy-save"
    )
    backup_path = destination_directory / f"{safe_stem}-{actual_sha256[:16]}.v1.json"
    if source.resolve() == backup_path.resolve():
        raise LegacyImportError("备份目标不能与旧存档源文件相同")
    if backup_path.exists():
        existing_sha256 = hashlib.sha256(backup_path.read_bytes()).hexdigest()
        if existing_sha256 != actual_sha256:
            raise LegacyImportError("同名旧存档备份内容不一致，拒绝覆盖")
        return LegacyBackup(path=backup_path.resolve(), sha256=actual_sha256, created=False)
    created = False
    try:
        with backup_path.open("xb") as stream:
            created = True
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        if created:
            backup_path.unlink(missing_ok=True)
        raise
    return LegacyBackup(path=backup_path.resolve(), sha256=actual_sha256, created=True)


def _meaningful(value: Any) -> bool:
    if value is None or value is False:
        return False
    if isinstance(value, (int, float)) and value == 0:
        return False
    if isinstance(value, (str, list, tuple, dict, set)) and not value:
        return False
    return True


def _safe_int(value: Any, path: str) -> int:
    if isinstance(value, bool):
        raise LegacyImportError(f"{path} 必须是整数")
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise LegacyImportError(f"{path} 必须是整数") from error


def _safe_float(value: Any, path: str) -> float:
    if isinstance(value, bool):
        raise LegacyImportError(f"{path} 必须是有限数值")
    try:
        result = float(value)
    except (TypeError, ValueError) as error:
        raise LegacyImportError(f"{path} 必须是有限数值") from error
    if not math.isfinite(result):
        raise LegacyImportError(f"{path} 必须是有限数值")
    return result


class LegacyV1Importer:
    """One-way V1 JSON to V2 state translator.

    This adapter intentionally consumes plain dictionaries.  Importing a save
    therefore cannot execute V1 constructors, migrations, extensions or event
    code.  Unsupported live workflows are blocked before a V2 row is written.
    """

    _MAPPED_TOP_LEVEL = {
        "id", "seed", "player", "created_at", "updated_at", "rng_state",
        "version",
    }
    _MAPPED_PLAYER_FIELDS = {
        "name", "spirit_root", "gender", "age", "realm_index", "layer",
        "lifespan", "opportunity", "qi_experience", "heart_demon", "hp", "mp",
        "path", "technique", "known_techniques", "additional_roots", "inventory",
        "alive", "death_reason", "breakthrough_pity", "awaiting_major_breakthrough",
        "awaiting_minor_breakthrough", "world", "location_id", "race", "faction_id",
        "faction_join_age", "faction_contribution", "master", "disciples",
        "dao_friends", "concubines", "dao_companion", "monster_species_id",
        "monster_evolution_id", "monster_evolution_history", "monster_adaptations",
        "monster_adaptation_progress", "monster_bloodline_imprints",
        "monster_acquired_bloodline_traits", "ghost_intrinsic_hp_current",
        "ghost_intrinsic_mp_current", "ghost_soul_erosion_rate_pp",
        "ghost_soul_erosion_time_progress", "ghost_wangsheng_energy",
        "ghost_reincarnation_imprints", "ghost_intrinsic_highwater_realm",
        "ghost_intrinsic_highwater_layer",
    }

    def __init__(self, definitions: GameDefinitions, commands: CommandBus):
        self.definitions = definitions
        self.commands = commands

    def import_document(
        self,
        document: dict[str, Any],
        *,
        source_name: str,
        source_sha256: str,
        target_game_id: str | None = None,
    ) -> LegacyImportResult:
        source = copy.deepcopy(document)
        version = _safe_int(source.get("version", 0), "version")
        if source.get("format") == "cultivation-life-v2":
            raise LegacyImportError("该文件已经是V2存档，不能再次导入")
        if version not in SUPPORTED_V1_SAVE_VERSIONS:
            raise LegacyImportError(f"不支持的V1存档版本：{version}")
        source_id = str(source.get("id", "")).strip()
        if not source_id:
            raise LegacyImportError("旧存档缺少id")
        target_id = str(target_game_id or source_id).strip()
        if not target_id or len(target_id) > 128:
            raise LegacyImportError("目标V2存档ID非法")
        player = source.get("player")
        if not isinstance(player, dict):
            raise LegacyImportError("旧存档缺少player对象")
        blockers = self._blocking_states(source, player)
        if blockers:
            raise LegacyImportBlockedError(blockers)

        seed = _safe_int(source.get("seed"), "seed")
        name = str(player.get("name", "")).strip()
        if not name:
            raise LegacyImportError("player.name不能为空")
        gender = str(player.get("gender", "male"))
        race = str(player.get("race", "human"))
        path = str(player.get("path", "dao"))
        root = str(player.get("spirit_root", ""))
        age = _safe_int(player.get("age", 16), "player.age")
        if gender not in {"male", "female"}:
            raise LegacyImportError(f"旧存档性别无法映射：{gender}")
        if not 0 <= age <= 1_000_000:
            raise LegacyImportError(f"旧存档年龄非法：{age}")
        realm_index = _safe_int(player.get("realm_index", 0), "player.realm_index")
        layer = _safe_int(player.get("layer", 1), "player.layer")
        if path not in self.definitions.paths:
            raise LegacyImportError(f"旧存档修行道路无法映射：{path}")
        if root not in self.definitions.roots:
            raise LegacyImportError(f"旧存档灵根无法映射：{root}")
        if not 0 <= realm_index < len(self.definitions.realms):
            raise LegacyImportError(f"旧存档境界序号无法映射：{realm_index}")
        realm = self.definitions.realms[realm_index]
        if not 1 <= layer <= realm.layers:
            raise LegacyImportError(f"旧存档境界层数非法：{realm_index}/{layer}")
        world_id = str(player.get("world", "human"))
        world = self.definitions.worlds.get(world_id)
        if world is None or not world.enabled:
            raise LegacyImportError(f"旧存档当前世界尚不能由V2表示：{world_id}")

        start_age = self._infer_start_age(source, age)
        elapsed_years = max(0, age - start_age)
        created_at = str(source.get("created_at", "")).strip()
        updated_at = str(source.get("updated_at", created_at)).strip()
        if not created_at:
            raise LegacyImportError("旧存档缺少created_at")
        report = LegacyImportReport(
            source_name=source_name,
            source_sha256=source_sha256,
            source_version=version,
            source_game_id=source_id,
            target_game_id=target_id,
        )

        bootstrap_worlds = self.definitions.start_worlds.get(path, ("human",))
        bootstrap_world = bootstrap_worlds[0]
        state = WorldState.new(seed=seed, created_at=created_at, game_id=target_id)
        events = self.commands.execute(state, BootstrapGame(
            name=name[:40],
            starting_age=start_age,
            gender=gender,
            race=race,
            spirit_root=root,
            path=path,
            start_world=bootstrap_world,
        ))
        actor_id = str(state.controlled_entity_id)
        state.clock = state.clock.at(elapsed_years)
        state.updated_at = updated_at or created_at
        self._import_player_core(state, actor_id, player, realm.id, report)
        self._import_rng(state, source, report)
        self._import_inventory(state, actor_id, player, report)
        self._import_relations(state, actor_id, player, report)
        self._import_faction(state, actor_id, source, player, report)
        self._import_extensions(state, actor_id, player, report)
        self._import_combat_condition(state, actor_id, player, report)
        self._audit_deferred_fields(source, player, report)

        report.imported_counts.setdefault("characters", 1)
        report.imported_counts["history_records_observed"] = len(source.get("history", []))
        report.status = "imported_with_warnings" if report.issues else "imported"
        state.module_versions["legacy_import"] = 1
        state.entities.put(actor_id, LEGACY_AUDIT, report.to_dict())
        context = SimulationContext(state=state, event_bus=self.commands.event_bus)
        context.emit(
            "migration.v1.imported",
            source="legacy_import",
            scope=EventScope.entity(actor_id),
            payload={
                "source_version": version,
                "source_game_id": source_id,
                "source_sha256": source_sha256,
                "warning_count": len(report.issues),
                "imported_counts": dict(report.imported_counts),
            },
        )
        context.persist_rng()
        return LegacyImportResult(
            state=state,
            events=tuple([*events, *context.emitted_events]),
            report=report,
        )

    @staticmethod
    def _blocking_states(source: dict[str, Any], player: dict[str, Any]) -> list[LegacyImportIssue]:
        blockers: list[LegacyImportIssue] = []
        candidates = (
            ("pending_event", source.get("pending_event"), "请先在V1结算当前事件"),
            ("active_trial", source.get("active_trial"), "请先在V1完成或退出突破试炼"),
            ("player.imprisonment", player.get("imprisonment"), "请先在V1结束监禁状态"),
            ("player.sealed_cultivation", player.get("sealed_cultivation"), "请先在V1解除修为封印"),
            ("player.ghost_captor", player.get("ghost_captor"), "请先在V1解决拘魂控制状态"),
        )
        for path, value, message in candidates:
            if _meaningful(value):
                blockers.append(LegacyImportIssue("live_workflow", path, message, "error"))
        auction = source.get("auction_state")
        if isinstance(auction, dict):
            frozen_bid = any(
                isinstance(lot, dict) and lot.get("current_bidder") == "player"
                for lot in auction.get("lots", [])
            )
            frozen_consignment = bool(auction.get("consignments"))
            if frozen_bid or frozen_consignment:
                blockers.append(LegacyImportIssue(
                    "frozen_auction_assets",
                    "auction_state",
                    "拍卖中仍有冻结竞价或寄拍资产；请先在V1取消或结算拍卖",
                    "error",
                ))
        return blockers

    @staticmethod
    def _infer_start_age(source: dict[str, Any], current_age: int) -> int:
        history = source.get("history", [])
        if isinstance(history, list):
            ages = [
                int(row["age"])
                for row in history
                if isinstance(row, dict) and isinstance(row.get("age"), int)
            ]
            if ages:
                return max(0, min(current_age, min(ages)))
        return min(current_age, 16)

    def _import_player_core(
        self,
        state: WorldState,
        actor_id: str,
        player: dict[str, Any],
        realm_id: str,
        report: LegacyImportReport,
    ) -> None:
        identity = state.entities.require(actor_id, IDENTITY)
        identity.update(
            name=str(player["name"]).strip()[:40],
            gender=str(player.get("gender", "male")),
            race=str(player.get("race", "human")),
        )
        state.entities.put(actor_id, IDENTITY, identity)
        age = int(player.get("age", 16))
        lifespan_value = player.get("lifespan")
        lifespan = None if lifespan_value is None else _safe_int(lifespan_value, "player.lifespan")
        if lifespan is not None and lifespan < 0:
            raise LegacyImportError("player.lifespan 不能为负数")
        alive = bool(player.get("alive", True))
        if alive and lifespan is not None and lifespan <= age:
            raise LegacyImportError("旧存档中存活角色已达到寿限，无法保持一致")
        life = {
            "birth_year": state.clock.year - age,
            "lifespan": lifespan,
            "alive": alive,
            "death_reason": player.get("death_reason"),
        }
        state.entities.put(actor_id, LIFE, life)
        state.scheduler.cancel(
            lambda event: event.event_type == LIFESPAN_DUE
            and event.payload.get("entity_id") == actor_id
        )
        if alive and lifespan is not None:
            state.scheduler.schedule(
                due_year=int(life["birth_year"]) + lifespan,
                event_type=LIFESPAN_DUE,
                source="character",
                scope=EventScope.entity(actor_id),
                payload={"entity_id": actor_id},
            )
        state.entities.put(actor_id, ACTIVITY, {"rest_years": 0, "actions_completed": 0})

        valid_roots = [
            str(root) for root in player.get("additional_roots", [])
            if str(root) in self.definitions.roots
        ]
        if len(valid_roots) != len(player.get("additional_roots", [])):
            report.warn("unknown_root", "player.additional_roots", "无法识别的后天灵根未导入")
        bottleneck = (
            "major" if player.get("awaiting_major_breakthrough")
            else "minor" if player.get("awaiting_minor_breakthrough") else None
        )
        opportunity = _safe_float(player.get("opportunity", 0.0), "player.opportunity")
        if opportunity < 0:
            raise LegacyImportError("player.opportunity 不能为负数")
        cultivation = {
            "path": str(player.get("path", "dao")),
            "spirit_root": str(player["spirit_root"]),
            "additional_roots": list(dict.fromkeys(valid_roots)),
            "realm_id": realm_id,
            "layer": int(player.get("layer", 1)),
            "opportunity": opportunity,
            "heart_demon": _safe_float(player.get("heart_demon", 0.0), "player.heart_demon"),
            "bottleneck": bottleneck,
            "breakthrough_pity": {
                str(key): max(0, int(value))
                for key, value in dict(player.get("breakthrough_pity", {})).items()
            },
            "qi_experience": {
                source: max(0.0, _safe_float(
                    dict(player.get("qi_experience", {})).get(source, 0.0),
                    f"player.qi_experience.{source}",
                ))
                for source in QI_SOURCES
            },
        }
        state.entities.put(actor_id, CULTIVATION, cultivation)
        known: list[str] = []
        for index, raw in enumerate(player.get("known_techniques", [])):
            technique_id = str(raw.get("id", "")) if isinstance(raw, dict) else ""
            if technique_id in self.definitions.techniques and technique_id not in known:
                known.append(technique_id)
            elif technique_id:
                report.warn(
                    "unknown_technique", f"player.known_techniques[{index}]",
                    f"功法 {technique_id} 尚无V2定义，未导入",
                )
        main = player.get("technique")
        main_id = str(main.get("id", "")) if isinstance(main, dict) else ""
        if main_id and main_id not in self.definitions.techniques:
            report.warn("unknown_technique", "player.technique", f"主修功法 {main_id} 尚无V2定义")
            main_id = ""
        if main_id and main_id not in known:
            known.append(main_id)
        state.entities.put(
            actor_id,
            PRACTICE,
            {"known_techniques": known, "main_technique_id": main_id or None},
        )
        world_id = str(player.get("world", "human"))
        location_id = str(player.get("location_id") or "")
        if location_id not in self.definitions.worlds[world_id].locations:
            fallback = self.definitions.default_location(world_id)
            report.warn(
                "unknown_location", "player.location_id",
                f"地点 {location_id or '<empty>'} 无法映射，已回退到 {fallback}",
            )
            location_id = fallback
        state.entities.put(actor_id, LOCATION, {"world_id": world_id, "location_id": location_id})
        report.imported_counts["techniques"] = len(known)

    def _import_rng(
        self, state: WorldState, source: dict[str, Any], report: LegacyImportReport,
    ) -> None:
        raw = str(source.get("rng_state", ""))
        if not raw:
            report.warn("rng_reset", "rng_state", "旧存档没有随机数状态，V2将从原种子重新开始")
            return
        try:
            probe = random.Random()
            probe.setstate(ast.literal_eval(raw))
        except (ValueError, SyntaxError, TypeError) as error:
            report.warn("rng_reset", "rng_state", f"旧随机数状态无效，已从原种子重置：{error}")
            return
        state.rng_state = raw

    def _import_inventory(
        self,
        state: WorldState,
        actor_id: str,
        player: dict[str, Any],
        report: LegacyImportReport,
    ) -> None:
        items: dict[str, int] = {}
        for index, raw in enumerate(player.get("inventory", [])):
            if not isinstance(raw, dict):
                report.warn("invalid_item", f"player.inventory[{index}]", "非对象行囊项未导入")
                continue
            item_id = str(raw.get("id", ""))
            quantity = _safe_int(raw.get("quantity", 1), f"player.inventory[{index}].quantity")
            if quantity <= 0:
                report.warn("invalid_item", f"player.inventory[{index}]", "非正数物品数量未导入")
                continue
            if item_id not in self.definitions.items:
                report.warn(
                    "unknown_item", f"player.inventory[{index}]",
                    f"物品 {item_id or '<empty>'} 尚无V2定义，未导入",
                )
                continue
            items[item_id] = items.get(item_id, 0) + quantity
        state.entities.put(actor_id, INVENTORY, {"items": items, "reserved": {}})
        state.entities.put(actor_id, MARKET, {"revision": 0, "offers": []})
        report.imported_counts["inventory_kinds"] = len(items)
        report.imported_counts["inventory_quantity"] = sum(items.values())

    def _import_relations(
        self,
        state: WorldState,
        actor_id: str,
        player: dict[str, Any],
        report: LegacyImportReport,
    ) -> None:
        rows: list[tuple[str, dict[str, Any], str]] = []
        companion = player.get("dao_companion")
        if isinstance(companion, dict):
            rows.append(("dao_companion", companion, "companion"))
        master = player.get("master")
        if isinstance(master, dict):
            rows.append(("master_disciple", master, "master"))
        for raw in player.get("disciples", []):
            if isinstance(raw, dict):
                rows.append(("master_disciple", raw, "disciple"))
        for raw in player.get("dao_friends", []):
            if isinstance(raw, dict):
                rows.append(("friend", raw, "friend"))
        for raw in player.get("concubines", []):
            if isinstance(raw, dict):
                rows.append(("concubine", raw, "concubine"))
        legacy_entities: dict[str, str] = {}
        imported = 0
        for index, (kind, raw, direction) in enumerate(rows):
            legacy_id = str(raw.get("id", "")).strip() or f"anonymous:{direction}:{index}"
            npc_id = legacy_entities.get(legacy_id)
            if npc_id is None:
                npc_id = self._create_related_character(state, raw, legacy_id, report)
                legacy_entities[legacy_id] = npc_id
            if any(
                {edge.source_id, edge.target_id} == {actor_id, npc_id}
                for edge in state.relations.find()
            ):
                report.warn(
                    "relationship_conflict", f"player.{direction}",
                    f"人物 {legacy_id} 在V1拥有重叠关系；仅保留优先出现的一种",
                )
                continue
            source_id, target_id = actor_id, npc_id
            if direction == "master":
                source_id, target_id = npc_id, actor_id
            elif kind in {"friend", "dao_companion"}:
                source_id, target_id = sorted((actor_id, npc_id))
            state.relations.add(
                source_id=source_id,
                target_id=target_id,
                kind=kind,
                created_year=state.clock.year,
                metadata={"legacy_id": legacy_id, "imported": True},
            )
            imported += 1
        report.imported_counts["related_characters"] = len(legacy_entities)
        report.imported_counts["relationships"] = imported

    def _create_related_character(
        self,
        state: WorldState,
        raw: dict[str, Any],
        legacy_id: str,
        report: LegacyImportReport,
    ) -> str:
        entity_id = state.entities.create("character")
        gender = str(raw.get("gender", "male"))
        if gender not in {"male", "female"}:
            gender = "female" if sum(map(ord, legacy_id)) % 2 else "male"
            report.warn("npc_default", f"relationship[{legacy_id}].gender", "关系人物性别缺失，已稳定补齐")
        age = max(0, int(raw.get("age", 16)))
        lifespan_raw = raw.get("lifespan")
        lifespan = None if lifespan_raw is None else max(0, int(lifespan_raw))
        alive = bool(raw.get("alive", True))
        if alive and lifespan is not None and lifespan <= age:
            alive = False
            report.warn(
                "npc_life_normalized", f"relationship[{legacy_id}]",
                "关系人物已达到寿限，导入时规范为死亡状态",
            )
        state.entities.put(entity_id, IDENTITY, {
            "name": str(raw.get("name", "无名故人")).strip()[:40] or "无名故人",
            "gender": gender,
            "race": str(raw.get("race", "human")),
        })
        state.entities.put(entity_id, LIFE, {
            "birth_year": state.clock.year - age,
            "lifespan": lifespan,
            "alive": alive,
            "death_reason": raw.get("death_reason"),
        })
        state.entities.put(entity_id, ACTIVITY, {"rest_years": 0, "actions_completed": 0})
        root = str(raw.get("spirit_root", "supreme_wood"))
        if root not in self.definitions.roots:
            root = "supreme_wood"
            report.warn("npc_default", f"relationship[{legacy_id}].spirit_root", "关系人物灵根无法映射，已使用安全默认值")
        path = str(raw.get("path", "dao"))
        if path not in self.definitions.paths:
            path = "dao"
            report.warn("npc_default", f"relationship[{legacy_id}].path", "关系人物道统无法映射，已使用安全默认值")
        realm_index = max(0, min(len(self.definitions.realms) - 1, int(raw.get("realm_index", 0))))
        realm = self.definitions.realms[realm_index]
        layer = max(1, min(realm.layers, int(raw.get("layer", 1))))
        state.entities.put(entity_id, CULTIVATION, {
            "path": path,
            "spirit_root": root,
            "additional_roots": [],
            "realm_id": realm.id,
            "layer": layer,
            "opportunity": max(0.0, _safe_float(
                raw.get("opportunity", 0.0), f"relationship[{legacy_id}].opportunity"
            )),
            "heart_demon": 0.0,
            "bottleneck": None,
            "breakthrough_pity": {},
            "qi_experience": {source: 0.0 for source in QI_SOURCES},
        })
        known = []
        main_id = str(raw.get("main_technique_id", ""))
        if main_id in self.definitions.techniques:
            known.append(main_id)
        else:
            main_id = ""
        state.entities.put(entity_id, PRACTICE, {
            "known_techniques": known,
            "main_technique_id": main_id or None,
        })
        world_id = str(raw.get("world", "human"))
        if world_id not in self.definitions.worlds or not self.definitions.worlds[world_id].enabled:
            world_id = "human"
            report.warn("npc_default", f"relationship[{legacy_id}].world", "关系人物所在世界无法映射，已回退人界")
        location_id = str(raw.get("location_id") or self.definitions.default_location(world_id))
        if location_id not in self.definitions.worlds[world_id].locations:
            location_id = self.definitions.default_location(world_id)
        state.entities.put(entity_id, LOCATION, {"world_id": world_id, "location_id": location_id})
        inventory: dict[str, int] = {}
        treasure = str(raw.get("treasure_item_id", ""))
        if treasure in self.definitions.items and not raw.get("treasure_looted"):
            inventory[treasure] = 1
        state.entities.put(entity_id, INVENTORY, {"items": inventory, "reserved": {}})
        state.entities.put(entity_id, MARKET, {"revision": 0, "offers": []})
        state.entities.put(entity_id, CONDITION, {"hp_ratio": 1.0, "mp_ratio": 1.0})
        state.entities.put(entity_id, LEGACY_AUDIT, {"legacy_entity_id": legacy_id})
        return entity_id

    def _import_faction(
        self,
        state: WorldState,
        actor_id: str,
        source: dict[str, Any],
        player: dict[str, Any],
        report: LegacyImportReport,
    ) -> None:
        legacy_faction_id = str(player.get("faction_id") or "")
        if not legacy_faction_id:
            report.imported_counts["faction_memberships"] = 0
            return
        target_id = next((
            faction_id for faction_id in state.entities.with_component(FACTION_PROFILE)
            if state.entities.require(faction_id, FACTION_PROFILE).get("external_id") == legacy_faction_id
        ), None)
        sects = source.get("sects", {}) if isinstance(source.get("sects"), dict) else {}
        legacy_profile = sects.get(legacy_faction_id)
        if target_id is None and isinstance(legacy_profile, dict):
            world_id = str(legacy_profile.get("world", player.get("world", "human")))
            if world_id not in self.definitions.worlds:
                report.warn("unknown_faction", "player.faction_id", "玩家所属自建势力世界无法映射，未导入成员身份")
                return
            target_id = state.entities.create("faction")
            founded = bool(legacy_profile.get("founded_by_player"))
            state.entities.put(target_id, FACTION_PROFILE, {
                "external_id": legacy_faction_id,
                "name": str(legacy_profile.get("name", legacy_faction_id)),
                "world_id": world_id,
                "path": str(legacy_profile.get("path", "dao")),
                "allegiance_race": str(legacy_profile.get("allegiance_race") or "human"),
                "description": str(legacy_profile.get("description", "")),
                "color": "#888888",
                "active": not bool(legacy_profile.get("extinct", False)),
            })
            state.entities.put(target_id, FACTION_GOVERNANCE, {
                "creator_id": actor_id if founded else None,
                "controller_id": actor_id if founded else None,
                "designated_successor_id": None,
            })
        if target_id is None:
            report.warn(
                "unknown_faction", "player.faction_id",
                f"势力 {legacy_faction_id} 尚无V2定义，未导入成员身份",
            )
            report.imported_counts["faction_memberships"] = 0
            return
        profile = state.entities.require(target_id, FACTION_PROFILE)
        if not profile.get("active"):
            profile["active"] = True
            state.entities.put(target_id, FACTION_PROFILE, profile)
            report.warn("faction_reactivated", "player.faction_id", "所属势力在旧档中已灭亡，为保持成员身份临时恢复为活跃")
        founded = isinstance(legacy_profile, dict) and bool(legacy_profile.get("founded_by_player"))
        role = "founder" if founded else "member"
        state.relations.add(
            source_id=actor_id,
            target_id=target_id,
            kind=MEMBERSHIP,
            created_year=max(0, state.clock.year - max(0, int(player.get("age", 16)) - int(player.get("faction_join_age") or player.get("age", 16)))),
            metadata={"role": role, "contribution": max(0, int(player.get("faction_contribution", 0)))},
        )
        if founded:
            governance = state.entities.require(target_id, FACTION_GOVERNANCE)
            governance.update(creator_id=actor_id, controller_id=actor_id)
            state.entities.put(target_id, FACTION_GOVERNANCE, governance)
        report.imported_counts["faction_memberships"] = 1

    def _import_extensions(
        self,
        state: WorldState,
        actor_id: str,
        player: dict[str, Any],
        report: LegacyImportReport,
    ) -> None:
        ghost = state.entities.get(actor_id, GHOST_SOUL)
        if ghost is not None:
            hp_current = player.get("ghost_intrinsic_hp_current")
            mp_current = player.get("ghost_intrinsic_mp_current")
            ghost.update(
                intrinsic_hp=max(0.0, float(ghost["intrinsic_hp"] if hp_current is None else hp_current)),
                intrinsic_mp=max(0.0, float(ghost["intrinsic_mp"] if mp_current is None else mp_current)),
                erosion_rate_pp=max(0.0, float(player.get("ghost_soul_erosion_rate_pp", 0.0))),
                erosion_time_progress=max(0.0, float(player.get("ghost_soul_erosion_time_progress", 0.0))),
                wangsheng=max(0, int(player.get("ghost_wangsheng_energy", 0))),
                reincarnation_imprints={
                    str(key): int(value)
                    for key, value in dict(player.get("ghost_reincarnation_imprints", {})).items()
                },
            )
            peak_index = player.get("ghost_intrinsic_highwater_realm")
            if isinstance(peak_index, int) and 0 <= peak_index < len(self.definitions.realms):
                ghost["historical_peak"] = {
                    "realm_id": self.definitions.realms[peak_index].id,
                    "layer": max(1, int(player.get("ghost_intrinsic_highwater_layer") or 1)),
                }
            state.entities.put(actor_id, GHOST_SOUL, ghost)
            report.imported_counts["ghost_states"] = 1
        elif str(player.get("path", "")) == "ghost" and any(
            _meaningful(player.get(key)) for key in (
                "ghost_intrinsic_hp_current", "ghost_intrinsic_mp_current",
                "ghost_soul_erosion_rate_pp", "ghost_wangsheng_energy",
            )
        ):
            report.warn("disabled_extension", "player.ghost_*", "鬼修DLC未加载，专属状态未导入")
        monster = state.entities.get(actor_id, MONSTER_BLOODLINE)
        if monster is not None:
            species_id = player.get("monster_species_id")
            monster_document = self.definitions.extension_documents.get("monster_bloodlines.json", {})
            species_ids = {
                str(row.get("id")) for row in monster_document.get("species", [])
                if isinstance(row, dict)
            }
            if species_id is not None and str(species_id) not in species_ids:
                report.warn(
                    "unknown_monster_species", "player.monster_species_id",
                    f"妖族本源 {species_id} 无法映射，已留空",
                )
                species_id = None
            monster.update(
                species_id=species_id,
                evolution_id=player.get("monster_evolution_id"),
                evolution_history=list(player.get("monster_evolution_history", [])),
                adaptation_years={
                    str(key): max(0, int(value))
                    for key, value in dict(player.get("monster_adaptation_progress", {})).items()
                },
                adaptations=list(player.get("monster_adaptations", [])),
                imprints=list(player.get("monster_bloodline_imprints", [])),
                traits=list(player.get("monster_acquired_bloodline_traits", [])),
            )
            state.entities.put(actor_id, MONSTER_BLOODLINE, monster)
            report.imported_counts["monster_states"] = 1
        elif str(player.get("path", "")) == "monster" and any(
            _meaningful(player.get(key)) for key in (
                "monster_species_id", "monster_evolution_id",
                "monster_evolution_history", "monster_adaptations",
            )
        ):
            report.warn("disabled_extension", "player.monster_*", "妖修DLC未加载，专属状态未导入")

    def _import_combat_condition(
        self,
        state: WorldState,
        actor_id: str,
        player: dict[str, Any],
        report: LegacyImportReport,
    ) -> None:
        state.entities.put(actor_id, CONDITION, {"hp_ratio": 1.0, "mp_ratio": 1.0})
        snapshot = combat_snapshot(state, self.definitions, actor_id)
        hp = max(0.0, _safe_float(player.get("hp", snapshot["max_hp"]), "player.hp"))
        mp = max(0.0, _safe_float(player.get("mp", snapshot["max_mp"]), "player.mp"))
        hp_ratio = min(1.0, hp / float(snapshot["max_hp"]))
        mp_ratio = min(1.0, mp / float(snapshot["max_mp"]))
        if hp > float(snapshot["max_hp"]) or mp > float(snapshot["max_mp"]):
            report.warn("combat_stat_clamped", "player.hp/mp", "V1绝对战斗资源超过V2派生上限，已按满状态导入")
        state.entities.put(actor_id, CONDITION, {"hp_ratio": hp_ratio, "mp_ratio": mp_ratio})

    def _audit_deferred_fields(
        self,
        source: dict[str, Any],
        player: dict[str, Any],
        report: LegacyImportReport,
    ) -> None:
        for key, value in source.items():
            if key not in self._MAPPED_TOP_LEVEL and _meaningful(value):
                report.warn("deferred_system", key, "该顶层系统尚未迁移到V2，数据仅在原存档保留")
        for key, value in player.items():
            if key not in self._MAPPED_PLAYER_FIELDS and _meaningful(value):
                report.warn("deferred_player_field", f"player.{key}", "该人物字段尚未迁移到V2，数据仅在原存档保留")
