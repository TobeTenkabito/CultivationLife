from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .domain.character import (
    BootstrapGame,
    PerformTimedAction,
    character_invariants,
    character_view,
    register_character_domain,
)
from .domain.cultivation import (
    AttemptBreakthrough,
    PerformActionUnits,
    cultivation_invariants,
    cultivation_view,
    register_cultivation_domain,
)
from .domain.combat import (
    ResolveCombat,
    combat_invariants,
    combat_view,
    register_combat_domain,
)
from .domain.economy import (
    BuyMarketOffer,
    RefreshMarket,
    economy_invariants,
    inventory_view,
    market_view,
    register_economy_domain,
)
from .domain.extensions import (
    extension_invariants,
    extension_view,
    reconcile_extension_state,
    register_extension_domains,
)
from .domain.factions import (
    InviteRelationshipToFaction,
    SetFactionRewardPreference,
    faction_catalog_view,
    faction_invariants,
    faction_view,
    register_faction_domain,
)
from .domain.relations import relationship_invariants, relationship_view, register_relationship_domain
from .domain.presentation import (
    RecordWorldNews,
    SetWorldNewsDebug,
    UpdateSetting,
    presentation_invariants,
    presentation_view,
    reconcile_presentation_state,
    register_presentation_domain,
)
from .domain.world import TravelWithinWorld, register_world_domain, world_invariants, world_view
from .infrastructure.content_loader import V2ContentLoader
from .infrastructure.legacy_import import (
    LEGACY_AUDIT,
    LegacyImportError,
    LegacyV1Importer,
    backup_legacy_save,
    load_legacy_save,
)
from .infrastructure.sqlite_store import SQLiteSaveStore
from .kernel.bus import CommandBus, SimulationContext
from .kernel.model import EventScope, WorldState
from .kernel.services import InvariantRegistry


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class CommandExecution:
    game: dict[str, Any]
    events: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class LegacyImportExecution:
    game: dict[str, Any]
    report: dict[str, Any]


