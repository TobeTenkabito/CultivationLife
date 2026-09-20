from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .domain.character import (
    IDENTITY,
    LIFE,
    LIFESPAN_DUE,
    WORLD_NPC_PROFILE,
    BootstrapGame,
    EnsureWorldCharacters,
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
    CULTIVATION,
    PRACTICE,
    AttemptBreakthrough,
    EquipMainTechnique,
    PerformActionUnits,
    breakthrough_view,
    cultivation_invariants,
    cultivation_view,
    register_cultivation_domain,
)
from .domain.combat import (
    ResolveCombat,
    combat_invariants,
    combat_snapshot,
    combat_view,
    register_combat_domain,
)
from .domain.party import (
    ManageParty,
    PARTY_MEMBER,
    party_crossing_ids,
    party_invariants,
    party_view,
    register_party_domain,
)
from .domain.demonic import (
    CaptiveAction,
    CraftMechanicalPuppet,
    EnterImprisonment,
    PostBattlePossession,
    PrisonAction,
    PuppetAction,
    RefineForeignSoul,
    demonic_invariants,
    demonic_view,
    reconcile_demonic_state,
    register_demonic_domain,
)
from .domain.ghost import (
    GhostAttachmentAction,
    GhostConstraintAction,
    GhostParadeAction,
    GhostSoulAction,
    LeavePossessedBody,
    PrepareGhostReincarnation,
    ReincarnateGhost,
    ghost_invariants,
    ghost_view,
    reconcile_ghost_state,
    register_ghost_domain,
    register_ghost_story_effects,
)
from .domain.monster import (
    ConfirmCustomLineage,
    EvolveMonster,
    PrepareCustomLineage,
    monster_invariants,
    monster_view,
    reconcile_monster_state,
    register_monster_domain,
)
from .domain.celestial import (
    HeavenlyCourtAction,
    ResolveHeavenlyElection,
    celestial_invariants,
    celestial_view,
    reconcile_celestial_state,
    register_celestial_domain,
    register_celestial_story_effects,
)
from .domain.intrigue import (
    INTRIGUE_GUEST,
    IntrigueGuestAction,
    IntriguePersonnelAction,
    IntrigueRecruitmentAction,
    IntrigueResolutionAction,
    intrigue_invariants,
    intrigue_view,
    reconcile_intrigue_state,
    register_intrigue_domain,
)
from .domain.war import (
    IssueBounty,
    WarAction,
    WarPeace,
    reconcile_war_state,
    register_war_domain,
    register_war_story_effects,
    war_invariants,
    war_view,
)
from .domain.world_simulation import register_world_simulation_domain
from .domain.economy import (
    INVENTORY,
    MARKET,
    BuyMarketOffer,
    RefreshMarket,
    ToggleMarketOfferLock,
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
    RepairGroundFormation,
    SaveCraftingBlueprint,
    SaveFormation,
    SellCraftedArtifact,
    WithdrawGroundFormation,
    artifact_invariants,
    crafting_view,
    formation_view,
    natal_view,
    preview_crafting_view,
    preview_formation_view,
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
    ConfigureMonsterBloodline,
    GHOST_SOUL,
    SpendWangsheng,
    extension_invariants,
    extension_view,
    reconcile_extension_state,
    register_extension_domains,
)
from .domain.factions import (
    FACTION_NPC,
    FACTION_GOVERNANCE,
    MEMBERSHIP,
    ArrangeFactionSuccession,
    DispatchFactionMember,
    EnsureFactionRosters,
    FoundFaction,
    InterceptFactionMember,
    InviteRelationshipToFaction,
    JoinFaction,
    LeaveFaction,
    ProposeDiplomacy,
    SetFactionRewardPreference,
    TransferVassalPersonnel,
    faction_catalog_view,
    faction_invariants,
    faction_view,
    governance_view,
    register_faction_domain,
    register_faction_story_effects,
)
from .domain.family import (
    CreateFamily,
    family_invariants,
    family_view,
    reconcile_family_state,
    register_family_domain,
)
from .domain.npc_lifecycle import (
    npc_lifecycle_invariants,
    reconcile_npc_lifecycle,
    register_npc_lifecycle_domain,
)
from .domain.concubines import (
    EnterConcubineStatus,
    ManageConcubine,
    ManageConcubineStatus,
    concubine_invariants,
    concubine_view,
    reconcile_concubine_state,
    register_concubine_domain,
    register_concubine_story_effects,
)
from .domain.relations import (
    BeginRelationshipCapture,
    BefriendDaoist,
    ChangeAffinity,
    EndRelationship,
    GiftDisciple,
    InteractDaoCompanion,
    InteractDaoFriend,
    OfferDiscipleRequest,
    ProposeDaoCompanion,
    RequestFromMaster,
    RequestMentorship,
    RespondDiscipleRequest,
    SOCIAL_PROFILE,
    disciple_request_view,
    reconcile_relationship_state,
    relationship_invariants,
    relationship_affinity,
    relationship_view,
    register_relationship_domain,
    register_relationship_story_effects,
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
    LOCATION,
    AscendWorld,
    CrossWorld,
    TravelWithinWorld,
    reconcile_world_state,
    register_world_domain,
    world_invariants,
    world_view,
)
from .domain.story import (
    BeginSpiritCrossing,
    RepairPendingStoryEvent,
    STORY_STATE,
    QueueStoryEvent,
    ResolveStoryChoice,
    reconcile_story_state,
    pending_story_needs_repair,
    register_story_domain,
    story_invariants,
    story_view,
)
from .domain.story_compat import register_story_compat_effects
from .domain.trials import (
    BeginAscensionTrial,
    reconcile_trial_state,
    register_trial_domain,
    register_trial_story_effects,
    tribulation_view,
    trial_invariants,
    trial_view,
)
from .infrastructure.content_loader import ContentLoader
from .infrastructure.sqlite_store import SQLiteSaveStore
from .achievement_system import (
    load_achievement_definitions,
    matching_achievement_ids,
    public_definition as public_achievement_definition,
)
from .kernel.bus import CommandBus
from .kernel.model import EventScope, WorldState
from .kernel.services import InvariantRegistry


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class CommandExecution:
    game: dict[str, Any]
    events: tuple[dict[str, Any], ...]


