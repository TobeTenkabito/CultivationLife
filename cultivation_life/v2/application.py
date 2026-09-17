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
from .domain.actions import (
    action_invariants,
    action_view,
    reconcile_action_runtime,
    register_action_domain,
)
from .domain.advanced_cultivation import (
    AbsorbTransformationMaterial,
    AttemptBodyBreakthrough,
    AttemptDivineSenseBreakthrough,
    EquipSpecialTechnique,
    ManageTransformation,
    advanced_cultivation_invariants,
    advanced_cultivation_view,
    reconcile_advanced_cultivation,
    register_advanced_cultivation_domain,
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
    UseItem,
    economy_invariants,
    inventory_view,
    market_view,
    register_economy_domain,
)
from .domain.assets import (
    asset_invariants,
    asset_view,
    reconcile_asset_ledger,
    register_asset_domain,
)
from .domain.auction import (
    AdvanceAuctionRound,
    BargainPrivateTrade,
    BuyBlackMarket,
    BuyPrivateTrade,
    ChooseAuctionIdentity,
    ConsignAuctionAsset,
    LeaveBlackMarket,
    NegotiateAuction,
    PlaceAuctionBid,
    ScheduleAuction,
    SearchBlackMarket,
    SellBlackMarketAsset,
    SellPrivateTrade,
    auction_invariants,
    auction_view,
    reconcile_auction_state,
    register_auction_domain,
)
from .domain.artifacts import (
    ActivateFormation,
    DeactivateFormation,
    DeleteFormation,
    DeployGroundFormation,
    ForgeArtifact,
    ManageNatalArtifact,
    PreviewCrafting,
    PreviewFormation,
    RepairGroundFormation,
    SaveCraftingBlueprint,
    SaveFormation,
    SellCraftedArtifact,
    WithdrawGroundFormation,
    artifact_invariants,
    crafting_view,
    formation_view,
    natal_view,
    reconcile_artifact_state,
    register_artifact_domains,
)
from .domain.production import (
    HarvestSpiritCrop,
    IrrigateSpiritCrop,
    PlantSpiritCrop,
    ReclaimSpiritField,
    RefinePill,
    SellSpiritPlant,
    UseHarvestedPlant,
    production_invariants,
    production_view,
    reconcile_production_state,
    register_production_domain,
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
from .domain.family import (
    CreateFamily,
    family_invariants,
    family_view,
    reconcile_family_state,
    register_family_domain,
)
from .domain.concubines import (
    EnterConcubineStatus,
    ManageConcubine,
    ManageConcubineStatus,
    concubine_invariants,
    concubine_view,
    reconcile_concubine_state,
    register_concubine_domain,
)
from .domain.relations import (
    BefriendDaoist,
    ChangeAffinity,
    GiftDisciple,
    InteractDaoCompanion,
    InteractDaoFriend,
    OfferDiscipleRequest,
    ProposeDaoCompanion,
    RequestFromMaster,
    RequestMentorship,
    RespondDiscipleRequest,
    disciple_request_view,
    reconcile_relationship_state,
    relationship_invariants,
    relationship_view,
    register_relationship_domain,
)
from .domain.presentation import (
    RecordWorldNews,
    SetWorldNewsDebug,
    UpdateSetting,
    presentation_invariants,
    presentation_view,
    reconcile_presentation_state,
    register_presentation_domain,
)
from .domain.world import (
    AscendWorld,
    CrossWorld,
    TravelWithinWorld,
    reconcile_world_state,
    register_world_domain,
    world_invariants,
    world_view,
)
from .domain.story import (
    QueueStoryEvent,
    ResolveStoryChoice,
    reconcile_story_state,
    register_story_domain,
    story_invariants,
    story_view,
)
from .domain.trials import (
    BeginAscensionTrial,
    reconcile_trial_state,
    register_trial_domain,
    register_trial_story_effects,
    trial_invariants,
    trial_view,
)
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
        register_action_domain(self.commands)
        register_cultivation_domain(self.commands, self.definitions)
        register_advanced_cultivation_domain(self.commands, self.definitions)
        register_trial_domain(self.commands, self.definitions)
        register_world_domain(self.commands, self.definitions)
        register_relationship_domain(self.commands, self.definitions)
        register_faction_domain(self.commands, self.definitions)
        register_family_domain(self.commands, self.definitions)
        register_concubine_domain(self.commands, self.definitions)
        register_economy_domain(self.commands, self.definitions)
        register_asset_domain(self.commands)
        register_production_domain(self.commands, self.definitions)
        register_auction_domain(self.commands, self.definitions)
        register_artifact_domains(self.commands, self.definitions)
        register_combat_domain(self.commands, self.definitions)
        register_extension_domains(self.commands, self.definitions)
        register_presentation_domain(self.commands, self.definitions)
        self.story_effects = register_story_domain(self.commands, self.definitions)
        register_trial_story_effects(self.story_effects, self.definitions)
        self.invariants.register("character", character_invariants)
        self.invariants.register("actions", action_invariants)
        self.invariants.register("cultivation", cultivation_invariants(self.definitions))
        self.invariants.register(
            "advanced_cultivation", advanced_cultivation_invariants(self.definitions)
        )
        self.invariants.register("trials", trial_invariants(self.definitions))
        self.invariants.register("world", world_invariants(self.definitions))
        self.invariants.register("relations", relationship_invariants)
        self.invariants.register("factions", faction_invariants(self.definitions))
        self.invariants.register("family", family_invariants)
        self.invariants.register("concubines", concubine_invariants)
        self.invariants.register("economy", economy_invariants(self.definitions))
        self.invariants.register("assets", asset_invariants)
        self.invariants.register("production", production_invariants(self.definitions))
        self.invariants.register("auction", auction_invariants)
        self.invariants.register("artifacts", artifact_invariants(self.definitions))
        self.invariants.register("combat", combat_invariants)
        self.invariants.register("extensions", extension_invariants(self.definitions))
        self.invariants.register("presentation", presentation_invariants(self.definitions))
        self.invariants.register("story", story_invariants(self.definitions))

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
        reconcile_action_runtime(state)
        reconcile_story_state(state)
        reconcile_advanced_cultivation(state, self.definitions)
        reconcile_world_state(state)
        reconcile_trial_state(state)
        reconcile_asset_ledger(state)
        reconcile_production_state(state)
        reconcile_auction_state(state)
        reconcile_artifact_state(state)
        reconcile_relationship_state(state)
        reconcile_family_state(state)
        reconcile_concubine_state(state)
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
        reconcile_action_runtime(state)
        reconcile_story_state(state)
        reconcile_advanced_cultivation(state, self.definitions)
        reconcile_world_state(state)
        reconcile_trial_state(state)
        reconcile_asset_ledger(state)
        reconcile_production_state(state)
        reconcile_auction_state(state)
        reconcile_artifact_state(state)
        reconcile_relationship_state(state)
        reconcile_family_state(state)
        reconcile_concubine_state(state)
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
        reconcile_action_runtime(state)
        reconcile_story_state(state)
        reconcile_advanced_cultivation(state, self.definitions)
        reconcile_world_state(state)
        reconcile_trial_state(state)
        reconcile_asset_ledger(state)
        reconcile_production_state(state)
        reconcile_auction_state(state)
        reconcile_artifact_state(state)
        reconcile_relationship_state(state)
        reconcile_family_state(state)
        reconcile_concubine_state(state)
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

    def change_affinity(
        self, game_id: str, target_id: str, amount: float, *, reason: str = "interaction",
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, ChangeAffinity(actor_id, target_id, amount, reason))

    def propose_dao_companion(self, game_id: str, target_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, ProposeDaoCompanion(actor_id, target_id))

    def interact_dao_companion(
        self, game_id: str, action: str, *, content_id: str = "",
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, InteractDaoCompanion(actor_id, action, content_id))

    def befriend_daoist(self, game_id: str, target_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, BefriendDaoist(actor_id, target_id))

    def interact_dao_friend(
        self, game_id: str, friend_id: str, action: str,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, InteractDaoFriend(actor_id, friend_id, action))

    def request_mentorship(
        self, game_id: str, target_id: str, role: str,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, RequestMentorship(actor_id, target_id, role))

    def offer_disciple_request(
        self, game_id: str, requester_id: str,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, OfferDiscipleRequest(requester_id, actor_id))

    def respond_disciple_request(
        self, game_id: str, request_id: str, accept: bool,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, RespondDiscipleRequest(actor_id, request_id, accept))

    def request_from_master(self, game_id: str, kind: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, RequestFromMaster(actor_id, kind))

    def gift_disciple(
        self, game_id: str, disciple_id: str, kind: str, content_id: str,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, GiftDisciple(actor_id, disciple_id, kind, content_id))

    def create_family(self, game_id: str, name: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, CreateFamily(actor_id, name))

    def manage_concubine(
        self, game_id: str, target_id: str, action: str,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, ManageConcubine(actor_id, target_id, action))

    def enter_concubine_status(
        self, game_id: str, owner_id: str, *, forced: bool = False,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id, EnterConcubineStatus(actor_id, owner_id, forced=forced)
        )

    def manage_concubine_status(
        self, game_id: str, action: str, *, method: str = "",
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id, ManageConcubineStatus(actor_id, action, method=method)
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

    def equip_special_technique(
        self, game_id: str, technique_id: str, slot: str,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, EquipSpecialTechnique(actor_id, technique_id, slot))

    def attempt_body_breakthrough(self, game_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, AttemptBodyBreakthrough(actor_id))

    def attempt_divine_sense_breakthrough(self, game_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, AttemptDivineSenseBreakthrough(actor_id))

    def absorb_transformation_material(
        self, game_id: str, item_id: str, *, mode: str = "direct",
        stat_id: str = "", batch: bool = False,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, AbsorbTransformationMaterial(
            actor_id, item_id, mode, stat_id, batch,
        ))

    def manage_transformation(
        self, game_id: str, form_id: str, action: str,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, ManageTransformation(actor_id, form_id, action))

    def travel(self, game_id: str, destination_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, TravelWithinWorld(actor_id=actor_id, destination_id=destination_id))

    def ascend_world(
        self, game_id: str, destination_world_id: str,
        *, invited_ids: tuple[str, ...] = (),
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id, AscendWorld(actor_id, destination_world_id, invited_ids)
        )

    def cross_world(self, game_id: str, destination_world_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, CrossWorld(actor_id, destination_world_id))

    def begin_ascension_trial(
        self, game_id: str, destination_world_id: str,
        *, invited_ids: tuple[str, ...] = (),
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id, BeginAscensionTrial(actor_id, destination_world_id, invited_ids)
        )

    def refresh_market(self, game_id: str, *, force: bool = False) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, RefreshMarket(actor_id=actor_id, force=force))

    def use_item(self, game_id: str, item_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, UseItem(actor_id, item_id))

    def reclaim_spirit_field(self, game_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, ReclaimSpiritField(actor_id))

    def plant_spirit_crop(
        self, game_id: str, plant_id: str, slot: int | None = None,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, PlantSpiritCrop(actor_id, plant_id, slot))

    def irrigate_spirit_crop(
        self, game_id: str, plot_id: str, mp_ratio: float = 0.0,
        booster_id: str = "",
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id, IrrigateSpiritCrop(actor_id, plot_id, mp_ratio, booster_id)
        )

    def harvest_spirit_crop(self, game_id: str, plot_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, HarvestSpiritCrop(actor_id, plot_id))

    def sell_spirit_plant(
        self, game_id: str, asset_id: str, *, venue: str = "market",
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, SellSpiritPlant(actor_id, asset_id, venue))

    def use_harvested_plant(self, game_id: str, asset_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, UseHarvestedPlant(actor_id, asset_id))

    def refine_pill(
        self, game_id: str, target_item_id: str,
        materials: tuple[tuple[str, int], ...],
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, RefinePill(actor_id, target_item_id, materials))

    def schedule_auction(
        self, game_id: str, location_id: str = "",
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, ScheduleAuction(actor_id, location_id))

    def consign_auction_asset(
        self, game_id: str, asset_ref: str, start_price: int = 0,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id, ConsignAuctionAsset(actor_id, asset_ref, start_price)
        )

    def consign_auction_item(
        self, game_id: str, item_id: str, start_price: int = 0,
    ) -> CommandExecution:
        return self.consign_auction_asset(game_id, item_id, start_price)

    def place_auction_bid(self, game_id: str, lot_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, PlaceAuctionBid(actor_id, lot_id))

    def advance_auction_round(self, game_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, AdvanceAuctionRound(actor_id))

    def negotiate_at_auction(
        self, game_id: str, attendee_id: str,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, NegotiateAuction(actor_id, attendee_id))

    def choose_auction_identity(self, game_id: str, alias: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, ChooseAuctionIdentity(actor_id, alias))

    def buy_private_trade_item(
        self, game_id: str, attendee_id: str, offer_id: str,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id, BuyPrivateTrade(actor_id, attendee_id, offer_id)
        )

    def sell_private_trade_asset(
        self, game_id: str, attendee_id: str, asset_ref: str,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id, SellPrivateTrade(actor_id, attendee_id, asset_ref)
        )

    def sell_private_trade_item(
        self, game_id: str, attendee_id: str, item_id: str,
    ) -> CommandExecution:
        return self.sell_private_trade_asset(game_id, attendee_id, item_id)

    def bargain_private_trade(
        self, game_id: str, attendee_id: str, side: str, asset_ref: str,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id, BargainPrivateTrade(actor_id, attendee_id, side, asset_ref)
        )

    def search_black_market(self, game_id: str, pattern: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, SearchBlackMarket(actor_id, pattern))

    def buy_black_market_item(
        self, game_id: str, result_id: str,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, BuyBlackMarket(actor_id, result_id))

    def sell_black_market_asset(
        self, game_id: str, kind: str, asset_ref: str,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id, SellBlackMarketAsset(actor_id, kind, asset_ref)
        )

    def leave_black_market(self, game_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, LeaveBlackMarket(actor_id))

    def preview_crafting(
        self, game_id: str, payload: dict[str, Any],
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, PreviewCrafting(actor_id, dict(payload)))

    def forge_crafted_artifact(
        self, game_id: str, payload: dict[str, Any],
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, ForgeArtifact(actor_id, dict(payload)))

    def save_crafting_blueprint(
        self, game_id: str, payload: dict[str, Any],
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, SaveCraftingBlueprint(actor_id, dict(payload)))

    def crafted_artifact_action(
        self, game_id: str, artifact_id: str, action: str, start_price: int = 0,
    ) -> CommandExecution:
        if action == "sell":
            state = self.store.load(game_id)
            actor_id = state.controlled_entity_id
            if actor_id is None:
                raise ValueError("游戏尚未初始化")
            return self.execute(game_id, SellCraftedArtifact(actor_id, artifact_id))
        if action == "consign":
            return self.consign_auction_asset(game_id, artifact_id, start_price)
        if action in {"natal", "unbind_natal"}:
            return self.natal_artifact_action(
                game_id, "bind" if action == "natal" else "unbind", artifact_id
            )
        if action in {"equip", "unequip"}:
            raise ValueError("炼器法宝留在资产仓库中即自动生效，无需另行装备")
        raise ValueError("未知炼器法宝操作")

    def preview_formation(
        self, game_id: str, payload: dict[str, Any],
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, PreviewFormation(actor_id, dict(payload)))

    def save_formation(
        self, game_id: str, payload: dict[str, Any],
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, SaveFormation(actor_id, dict(payload)))

    def activate_formation(self, game_id: str, loadout_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, ActivateFormation(actor_id, loadout_id))

    def deactivate_formation(self, game_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, DeactivateFormation(actor_id))

    def delete_formation(self, game_id: str, loadout_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, DeleteFormation(actor_id, loadout_id))

    def deploy_ground_formation(
        self, game_id: str, owner_kind: str = "player",
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, DeployGroundFormation(actor_id, owner_kind))

    def withdraw_ground_formation(
        self, game_id: str, ground_id: str,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, WithdrawGroundFormation(actor_id, ground_id))

    def repair_ground_formation(
        self, game_id: str, ground_id: str, supply_id: str, quantity: int = 1,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id, RepairGroundFormation(actor_id, ground_id, supply_id, quantity)
        )

    def natal_artifact_action(
        self, game_id: str, action: str, item_id: str = "", slot_index: int = -1,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id, ManageNatalArtifact(actor_id, action, item_id, slot_index)
        )

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

    def choose(self, game_id: str, choice_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id, ResolveStoryChoice(actor_id=actor_id, choice_id=choice_id),
        )

    def queue_story_event(
        self, game_id: str, event_id: str, *, reason: str = "scripted",
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id,
            QueueStoryEvent(actor_id=actor_id, event_id=event_id, reason=reason),
        )

    def get_game(self, game_id: str) -> dict[str, Any]:
        state = self.store.load(game_id)
        reconcile_extension_state(state, self.definitions)
        reconcile_presentation_state(state)
        reconcile_action_runtime(state)
        reconcile_story_state(state)
        reconcile_advanced_cultivation(state, self.definitions)
        reconcile_world_state(state)
        reconcile_trial_state(state)
        reconcile_asset_ledger(state)
        reconcile_production_state(state)
        reconcile_auction_state(state)
        reconcile_artifact_state(state)
        reconcile_relationship_state(state)
        reconcile_family_state(state)
        reconcile_concubine_state(state)
        self.invariants.validate(state)
        return self._present(state)

    def list_games(self) -> list[dict[str, Any]]:
        return self.store.list_games()

    def event_journal(self, game_id: str, *, after_sequence: int = 0) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self.store.load_events(game_id, after_sequence=after_sequence)]

    def _present(self, state: WorldState) -> dict[str, Any]:
        player = character_view(state)
        cultivation = cultivation_view(state, self.definitions)
        advanced_cultivation = advanced_cultivation_view(state, self.definitions)
        current_world = world_view(state, self.definitions)
        presentation = presentation_view(state)
        story = story_view(state)
        action = action_view(state)
        alive = bool(player["alive"])
        interaction_open = story["pending_event"] is not None
        return {
            "format": "cultivation-life-v2",
            "id": state.game_id,
            "revision": state.revision,
            "schema_version": state.schema_version,
            "clock": {"year": state.clock.year},
            "player": {**player, "cultivation": cultivation, **advanced_cultivation},
            "world": current_world,
            "relationships": relationship_view(state),
            "disciple_requests": disciple_request_view(state),
            "faction": faction_view(state, self.definitions),
            "family": family_view(state, self.definitions),
            "concubine_system": concubine_view(state, self.definitions),
            "available_factions": faction_catalog_view(state, current_world["world_id"]),
            "inventory": inventory_view(state, self.definitions),
            "assets": asset_view(state),
            "production": production_view(state, self.definitions),
            "auction": auction_view(state, self.definitions),
            "crafting": crafting_view(state, self.definitions),
            "formation_system": formation_view(state, self.definitions),
            "natal_artifact": natal_view(state, self.definitions),
            "market": market_view(state, self.definitions),
            "combat": combat_view(state, self.definitions),
            "extensions": extension_view(state, self.definitions),
            "settings": presentation["settings"],
            "debug_world_news": presentation["debug_world_news"],
            "world_news": presentation["world_news"],
            "pending_event": story["pending_event"],
            "story": {
                "queued_event_count": story["queued_event_count"],
                "history": story["history"],
                "flags": story["flags"],
                "milestones": story["milestones"],
                "attributes": story["attributes"],
            },
            "action": action,
            "trial": trial_view(state),
            "capabilities": {
                "character.cultivate": {
                    "enabled": alive and not interaction_open,
                    "reason": "请先处理当前事件" if interaction_open else None if alive else "角色已经死亡",
                },
                "character.rest": {
                    "enabled": alive and not interaction_open,
                    "reason": "请先处理当前事件" if interaction_open else None if alive else "角色已经死亡",
                },
                "cultivation.breakthrough": {
                    "enabled": alive and not interaction_open and cultivation["bottleneck"] in {"minor", "major"},
                    "reason": "请先处理当前事件" if interaction_open else None if alive and cultivation["bottleneck"] else "尚未抵达突破瓶颈",
                },
                "world.travel": {
                    "enabled": alive and not interaction_open,
                    "reason": "请先处理当前事件" if interaction_open else None if alive else "角色已经死亡",
                },
                "economy.market": {
                    "enabled": alive and not interaction_open and cultivation["realm_index"] > 0,
                    "reason": "请先处理当前事件" if interaction_open else None if alive and cultivation["realm_index"] > 0 else "凡人或死亡角色无法进入坊市",
                },
                "combat.initiate": {
                    "enabled": alive and not interaction_open,
                    "reason": "请先处理当前事件" if interaction_open else None if alive else "角色已经死亡",
                },
            },
        }