class V2GameEngine:
    """Transactional application boundary for the V2 simulation."""

    def __init__(
        self,
        database_path: Path,
        *,
        content_directory: Path | None = None,
        legacy_backup_directory: Path | None = None,
    ):
        default_content = Path(__file__).resolve().parents[2] / "content"
        self.definitions = V2ContentLoader.load(content_directory or default_content)
        database_path = Path(database_path)
        self.store = SQLiteSaveStore(database_path)
        self.legacy_backup_directory = Path(
            legacy_backup_directory or database_path.parent / "legacy-v1-backups"
        )
        self.commands = CommandBus()
        self.invariants = InvariantRegistry()
        register_character_domain(self.commands, self.definitions)
        register_cultivation_domain(self.commands, self.definitions)
        register_world_domain(self.commands, self.definitions)
        register_relationship_domain(self.commands)
        register_faction_domain(self.commands, self.definitions)
        register_economy_domain(self.commands, self.definitions)
        register_combat_domain(self.commands, self.definitions)
        register_extension_domains(self.commands, self.definitions)
        register_presentation_domain(self.commands, self.definitions)
        self.invariants.register("character", character_invariants)
        self.invariants.register("cultivation", cultivation_invariants(self.definitions))
        self.invariants.register("world", world_invariants(self.definitions))
        self.invariants.register("relations", relationship_invariants)
        self.invariants.register("factions", faction_invariants(self.definitions))
        self.invariants.register("economy", economy_invariants(self.definitions))
        self.invariants.register("combat", combat_invariants)
        self.invariants.register("extensions", extension_invariants(self.definitions))
        self.invariants.register("presentation", presentation_invariants(self.definitions))

    def create_game(
        self,
        name: str,
        *,
        seed: int | None = None,
        starting_age: int = 16,
        gender: str = "male",
        race: str = "human",
        spirit_root: str = "supreme_wood",
        path: str = "dao",
        start_world: str = "human",
    ) -> dict[str, Any]:
        now = _now_iso()
        state = WorldState.new(seed=seed if seed is not None else secrets.randbits(63), created_at=now)
        events = self.commands.execute(state, BootstrapGame(
            name=name,
            starting_age=starting_age,
            gender=gender,
            race=race,
            spirit_root=spirit_root,
            path=path,
            start_world=start_world,
        ))
        reconcile_extension_state(state, self.definitions)
        reconcile_presentation_state(state)
        self.invariants.validate(state)
        player = character_view(state)
        self.store.create(state, events, player_name=player["name"])
        return self._present(state)

    def import_v1_save(
        self,
        source_path: Path,
        *,
        target_game_id: str | None = None,
    ) -> LegacyImportExecution:
        """Import one legacy JSON save without changing the source file."""
        source = Path(source_path)
        document, source_sha256 = load_legacy_save(source)
        for saved in self.store.list_games():
            existing = self.store.load(str(saved["game_id"]))
            actor_id = existing.controlled_entity_id
            audit = existing.entities.get(actor_id, LEGACY_AUDIT) if actor_id else None
            if audit and audit.get("source_sha256") == source_sha256:
                raise LegacyImportError(
                    f"该V1存档已经导入为V2存档：{existing.game_id}"
                )
        importer = LegacyV1Importer(self.definitions, self.commands)
        result = importer.import_document(
            document,
            source_name=source.name,
            source_sha256=source_sha256,
            target_game_id=target_game_id,
        )
        state = result.state
        reconcile_extension_state(state, self.definitions)
        reconcile_presentation_state(state)
        self.invariants.validate(state)
        player = character_view(state)
        backup = backup_legacy_save(
            source,
            self.legacy_backup_directory,
            expected_sha256=source_sha256,
        )
        result.report.backup_path = str(backup.path)
        result.report.backup_sha256 = backup.sha256
        result.report.backup_created = backup.created
        state.entities.put(str(state.controlled_entity_id), LEGACY_AUDIT, result.report.to_dict())
        backup_context = SimulationContext(state=state, event_bus=self.commands.event_bus)
        backup_context.emit(
            "migration.v1.backup.verified",
            source="legacy_import",
            scope=EventScope.entity(str(state.controlled_entity_id)),
            payload={
                "backup_path": str(backup.path),
                "backup_sha256": backup.sha256,
                "backup_created": backup.created,
            },
        )
        backup_context.persist_rng()
        self.store.create(
            state,
            [*result.events, *backup_context.emitted_events],
            player_name=player["name"],
        )
        return LegacyImportExecution(game=self._present(state), report=result.report.to_dict())

    def legacy_import_report(self, game_id: str) -> dict[str, Any]:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        report = state.entities.get(actor_id, LEGACY_AUDIT) if actor_id else None
        if report is None:
            raise KeyError("该V2存档不是由V1导入的")
        return report

    def execute(self, game_id: str, command: object) -> CommandExecution:
        state = self.store.load(game_id)
        reconcile_extension_state(state, self.definitions)
        reconcile_presentation_state(state)
        self.invariants.validate(state)
        expected_revision = state.revision
        events = self.commands.execute(state, command)
        self.invariants.validate(state)
        state.updated_at = _now_iso()
        player = character_view(state)
        self.store.save(
            state,
            events,
            player_name=player["name"],
            expected_revision=expected_revision,
        )
        return CommandExecution(
            game=self._present(state),
            events=tuple(event.to_dict() for event in events),
        )

    def perform_timed_action(self, game_id: str, action: str, years: int = 1) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id,
            PerformTimedAction(actor_id=actor_id, action=action, years=years),
        )

    def perform_action(self, game_id: str, action: str, units: int = 1) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, PerformActionUnits(actor_id=actor_id, action=action, units=units))

    def attempt_breakthrough(self, game_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, AttemptBreakthrough(actor_id=actor_id))

    def travel(self, game_id: str, destination_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, TravelWithinWorld(actor_id=actor_id, destination_id=destination_id))

    def refresh_market(self, game_id: str, *, force: bool = False) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, RefreshMarket(actor_id=actor_id, force=force))

    def buy_market_offer(self, game_id: str, offer_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, BuyMarketOffer(actor_id=actor_id, offer_id=offer_id))

    def fight(self, game_id: str, target_id: str, *, objective: str = "duel") -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id,
            ResolveCombat(attacker_id=actor_id, target_id=target_id, objective=objective),
        )

    def invite_relationship_to_faction(
        self, game_id: str, target_id: str
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id,
            InviteRelationshipToFaction(actor_id=actor_id, target_id=target_id),
        )

    def set_faction_reward(self, game_id: str, reward_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id,
            SetFactionRewardPreference(actor_id=actor_id, reward_id=reward_id),
        )

    def update_setting(self, game_id: str, setting: str, enabled: bool) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id,
            UpdateSetting(actor_id=actor_id, setting=setting, enabled=enabled),
        )

    def set_world_news_debug(self, game_id: str, enabled: bool) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, SetWorldNewsDebug(actor_id=actor_id, enabled=enabled))

    def record_world_news(
        self,
        game_id: str,
        world_id: str,
        title: str,
        summary: str,
        *,
        tags: tuple[str, ...] = (),
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id,
            RecordWorldNews(
                actor_id=actor_id,
                world_id=world_id,
                title=title,
                summary=summary,
                tags=tags,
            ),
        )

    def get_game(self, game_id: str) -> dict[str, Any]:
        state = self.store.load(game_id)
        reconcile_extension_state(state, self.definitions)
        reconcile_presentation_state(state)
        self.invariants.validate(state)
        return self._present(state)

    def list_games(self) -> list[dict[str, Any]]:
        return self.store.list_games()

    def event_journal(self, game_id: str, *, after_sequence: int = 0) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self.store.load_events(game_id, after_sequence=after_sequence)]

    def _present(self, state: WorldState) -> dict[str, Any]:
        player = character_view(state)
        cultivation = cultivation_view(state, self.definitions)
        current_world = world_view(state, self.definitions)
        presentation = presentation_view(state)
        alive = bool(player["alive"])
        return {
            "format": "cultivation-life-v2",
            "id": state.game_id,
            "revision": state.revision,
            "schema_version": state.schema_version,
            "clock": {"year": state.clock.year},
            "player": {**player, "cultivation": cultivation},
            "world": current_world,
            "relationships": relationship_view(state),
            "faction": faction_view(state, self.definitions),
            "available_factions": faction_catalog_view(state, current_world["world_id"]),
            "inventory": inventory_view(state, self.definitions),
            "market": market_view(state, self.definitions),
            "combat": combat_view(state, self.definitions),
            "extensions": extension_view(state, self.definitions),
            "settings": presentation["settings"],
            "debug_world_news": presentation["debug_world_news"],
            "world_news": presentation["world_news"],
            "capabilities": {
                "character.cultivate": {
                    "enabled": alive,
                    "reason": None if alive else "角色已经死亡",
                },
                "character.rest": {
                    "enabled": alive,
                    "reason": None if alive else "角色已经死亡",
                },
                "cultivation.breakthrough": {
                    "enabled": alive and cultivation["bottleneck"] in {"minor", "major"},
                    "reason": None if alive and cultivation["bottleneck"] else "尚未抵达突破瓶颈",
                },
                "world.travel": {
                    "enabled": alive,
                    "reason": None if alive else "角色已经死亡",
                },
                "economy.market": {
                    "enabled": alive and cultivation["realm_index"] > 0,
                    "reason": None if alive and cultivation["realm_index"] > 0 else "凡人或死亡角色无法进入坊市",
                },
                "combat.initiate": {
                    "enabled": alive,
                    "reason": None if alive else "角色已经死亡",
                },
            },
        }