class GameEngine:
    """Transactional application boundary for the simulation."""

    def __init__(
        self,
        database_path: Path,
        *,
        content_directory: Path | None = None,
        extension_root: Path | None = None,
    ):
        default_content = Path(__file__).resolve().parents[1] / "content"
        content_root = Path(content_directory or default_content)
        project_root = (
            Path(extension_root) if extension_root is not None
            else content_root.parent
        )
        self.definitions = ContentLoader.load(
            content_root,
            project_root=project_root,
        )
        database_path = Path(database_path)
        self.store = SQLiteSaveStore(database_path)
        self.achievement_definitions = load_achievement_definitions(
            content_root, project_root, self.definitions
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
        register_npc_lifecycle_domain(self.commands, self.definitions)
        register_concubine_domain(self.commands, self.definitions)
        register_economy_domain(self.commands, self.definitions)
        register_asset_domain(self.commands)
        register_production_domain(self.commands, self.definitions)
        register_auction_domain(self.commands, self.definitions)
        register_artifact_domains(self.commands, self.definitions)
        register_combat_domain(self.commands, self.definitions)
        register_party_domain(self.commands, self.definitions)
        register_demonic_domain(self.commands, self.definitions)
        register_war_domain(self.commands, self.definitions)
        register_world_simulation_domain(self.commands, self.definitions)
        register_extension_domains(self.commands, self.definitions)
        register_ghost_domain(self.commands, self.definitions)
        register_monster_domain(self.commands, self.definitions)
        register_celestial_domain(self.commands, self.definitions)
        register_intrigue_domain(self.commands, self.definitions)
        register_presentation_domain(self.commands, self.definitions)
        self.story_effects = register_story_domain(self.commands, self.definitions)
        register_trial_story_effects(self.story_effects, self.definitions)
        register_relationship_story_effects(self.story_effects, self.definitions)
        register_faction_story_effects(self.story_effects, self.definitions)
        register_concubine_story_effects(self.story_effects, self.definitions)
        register_war_story_effects(self.story_effects, self.definitions)
        register_ghost_story_effects(self.story_effects, self.definitions)
        register_celestial_story_effects(self.story_effects)
        register_story_compat_effects(self.story_effects, self.definitions)
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
        self.invariants.register("npc_lifecycle", npc_lifecycle_invariants)
        self.invariants.register("concubines", concubine_invariants)
        self.invariants.register("economy", economy_invariants(self.definitions))
        self.invariants.register("assets", asset_invariants)
        self.invariants.register("production", production_invariants(self.definitions))
        self.invariants.register("auction", auction_invariants)
        self.invariants.register("artifacts", artifact_invariants(self.definitions))
        self.invariants.register("combat", combat_invariants)
        self.invariants.register("party", party_invariants)
        self.invariants.register("demonic", demonic_invariants)
        self.invariants.register("war", war_invariants(self.definitions))
        self.invariants.register("extensions", extension_invariants(self.definitions))
        self.invariants.register("ghost", ghost_invariants)
        self.invariants.register("monster", monster_invariants(self.definitions))
        self.invariants.register("celestial", celestial_invariants(self.definitions))
        self.invariants.register("intrigue", intrigue_invariants(self.definitions))
        self.invariants.register("presentation", presentation_invariants(self.definitions))
        self.invariants.register("story", story_invariants(self.definitions))

    def _ensure_current_market(self, state: WorldState):
        """Populate markets missing from migrated or newly promoted saves."""
        actor_id = state.controlled_entity_id
        if actor_id is None:
            return []
        cultivation = state.entities.get(actor_id, CULTIVATION)
        location = state.entities.get(actor_id, LOCATION)
        market = state.entities.get(actor_id, MARKET)
        life = state.entities.get(actor_id, LIFE)
        if not all(isinstance(row, dict) for row in (
            cultivation, location, market, life,
        )):
            return []
        if not bool(life.get("alive")):
            return []
        if self.definitions.realm_index(str(cultivation["realm_id"])) == 0:
            return []
        story = state.entities.get(actor_id, STORY_STATE) or {}
        if story.get("pending") is not None:
            return []
        world_id = str(location["world_id"])
        if not any(
            good.world_id == world_id for good in self.definitions.market_goods
        ):
            return []
        stale = (
            market.get("world_id") != location.get("world_id")
            or market.get("location_id") != location.get("location_id")
            or not market.get("offers")
        )
        if not stale:
            return []
        return self.commands.execute(
            state, RefreshMarket(actor_id=str(actor_id), force=True)
        )

    def list_achievements(self) -> dict[str, Any]:
        records = self.store.achievement_unlocks()
        rows = []
        for definition in self.achievement_definitions:
            record = records.get(str(definition["id"]))
            rows.append({
                **public_achievement_definition(definition),
                "unlocked": record is not None,
                "unlocked_at": record.get("unlocked_at") if record else None,
                "player_name": record.get("player_name") if record else None,
            })
        return {
            "achievements": rows,
            "unlocked": sum(bool(row["unlocked"]) for row in rows),
            "total": len(rows),
            "progress_available": True,
        }

    def _present_with_achievements(self, state: WorldState) -> dict[str, Any]:
        matched = matching_achievement_ids(
            state, self.definitions, self.achievement_definitions
        )
        actor_id = str(state.controlled_entity_id)
        identity = state.entities.require(actor_id, IDENTITY)
        fresh_ids = self.store.unlock_achievements(
            matched,
            unlocked_at=_now_iso(),
            game_id=state.game_id,
            player_name=str(identity["name"]),
        )
        game = self._present(state)
        records = self.store.achievement_unlocks()
        game["new_achievements"] = [
            {
                **public_achievement_definition(definition),
                **records[str(definition["id"])],
                "unlocked": True,
            }
            for definition in self.achievement_definitions
            if str(definition["id"]) in fresh_ids
        ]
        return game

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
        preset_id: str | None = None,
        monster_species_id: str | None = None,
    ) -> dict[str, Any]:
        preset: dict[str, Any] | None = None
        if preset_id:
            preset = next((
                dict(row)
                for row in self.definitions.systems.get("quick_start_presets", [])
                if str(row.get("id")) == preset_id and bool(row.get("enabled", True))
            ), None)
            if preset is None:
                raise ValueError("未知或未开放的快速开始预设")
            name = name.strip() or str(preset["name"])
            starting_age = int(preset.get("age", starting_age))
            race = str(preset.get("race", race))
            spirit_root = str(preset.get("spirit_root", spirit_root))
            path = str(preset.get("path", path))
            start_world = str(preset.get("world", start_world))
        elif start_world not in self.definitions.start_worlds.get(path, ()):
            raise ValueError("该修行道统无法从所选界面开局")
        if path == "monster" and preset is None:
            race = "monster"
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
        if path == "monster" and monster_species_id is not None:
            species_id = str(monster_species_id)
            events = [
                *events,
                *self.commands.execute(
                    state, ConfigureMonsterBloodline(
                        str(state.controlled_entity_id), species_id
                    )
                ),
            ]
        if preset is not None:
            actor_id = str(state.controlled_entity_id)
            realm = self.definitions.realms[int(preset["realm_index"])]
            layer = int(preset.get("layer", 1))
            cultivation = state.entities.require(actor_id, CULTIVATION)
            cultivation.update({
                "realm_id": realm.id,
                "layer": layer,
                "additional_roots": list(map(str, preset.get("additional_roots", []))),
                "opportunity": round(
                    realm.opportunity_base * (1 + 0.12 * (layer - 1))
                    * float(preset.get("opportunity_fraction", 0.0)),
                    4,
                ),
                "bottleneck": None,
            })
            state.entities.put(actor_id, CULTIVATION, cultivation)

            practice = state.entities.require(actor_id, PRACTICE)
            main_id = str(preset.get("main_technique", "")) or None
            support_id = str(preset.get("support_technique", "")) or None
            combat_ids = list(map(str, preset.get("combat_techniques", [])))
            known = list(dict.fromkeys(filter(None, [
                main_id, support_id, *combat_ids,
            ])))
            practice.update({
                "known_techniques": known,
                "main_technique_id": main_id,
                "support_technique_id": support_id,
                "combat_technique_ids": combat_ids,
            })
            state.entities.put(actor_id, PRACTICE, practice)

            story = state.entities.require(actor_id, STORY_STATE)
            story["flags"] = list(map(str, preset.get("story_flags", [])))
            attributes = dict(story.get("attributes", {}))
            for key in ("karma", "fame", "sha_qi"):
                attributes[key] = float(preset.get(key, 0.0))
            story["attributes"] = attributes
            state.entities.put(actor_id, STORY_STATE, story)

            inventory = state.entities.require(actor_id, INVENTORY)
            inventory["items"] = {
                str(row["id"]): int(row.get("quantity", 1))
                for row in preset.get("inventory", [])
                if str(row.get("id", "")) in self.definitions.items
            }
            inventory["reserved"] = {}
            state.entities.put(actor_id, INVENTORY, inventory)

            life = state.entities.require(actor_id, LIFE)
            if path == "ghost" or realm.lifespan is None:
                life["lifespan"] = None
            else:
                lifespan = int(realm.lifespan[1])
                if path == "monster":
                    lifespan *= 3
                life["lifespan"] = max(starting_age + 1, lifespan)
            state.entities.put(actor_id, LIFE, life)
            state.scheduler.cancel(lambda scheduled: (
                scheduled.event_type == LIFESPAN_DUE
                and str(scheduled.payload.get("entity_id", "")) == actor_id
            ))
            if life["lifespan"] is not None:
                state.scheduler.schedule(
                    due_year=int(life["birth_year"]) + int(life["lifespan"]),
                    event_type=LIFESPAN_DUE,
                    source="character",
                    scope=EventScope.entity(actor_id),
                    payload={"entity_id": actor_id},
                )
            ghost_soul = state.entities.get(actor_id, "dlc.ghost.soul")
            if ghost_soul is not None:
                ghost_soul["historical_peak"] = {"realm_id": realm.id, "layer": layer}
                state.entities.put(actor_id, "dlc.ghost.soul", ghost_soul)
        reconcile_extension_state(state, self.definitions)
        reconcile_ghost_state(state, self.definitions)
        reconcile_monster_state(state, self.definitions)
        reconcile_celestial_state(state, self.definitions)
        reconcile_intrigue_state(state, self.definitions)
        reconcile_presentation_state(state)
        reconcile_action_runtime(state)
        reconcile_story_state(state)
        reconcile_advanced_cultivation(state, self.definitions)
        reconcile_world_state(state)
        reconcile_trial_state(state, self.definitions)
        reconcile_asset_ledger(state)
        reconcile_production_state(state)
        reconcile_auction_state(state)
        reconcile_artifact_state(state)
        reconcile_relationship_state(state)
        reconcile_family_state(state)
        reconcile_npc_lifecycle(state)
        reconcile_concubine_state(state)
        reconcile_demonic_state(state)
        reconcile_war_state(state)
        events = [*events, *self._ensure_current_market(state)]
        self.invariants.validate(state)
        player = character_view(state)
        self.store.create(state, events, player_name=player["name"])
        return self._present_with_achievements(state)

    def execute(self, game_id: str, command: object) -> CommandExecution:
        state = self.store.load(game_id)
        expected_revision = state.revision
        content_events = self.commands.execute(state, EnsureWorldCharacters())
        roster_events = self.commands.execute(state, EnsureFactionRosters())
        reconcile_extension_state(state, self.definitions)
        reconcile_ghost_state(state, self.definitions)
        reconcile_monster_state(state, self.definitions)
        reconcile_celestial_state(state, self.definitions)
        reconcile_intrigue_state(state, self.definitions)
        reconcile_presentation_state(state)
        reconcile_action_runtime(state)
        reconcile_story_state(state)
        story_repair_events = (
            self.commands.execute(
                state, RepairPendingStoryEvent(str(state.controlled_entity_id))
            )
            if pending_story_needs_repair(state, self.definitions) else []
        )
        reconcile_advanced_cultivation(state, self.definitions)
        reconcile_world_state(state)
        reconcile_trial_state(state, self.definitions)
        reconcile_asset_ledger(state)
        reconcile_production_state(state)
        reconcile_auction_state(state)
        reconcile_artifact_state(state)
        reconcile_relationship_state(state)
        reconcile_family_state(state)
        reconcile_npc_lifecycle(state)
        reconcile_concubine_state(state)
        reconcile_demonic_state(state)
        reconcile_war_state(state)
        market_events = self._ensure_current_market(state)
        self.invariants.validate(state)
        events = [
            *content_events,
            *roster_events,
            *story_repair_events,
            *market_events,
            *self.commands.execute(state, command),
        ]
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
            game=self._present_with_achievements(state),
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

    def end_relationship(
        self, game_id: str, kind: str, target_id: str = "",
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        normalized = {
            "companion": "dao_companion",
            "dao_companion": "dao_companion",
            "friend": "friend",
            "master": "master_disciple",
            "disciple": "master_disciple",
            "master_disciple": "master_disciple",
            "concubine": "concubine",
        }.get(kind, kind)
        candidates = []
        for edge in state.relations.involving(actor_id):
            if not edge.active or edge.kind != normalized:
                continue
            other_id = edge.target_id if edge.source_id == actor_id else edge.source_id
            if target_id and other_id != target_id:
                continue
            if kind == "master" and not (
                edge.kind == "master_disciple" and edge.target_id == actor_id
            ):
                continue
            if kind == "disciple" and not (
                edge.kind == "master_disciple" and edge.source_id == actor_id
            ):
                continue
            candidates.append(edge)
        if len(candidates) != 1:
            raise ValueError("无法唯一确定要结束的关系")
        return self.execute(
            game_id, EndRelationship(actor_id, candidates[0].relation_id)
        )

    def request_mentorship(
        self, game_id: str, target_id: str, role: str,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, RequestMentorship(actor_id, target_id, role))

    def manage_faction_relationship(
        self, game_id: str, target_id: str, role: str,
    ) -> CommandExecution:
        return self.request_mentorship(game_id, target_id, role)

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

    def create_faction(self, game_id: str, name: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, FoundFaction(actor_id, name))

    def join_faction(self, game_id: str, faction_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, JoinFaction(actor_id, faction_id))

    def leave_faction(self, game_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, LeaveFaction(actor_id))

    def arrange_faction_succession(self, game_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, ArrangeFactionSuccession(actor_id))

    def dispatch_faction_member(self, game_id: str, target: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, DispatchFactionMember(actor_id, target))

    def dispatch_disciple(self, game_id: str, target: str) -> CommandExecution:
        return self.dispatch_faction_member(game_id, target)

    def intercept_faction_member(
        self, game_id: str, target_id: str,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, InterceptFactionMember(actor_id, target_id))

    def intercept_faction_npc(
        self, game_id: str, target_id: str,
    ) -> CommandExecution:
        return self.intercept_faction_member(game_id, target_id)

    def begin_relationship_capture(
        self, game_id: str, kind: str, target_id: str = "",
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, BeginRelationshipCapture(actor_id, kind, target_id))

    def propose_diplomacy(
        self, game_id: str, kind: str, target_id: str, status: str,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        normalized = "faction" if kind in {"faction", "sect"} else kind
        return self.execute(
            game_id, ProposeDiplomacy(actor_id, normalized, target_id, status)
        )

    def propose_race_diplomacy(
        self, game_id: str, target_id: str, status: str,
    ) -> CommandExecution:
        return self.propose_diplomacy(game_id, "race", target_id, status)

    def propose_sect_diplomacy(
        self, game_id: str, target_id: str, status: str,
    ) -> CommandExecution:
        return self.propose_diplomacy(game_id, "faction", target_id, status)

    def transfer_vassal_personnel(
        self, game_id: str, kind: str, target_id: str, character_id: str,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        normalized = "faction" if kind in {"faction", "sect"} else kind
        return self.execute(
            game_id,
            TransferVassalPersonnel(actor_id, normalized, target_id, character_id),
        )

    def manage_party(
        self, game_id: str, target_id: str, action: str,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, ManageParty(actor_id, target_id, action))

    def war_action(
        self, game_id: str, war_id: str, action: str, *, ally_id: str = "",
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, WarAction(actor_id, war_id, action, ally_id))

    def war_peace(
        self,
        game_id: str,
        war_id: str,
        term: str = "white_peace",
        *,
        target_id: str = "",
        target_power_id: str = "",
        third_party_id: str = "",
        third_status: str = "neutral",
        concede: bool = False,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id,
            WarPeace(
                actor_id, war_id, term, target_id, target_power_id,
                third_party_id, third_status, concede,
            ),
        )

    def issue_bounty(
        self, game_id: str, target_id: str, authority: str = "",
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, IssueBounty(actor_id, target_id, authority))

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

    def equip_known_technique(
        self, game_id: str, technique_id: str, slot: str,
    ) -> CommandExecution:
        if slot in {"body", "divine_sense", "transformation"}:
            return self.equip_special_technique(game_id, technique_id, slot)
        if slot not in {"main", "support", "combat"}:
            raise ValueError("未知功法槽位")
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, EquipMainTechnique(actor_id, technique_id, slot))

    def imprison_character(
        self,
        game_id: str,
        captor_id: str,
        years: int,
        *,
        name: str = "势力大牢",
        facility: str = "world_prison",
        hostility: float = 0.0,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, EnterImprisonment(
            actor_id, captor_id, years, name, facility, hostility
        ))

    def prison_action(self, game_id: str, action: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, PrisonAction(actor_id, action))

    def captive_action(
        self, game_id: str, target_id: str, action: str,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, CaptiveAction(actor_id, target_id, action))

    def craft_mechanical_puppet(self, game_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, CraftMechanicalPuppet(actor_id))

    def puppet_action(
        self, game_id: str, puppet_id: str, action: str,
        content_id: str = "",
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id, PuppetAction(actor_id, puppet_id, action, content_id)
        )

    def refine_foreign_souls(
        self, game_id: str, *, secluded: bool = False,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, RefineForeignSoul(actor_id, secluded))

    def secluded_refine_foreign_souls(
        self, game_id: str,
    ) -> CommandExecution:
        return self.refine_foreign_souls(game_id, secluded=True)

    def post_battle_possess(
        self, game_id: str, target_id: str,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, PostBattlePossession(actor_id, target_id))

    def prepare_ghost_reincarnation(self, game_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, PrepareGhostReincarnation(actor_id))

    def reincarnate_ghost(self, game_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, ReincarnateGhost(actor_id))

    def ghost_parade_action(
        self, game_id: str, action: str, soul_id: str = "",
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, GhostParadeAction(actor_id, action, soul_id))

    def ghost_soul_action(
        self, game_id: str, soul_id: str, action: str, slot: str = "",
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, GhostSoulAction(actor_id, soul_id, action, slot))

    def ghost_attachment_action(
        self, game_id: str, action: str, item_id: str = "",
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, GhostAttachmentAction(actor_id, action, item_id))

    def ghost_constraint_action(
        self, game_id: str, action: str,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, GhostConstraintAction(actor_id, action))

    def leave_possessed_body(self, game_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, LeavePossessedBody(actor_id))

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

    def batch_absorb_transformation_material(
        self, game_id: str, item_id: str, mode: str = "direct",
        stat_id: str = "",
    ) -> CommandExecution:
        return self.absorb_transformation_material(
            game_id, item_id, mode=mode, stat_id=stat_id, batch=True,
        )

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
        if not invited_ids:
            invited_ids = party_crossing_ids(state, actor_id)
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
        if not invited_ids:
            invited_ids = party_crossing_ids(state, actor_id)
        return self.execute(
            game_id, BeginAscensionTrial(actor_id, destination_world_id, invited_ids)
        )

    def begin_spirit_crossing(self, game_id: str) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id,
            BeginSpiritCrossing(actor_id, party_crossing_ids(state, actor_id)),
        )

    def spend_wangsheng(
        self, game_id: str, *, all_available: bool = False,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        uses = 1
        if all_available:
            soul = state.entities.get(actor_id, GHOST_SOUL) or {}
            unit_cost = max(
                1,
                int(self.definitions.systems.get("ghost_cultivation", {}).get(
                    "wangsheng_cost", 2
                )),
            )
            uses = int(soul.get("wangsheng", 0)) // unit_cost
            if uses <= 0:
                raise ValueError("往生不足")
        return self.execute(game_id, SpendWangsheng(actor_id, uses))

    def evolve_monster(
        self, game_id: str, evolution_id: str,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, EvolveMonster(actor_id, evolution_id))

    def prepare_custom_lineage(
        self, game_id: str, evolution_id: str,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, PrepareCustomLineage(actor_id, evolution_id))

    def confirm_custom_lineage(
        self, game_id: str, evolution_id: str, name: str,
        rules: tuple[dict[str, Any], ...],
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id, ConfirmCustomLineage(actor_id, evolution_id, name, rules)
        )

    def refresh_market(self, game_id: str, *, force: bool = False) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, RefreshMarket(actor_id=actor_id, force=force))

    def toggle_market_offer_lock(
        self, game_id: str, offer_id: str,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, ToggleMarketOfferLock(actor_id, offer_id))

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
        booster_id: str = "", *, mp_amount: float | None = None,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        if mp_amount is not None:
            maximum = float(combat_snapshot(
                state, self.definitions, actor_id
            )["max_mp"])
            mp_ratio = float(mp_amount) / max(1.0, maximum)
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
        preview = preview_crafting_view(
            state, self.definitions, actor_id, dict(payload)
        )
        game = self._present(state)
        game["crafting"]["last_preview"] = preview
        return CommandExecution(game=game, events=())

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
        preview = preview_formation_view(
            state, self.definitions, actor_id, dict(payload)
        )
        game = self._present(state)
        game["formation_system"]["last_preview"] = preview
        return CommandExecution(game=game, events=())

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

    def resolve_heavenly_election(
        self, game_id: str, method: str = "none", pledge_id: str = "",
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, ResolveHeavenlyElection(actor_id, method, pledge_id))

    def heavenly_court_action(
        self, game_id: str, action: str, target_id: str = "",
        enact: bool | None = None, influence_spend: int = 0,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id,
            HeavenlyCourtAction(actor_id, action, target_id, enact, influence_spend),
        )

    def intrigue_personnel_action(
        self,
        game_id: str,
        kind: str,
        action: str,
        member_id: str,
        position_id: str = "",
        years: int = 1,
        reason: str = "",
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id,
            IntriguePersonnelAction(
                actor_id, kind, action, member_id, position_id, years, reason,
            ),
        )

    def intrigue_guest_action(
        self, game_id: str, kind: str, action: str, target_id: str = "",
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(game_id, IntrigueGuestAction(actor_id, kind, action, target_id))

    def intrigue_propose_resolution(
        self, game_id: str, kind: str, resolution_type: str,
        target_id: str = "", *, player_vote: bool = True,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id,
            IntrigueResolutionAction(
                actor_id, kind, resolution_type, target_id, player_vote,
            ),
        )

    def intrigue_recruitment_action(
        self, game_id: str, action: str, *,
        filters: dict[str, Any] | None = None,
        candidate_ids: tuple[str, ...] = (),
        player_vote: bool = True,
    ) -> CommandExecution:
        state = self.store.load(game_id)
        actor_id = state.controlled_entity_id
        if actor_id is None:
            raise ValueError("游戏尚未初始化")
        return self.execute(
            game_id,
            IntrigueRecruitmentAction(
                actor_id, action, filters, candidate_ids, player_vote,
            ),
        )

    def get_game(self, game_id: str) -> dict[str, Any]:
        state = self.store.load(game_id)
        expected_revision = state.revision
        content_events = self.commands.execute(state, EnsureWorldCharacters())
        roster_events = self.commands.execute(state, EnsureFactionRosters())
        reconcile_extension_state(state, self.definitions)
        reconcile_ghost_state(state, self.definitions)
        reconcile_monster_state(state, self.definitions)
        reconcile_celestial_state(state, self.definitions)
        reconcile_intrigue_state(state, self.definitions)
        reconcile_presentation_state(state)
        reconcile_action_runtime(state)
        reconcile_story_state(state)
        story_repair_events = (
            self.commands.execute(
                state, RepairPendingStoryEvent(str(state.controlled_entity_id))
            )
            if pending_story_needs_repair(state, self.definitions) else []
        )
        reconcile_advanced_cultivation(state, self.definitions)
        reconcile_world_state(state)
        reconcile_trial_state(state, self.definitions)
        reconcile_asset_ledger(state)
        reconcile_production_state(state)
        reconcile_auction_state(state)
        reconcile_artifact_state(state)
        reconcile_relationship_state(state)
        reconcile_family_state(state)
        reconcile_npc_lifecycle(state)
        reconcile_concubine_state(state)
        reconcile_demonic_state(state)
        reconcile_war_state(state)
        market_events = self._ensure_current_market(state)
        self.invariants.validate(state)
        events = [
            *content_events, *roster_events, *story_repair_events, *market_events
        ]
        if events:
            state.updated_at = _now_iso()
            player = character_view(state)
            self.store.save(
                state,
                events,
                player_name=player["name"],
                expected_revision=expected_revision,
            )
        return self._present_with_achievements(state)

    def list_games(self) -> list[dict[str, Any]]:
        return self.store.list_games()

    def event_journal(self, game_id: str, *, after_sequence: int = 0) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self.store.load_events(game_id, after_sequence=after_sequence)]

    def _character_projection(
        self, state: WorldState, entity_id: str, *, observer_id: str,
    ) -> dict[str, Any]:
        character = character_view(state, entity_id)
        cultivation = cultivation_view(state, self.definitions, entity_id)
        practice = state.entities.require(entity_id, PRACTICE)
        location = state.entities.require(entity_id, LOCATION)
        snapshot = combat_snapshot(state, self.definitions, entity_id)
        identity = state.entities.require(entity_id, IDENTITY)
        world_profile = state.entities.get(entity_id, WORLD_NPC_PROFILE) or {}
        faction_profile = state.entities.get(entity_id, FACTION_NPC) or {}
        actor_cultivation = state.entities.require(observer_id, CULTIVATION)
        actor_rank = (
            self.definitions.realm_index(str(actor_cultivation["realm_id"])),
            int(actor_cultivation["layer"]),
        )
        target_rank = (int(cultivation["realm_index"]), int(cultivation["layer"]))
        involved = [
            edge for edge in state.relations.involving(observer_id)
            if entity_id in {edge.source_id, edge.target_id}
        ]
        social = [
            edge for edge in involved
            if edge.kind in {"friend", "dao_companion", "master_disciple", "concubine"}
        ]
        social_kinds = {edge.kind for edge in social}
        party_edge = next((
            edge for edge in state.relations.find(
                source_id=observer_id, kind=PARTY_MEMBER
            ) if edge.target_id == entity_id
        ), None)
        party_count = len(state.relations.find(
            source_id=observer_id, kind=PARTY_MEMBER
        ))
        relationship_rules = dict(self.definitions.systems.get("relationship", {}))
        party_rules = dict(self.definitions.systems.get("party", {}))
        affinity = relationship_affinity(state, entity_id, observer_id)
        if affinity >= float(relationship_rules.get("positive_affinity_threshold", 30)):
            attitude = "亲近"
        elif affinity >= float(relationship_rules.get("friend_affinity_required", 15)):
            attitude = "友善"
        elif affinity <= float(relationship_rules.get("hostile_affinity_threshold", -25)):
            attitude = "敌视"
        elif affinity < 0:
            attitude = "冷淡"
        else:
            attitude = "平常"
        actor_location = state.entities.require(observer_id, LOCATION)
        same_world = location.get("world_id") == actor_location.get("world_id")
        actor_profile = state.entities.get(observer_id, SOCIAL_PROFILE) or {}
        attempts = set(map(str, actor_profile.get("attempts", [])))
        actor_has_master = bool(state.relations.find(
            target_id=observer_id, kind="master_disciple"
        ))
        actor_disciple_count = len(state.relations.find(
            source_id=observer_id, kind="master_disciple"
        ))
        actor_has_companion = bool(state.relations.involving(
            observer_id, kind="dao_companion"
        ))
        actor_membership = next(iter(state.relations.find(
            source_id=observer_id, kind=MEMBERSHIP
        )), None)
        target_membership = next(iter(state.relations.find(
            source_id=entity_id, kind=MEMBERSHIP
        )), None)
        target_faction = (
            state.entities.get(target_membership.target_id, "faction.profile")
            if target_membership else None
        )
        same_faction = bool(
            actor_membership and target_membership
            and actor_membership.target_id == target_membership.target_id
        )
        controlled_faction_id = (
            actor_membership.target_id
            if actor_membership
            and (state.entities.get(
                actor_membership.target_id, FACTION_GOVERNANCE
            ) or {}).get("controller_id") == observer_id
            else None
        )
        target_is_controlled_guest = bool(
            controlled_faction_id
            and state.relations.find(
                source_id=controlled_faction_id,
                target_id=entity_id,
                kind=INTRIGUE_GUEST,
            )
        )
        main_id = practice.get("main_technique_id")
        world_id = str(location["world_id"])
        world = self.definitions.worlds[world_id]
        location_id = str(location["location_id"])
        title = str(
            world_profile.get("title")
            or faction_profile.get("title")
            or "云游修士"
        )
        alive = bool(character["alive"])
        unrelated = not social
        can_interact = bool(alive and same_world and entity_id != observer_id)
        max_disciples = int(relationship_rules.get("max_disciples", 8))
        return {
            **character,
            **cultivation,
            "external_id": identity.get("external_id"),
            "title": title,
            "gender_name": {"male": "男", "female": "女"}.get(
                str(character["gender"]), "性别未明"
            ),
            "race_name": str(
                self.definitions.races.get(str(character["race"]), {}).get(
                    "name", character["race"]
                )
            ),
            "world": world_id,
            "world_name": world.name,
            "location": location_id,
            "location_name": world.locations[location_id].name,
            "perceived_alive": alive and same_world,
            "status": "存活" if alive and same_world else (
                character.get("death_reason") or "不在当前界面，生死不明"
            ),
            "combat_power": round(float(snapshot["power"]), 1) if same_world else None,
            "affinity": round(affinity, 1),
            "attitude": attitude,
            "main_technique_id": main_id,
            "main_technique_name": (
                self.definitions.techniques[str(main_id)].name
                if main_id in self.definitions.techniques else "尚无主修功法"
            ),
            "techniques": list(map(str, practice.get("known_techniques", []))),
            "source": "world" if world_profile else "faction" if target_membership else "event",
            "faction_id": target_membership.target_id if target_membership else None,
            "faction_external_id": (
                target_faction.get("external_id") if target_faction else None
            ),
            "faction_name": target_faction.get("name") if target_faction else None,
            "treasure_name": (
                self.definitions.items[str(world_profile.get("treasure_item_id"))].name
                if str(world_profile.get("treasure_item_id", "")) in self.definitions.items
                else None
            ),
            "formation": None,
            "wounds": 0,
            "in_party": party_edge is not None,
            "can_invite_party": bool(
                can_interact and party_edge is None
                and party_count < int(party_rules.get("max_companions", 2))
            ),
            "can_propose_companion": bool(
                can_interact and not actor_has_companion
                and "master_disciple" not in social_kinds
                and "concubine" not in social_kinds
            ),
            "can_befriend": bool(
                can_interact and unrelated
                and affinity >= float(relationship_rules.get(
                    "friend_affinity_required", 15
                ))
            ),
            "can_intercept": bool(can_interact and same_faction),
            "can_request_master": bool(
                can_interact and same_faction and unrelated and not actor_has_master
                and target_rank > actor_rank
                and f"master:{entity_id}" not in attempts
            ),
            "can_accept_disciple": bool(
                can_interact and same_faction and unrelated
                and actor_disciple_count < max_disciples
                and target_rank < actor_rank
                and f"disciple:{entity_id}" not in attempts
            ),
            "can_recruit_concubine": bool(
                can_interact and character["gender"] == "female"
                and target_rank <= actor_rank and "concubine" not in social_kinds
            ),
            "can_invite_faction": bool(
                can_interact and actor_membership and target_membership is None
            ),
            "can_invite_guest": bool(
                can_interact and controlled_faction_id
                and not target_is_controlled_guest
                and not (
                    target_membership
                    and target_membership.target_id == controlled_faction_id
                )
                and (affinity >= 30 or "friend" in social_kinds)
            ),
            "is_master": any(
                edge.kind == "master_disciple" and edge.source_id == entity_id
                for edge in social
            ),
            "is_disciple": any(
                edge.kind == "master_disciple" and edge.target_id == entity_id
                for edge in social
            ),
            "is_friend": "friend" in social_kinds,
            "same_cultivation": bool(
                cultivation.get("realm_id") == actor_cultivation.get("realm_id")
                and cultivation.get("path") == actor_cultivation.get("path")
            ),
            "breakthrough_bonus": float(
                relationship_rules.get("companion_breakthrough_bonus", 0.05)
            ),
        }

    def _character_catalog(self, state: WorldState) -> list[dict[str, Any]]:
        actor_id = state.controlled_entity_id
        if actor_id is None:
            return []
        world_id = state.entities.require(actor_id, LOCATION)["world_id"]
        rows: list[dict[str, Any]] = []
        for entity_id in state.entities.with_component(IDENTITY):
            if entity_id == actor_id:
                continue
            life = state.entities.get(entity_id, LIFE) or {}
            location = state.entities.get(entity_id, LOCATION) or {}
            if not bool(life.get("alive")) or location.get("world_id") != world_id:
                continue
            rows.append(self._character_projection(
                state, entity_id, observer_id=actor_id
            ))
        return sorted(
            rows,
            key=lambda row: (-row["realm_index"], -row["layer"], row["name"]),
        )

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
        actor_id = str(state.controlled_entity_id)
        characters = self._character_catalog(state)
        projections = {str(row["id"]): row for row in characters}

        def projected(entity_id: str) -> dict[str, Any]:
            if entity_id not in projections:
                projections[entity_id] = self._character_projection(
                    state, entity_id, observer_id=actor_id
                )
            return projections[entity_id]

        relationships = relationship_view(state, self.definitions)
        for row in relationships:
            other_id = str(dict(row.get("other", {})).get("id", ""))
            if other_id:
                row["other"] = projected(other_id)
        disciple_requests = disciple_request_view(state)
        for row in disciple_requests:
            requester_id = str(dict(row.get("requester", {})).get("id", ""))
            if requester_id:
                row["requester"] = projected(requester_id)
        faction = faction_view(state, self.definitions)
        if faction is not None:
            faction_id = str(faction["id"])
            governance = state.entities.require(faction_id, FACTION_GOVERNANCE)
            actor_membership = next(
                edge for edge in state.relations.find(
                    source_id=actor_id, target_id=faction_id, kind=MEMBERSHIP
                )
            )
            roster = []
            for entry in faction.get("roster", []):
                entity_id = str(entry["id"])
                roster.append({
                    **projected(entity_id), **entry,
                    "is_player": entity_id == actor_id,
                })
            roster.sort(key=lambda row: (
                -int(row["realm_index"]), -int(row["layer"]), str(row["name"])
            ))
            actor_realm = int(cultivation["realm_index"])
            creator_id = governance.get("creator_id")
            controller_id = governance.get("controller_id")
            successor_id = governance.get("designated_successor_id")
            successor_name = None
            if successor_id and state.entities.exists(str(successor_id)):
                successor_name = str(
                    state.entities.require(str(successor_id), IDENTITY)["name"]
                )
            eligible_successors = [
                row for row in roster
                if not row["is_player"] and bool(row.get("alive", True))
            ]
            historical_members = {
                edge.source_id
                for edge in state.relations.find(
                    target_id=faction_id, kind=MEMBERSHIP, active_only=False
                )
                if edge.source_id != actor_id
            }
            fallen_count = sum(
                not bool((state.entities.get(entity_id, LIFE) or {}).get("alive"))
                or (state.entities.get(entity_id, LOCATION) or {}).get("world_id")
                != current_world["world_id"]
                for entity_id in historical_members
            )
            founded_by_player = creator_id == actor_id
            succession_arranged = bool(successor_id)
            faction_rules = dict(
                self.definitions.systems.get("player_faction", {})
            )
            faction = {
                **faction,
                "member": True,
                "world": current_world["world_id"],
                "world_name": current_world["world_name"],
                "description": next((
                    definition.description
                    for definition in self.definitions.factions.values()
                    if definition.id == faction.get("external_id")
                ), "修行势力"),
                "join_age": next((
                    edge.created_year for edge in state.relations.find(
                        source_id=actor_id, kind=MEMBERSHIP
                    ) if edge.target_id == faction.get("id")
                ), state.clock.year),
                "role": (
                    "开山祖师" if founded_by_player
                    else "宗门执掌" if controller_id == actor_id
                    else "议事长老" if actor_realm >= 4
                    else "宗门弟子"
                ),
                "fixed_reward_unlocked": actor_realm >= 4,
                "can_dispatch": actor_realm >= 4,
                "dispatch_used": (
                    actor_membership.metadata.get("last_dispatch_year")
                    == state.clock.year
                ),
                "dispatch_cost": int(self.definitions.systems.get(
                    "factions", {}
                ).get("disciple_dispatch_cost", 0)),
                "dispatch_success": float(self.definitions.systems.get(
                    "factions", {}
                ).get("disciple_dispatch_success", 0.0)),
                "can_leave": True,
                "can_arrange_succession": bool(
                    founded_by_player and controller_id == actor_id
                    and eligible_successors
                ),
                "founded_by_player": founded_by_player,
                "succession_plan": {
                    "arranged": succession_arranged,
                    "successor_id": successor_id,
                    "successor_name": successor_name,
                },
                "pressure": int(governance.get("pressure", 0)),
                "pressure_limit": int(faction_rules.get("pressure_limit", 3)),
                "fallen_count": fallen_count,
                "has_diplomatic_voice": bool(faction.get("has_voice")),
                "roster": roster,
            }
        lineage_race = str(player["race"])
        allegiance_race = str(
            (faction.get("allegiance_race") or lineage_race)
            if faction is not None else lineage_race
        )
        return {
            "format": "cultivation-life-v2",
            "id": state.game_id,
            "seed": state.seed,
            "revision": state.revision,
            "schema_version": state.schema_version,
            "clock": {"year": state.clock.year},
            "player": {
                **player, "cultivation": cultivation, **advanced_cultivation,
                "lineage_race": lineage_race,
                "allegiance_race": allegiance_race,
            },
            "world": current_world,
            "relationships": relationships,
            "characters": characters,
            "disciple_requests": disciple_requests,
            "faction": faction,
            "governance": governance_view(state),
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
            "party": party_view(state, self.definitions),
            "demonic_system": demonic_view(state, self.definitions),
            "ghost_system": ghost_view(state, self.definitions),
            "monster_system": monster_view(state, self.definitions),
            "heavenly_court": celestial_view(state, self.definitions),
            "intrigue_system": intrigue_view(state, self.definitions),
            "war_system": war_view(state, self.definitions),
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
                "spirit_crossing": story["spirit_crossing"],
            },
            "breakthrough": breakthrough_view(state, self.definitions),
            "action": action,
            "trial": trial_view(state),
            "tribulation": tribulation_view(state),
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
