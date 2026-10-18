"""Explicit capabilities of the remaining character systems; no engine dependency."""
from __future__ import annotations
from dataclasses import dataclass
import random
from typing import Any, Callable, Protocol
from ...models import GameState, Player, SectNpc, SectState, HistoryRecord, Item
from ...ports import CommitPort, MapPort
from ..world_transition_schema import WorldTransitionPlan

class BuddhistGuardLoadPort(Protocol):
    def __call__(self, game_id: str) -> GameState: ...

@dataclass(frozen=True, slots=True)
class BuddhistGuardDependencies:
    _load: BuddhistGuardLoadPort


class BuddhistStateAdvanceBuddhistSocietyYearPort(Protocol):
    def __call__(self, game: GameState) -> None: ...

class BuddhistStateBuddhistBurdenPort(Protocol):
    def __call__(self, game: GameState) -> float: ...

class BuddhistStateBuddhistPermissionsPort(Protocol):
    def __call__(self, game: GameState) -> list[dict[str, Any]]: ...

class BuddhistStateEnsureBuddhistStatePort(Protocol):
    def __call__(self, game: GameState) -> None: ...

@dataclass(frozen=True, slots=True)
class BuddhistStateDependencies:
    _advance_buddhist_society_year: BuddhistStateAdvanceBuddhistSocietyYearPort
    _buddhist_burden: BuddhistStateBuddhistBurdenPort
    _buddhist_permissions: BuddhistStateBuddhistPermissionsPort
    _ensure_buddhist_state: BuddhistStateEnsureBuddhistStatePort
    _get_maps: Callable[[], MapPort]

    @property
    def maps(self) -> MapPort:
        return self._get_maps()


class ConcubineQueriesEnsureIntriguePersonalityPort(Protocol):
    def __call__(self, game: GameState, npc: SectNpc) -> dict[str, Any]: ...

class ConcubineQueriesFindNpcPort(Protocol):
    def __call__(self, game: GameState, npc_id: str) -> SectNpc | None: ...

class ConcubineQueriesIntrigueEnabledPort(Protocol):
    def __call__(self) -> bool: ...

class ConcubineQueriesNpcPowerPort(Protocol):
    def __call__(self, npc: SectNpc) -> float: ...

class ConcubineQueriesNpcRealmNamePort(Protocol):
    def __call__(self, npc: SectNpc) -> str: ...

class ConcubineQueriesNpcRootNamePort(Protocol):
    def __call__(self, root_id: str) -> str: ...

class ConcubineQueriesOwnerPersonalityPort(Protocol):
    def __call__(self, game: GameState, owner: SectNpc) -> dict[str, Any]: ...

class ConcubineQueriesPersonalityScorePort(Protocol):
    def __call__(self, personality: dict[str, Any], scores: dict[str, float], default: float=...) -> float: ...

class ConcubineQueriesPromoteCachedNpcPort(Protocol):
    def __call__(self, game: GameState, npc_id: str, reason: str) -> SectNpc | None: ...

class ConcubineQueriesRankPort(Protocol):
    def __call__(self, value: Player | SectNpc | dict[str, Any]) -> tuple[int, int]: ...

class ConcubineQueriesRelationByIdPort(Protocol):
    def __call__(self, player: Player, target_id: str) -> dict[str, Any] | None: ...

class ConcubineQueriesRelationshipProtectorsPort(Protocol):
    def __call__(self, game: GameState, enemy: SectNpc) -> list[dict[str, Any]]: ...

class ConcubineQueriesRevengeReadyPort(Protocol):
    def __call__(self, game: GameState, family: str, adversary_id: str) -> bool: ...

class ConcubineQueriesSectMembersPort(Protocol):
    def __call__(self, game: GameState, sect: SectState) -> list[SectNpc]: ...

class ConcubineQueriesStableGenderPort(Protocol):
    def __call__(self, identity: str, name: str=...) -> str: ...

@dataclass(frozen=True, slots=True)
class ConcubineQueriesDependencies:
    _ensure_intrigue_personality: ConcubineQueriesEnsureIntriguePersonalityPort
    _find_npc: ConcubineQueriesFindNpcPort
    _intrigue_enabled: ConcubineQueriesIntrigueEnabledPort
    _npc_power: ConcubineQueriesNpcPowerPort
    _npc_realm_name: ConcubineQueriesNpcRealmNamePort
    _npc_root_name: ConcubineQueriesNpcRootNamePort
    _owner_personality: ConcubineQueriesOwnerPersonalityPort
    _personality_score: ConcubineQueriesPersonalityScorePort
    _promote_cached_npc: ConcubineQueriesPromoteCachedNpcPort
    _rank: ConcubineQueriesRankPort
    _relation_by_id: ConcubineQueriesRelationByIdPort
    _relationship_protectors: ConcubineQueriesRelationshipProtectorsPort
    _revenge_ready: ConcubineQueriesRevengeReadyPort
    _sect_members: ConcubineQueriesSectMembersPort
    _stable_gender: ConcubineQueriesStableGenderPort


class DemonicActionsCompleteSoulRefinementPort(Protocol):
    def __call__(self, player: Player, soul: dict[str, Any]) -> None: ...

class DemonicActionsDemonicRulesPort(Protocol):
    def __call__(self) -> dict[str, Any]: ...

class DemonicActionsDevourPuppetPort(Protocol):
    def __call__(self, game: GameState, puppet: dict[str, Any]) -> tuple[str, str]: ...

class DemonicActionsGrantArtExperiencePort(Protocol):
    def __call__(self, player: Player, art_id: str, amount: float) -> None: ...

class DemonicActionsLoadPort(Protocol):
    def __call__(self, game_id: str) -> GameState: ...

class DemonicActionsPuppetTechniquePort(Protocol):
    def __call__(self, technique_id: str | None) -> Any: ...

class DemonicActionsSoulRefineGainPort(Protocol):
    def __call__(self, player: Player) -> float: ...

class DemonicActionsPresentPort(Protocol):
    def __call__(self, game: GameState) -> dict[str, Any]: ...

class DemonicActionsTrainOwnedPort(Protocol):
    def __call__(self, game_id: str, target_id: str, kind: str, axis: str, batches: int=...) -> dict[str, Any]: ...

@dataclass(frozen=True, slots=True)
class DemonicActionsDependencies:
    _complete_soul_refinement: DemonicActionsCompleteSoulRefinementPort
    _demonic_rules: DemonicActionsDemonicRulesPort
    _devour_puppet: DemonicActionsDevourPuppetPort
    _grant_art_experience: DemonicActionsGrantArtExperiencePort
    _load: DemonicActionsLoadPort
    _puppet_technique: DemonicActionsPuppetTechniquePort
    _soul_refine_gain: DemonicActionsSoulRefineGainPort
    present: DemonicActionsPresentPort
    _get_store: Callable[[], CommitPort]
    train_owned: DemonicActionsTrainOwnedPort

    @property
    def store(self) -> CommitPort:
        return self._get_store()


class DemonicCombatLivingPuppetPartyPowersPort(Protocol):
    def __call__(self, player: Player, game: GameState | None=...) -> list[float]: ...

class DemonicCombatPlayerIntrinsicCombatPowerPort(Protocol):
    def __call__(self, player: Player) -> float: ...

class DemonicCombatPublicPartyPort(Protocol):
    def __call__(self, game: GameState) -> list[dict[str, Any]]: ...

class DemonicCombatPuppetIntrinsicContributionPort(Protocol):
    def __call__(self, player: Player) -> float: ...

@dataclass(frozen=True, slots=True)
class DemonicCombatDependencies:
    _living_puppet_party_powers: DemonicCombatLivingPuppetPartyPowersPort
    _player_intrinsic_combat_power: DemonicCombatPlayerIntrinsicCombatPowerPort
    _public_party: DemonicCombatPublicPartyPort
    _puppet_intrinsic_contribution: DemonicCombatPuppetIntrinsicContributionPort


class DemonicGrowthAddOpportunityPort(Protocol):
    def __call__(self, player: Player, amount: float, regional_efficiencies: dict[str, float] | None=..., *, apply_efficiency: bool=...) -> float: ...

class DemonicGrowthDemonicRulesPort(Protocol):
    def __call__(self) -> dict[str, Any]: ...

class DemonicGrowthSoulRefineGainPort(Protocol):
    def __call__(self, player: Player) -> float: ...

@dataclass(frozen=True, slots=True)
class DemonicGrowthDependencies:
    _add_opportunity: DemonicGrowthAddOpportunityPort
    _demonic_rules: DemonicGrowthDemonicRulesPort
    _soul_refine_gain: DemonicGrowthSoulRefineGainPort


class DemonicPuppetRulesDemonicRulesPort(Protocol):
    def __call__(self) -> dict[str, Any]: ...

@dataclass(frozen=True, slots=True)
class DemonicPuppetRulesDependencies:
    _demonic_rules: DemonicPuppetRulesDemonicRulesPort


class DemonicViewDemonicRulesPort(Protocol):
    def __call__(self) -> dict[str, Any]: ...

class DemonicViewNpcRealmNamePort(Protocol):
    def __call__(self, npc: SectNpc) -> str: ...

class DemonicViewPuppetTechniquePort(Protocol):
    def __call__(self, technique_id: str | None) -> Any: ...

class DemonicViewSecludedRefiningYearsPort(Protocol):
    def __call__(self, player: Player) -> int: ...

class DemonicViewStableGenderPort(Protocol):
    def __call__(self, identity: str, name: str=...) -> str: ...

@dataclass(frozen=True, slots=True)
class DemonicViewDependencies:
    _demonic_rules: DemonicViewDemonicRulesPort
    _npc_realm_name: DemonicViewNpcRealmNamePort
    _puppet_technique: DemonicViewPuppetTechniquePort
    _secluded_refining_years: DemonicViewSecludedRefiningYearsPort
    _stable_gender: DemonicViewStableGenderPort


class FamilyActionsFamilyAssignOfficePort(Protocol):
    def __call__(self, game: GameState, npc: SectNpc, sect: SectState) -> None: ...

class FamilyActionsFamilyChildNpcPort(Protocol):
    def __call__(self, child: dict[str, Any]) -> SectNpc: ...

class FamilyActionsFamilyDecisionMemberPort(Protocol):
    def __call__(self, game: GameState, npc: SectNpc, sect: SectState) -> bool: ...

class FamilyActionsFamilyElitesPort(Protocol):
    def __call__(self, game: GameState, entity: SectState) -> list[tuple[int, int]]: ...

class FamilyActionsFamilyEquipmentPort(Protocol):
    def __call__(self, player: Player, item: Item) -> tuple[float, dict[str, Any] | None] | None: ...

class FamilyActionsFamilyInfusionPort(Protocol):
    def __call__(self, game: GameState, npc: SectNpc) -> dict[str, Any]: ...

class FamilyActionsFamilyIsKinPort(Protocol):
    def __call__(self, game: GameState, npc: SectNpc) -> bool: ...

class FamilyActionsFamilyLogPort(Protocol):
    def __call__(self, game: GameState, action: str, text: str, changes: dict[str, Any] | None=...) -> None: ...

class FamilyActionsFamilyRegisterChildrenPort(Protocol):
    def __call__(self, game: GameState) -> None: ...

class FamilyActionsFamilyRelationPort(Protocol):
    def __call__(self, game: GameState, other: SectState) -> dict[str, Any]: ...

class FamilyActionsFamilyTotalPowerPort(Protocol):
    def __call__(self, game: GameState, family: SectState) -> float: ...

class FamilyActionsFamilyWorldTierPort(Protocol):
    def __call__(self, world: str) -> int: ...

class FamilyActionsHasFamilyVoicePort(Protocol):
    def __call__(self, game: GameState) -> bool: ...

class FamilyActionsIntrigueEnabledPort(Protocol):
    def __call__(self) -> bool: ...

class FamilyActionsIntrigueIsImprisonedPort(Protocol):
    def __call__(self, game: GameState, npc_id: str) -> bool: ...

class FamilyActionsLoadPort(Protocol):
    def __call__(self, game_id: str) -> GameState: ...

class FamilyActionsNpcRealmNamePort(Protocol):
    def __call__(self, npc: SectNpc) -> str: ...

class FamilyActionsRandomNpcRootPort(Protocol):
    def __call__(self, realm_index: int, rng: random.Random) -> str: ...

class FamilyActionsStartWarPort(Protocol):
    def __call__(self, game: GameState, kind: str, attacker: str, defender: str, *, initiated_by_player: bool=..., prepare_supplies: bool=..., strategic_war_id: str=...) -> dict[str, Any]: ...

class FamilyActionsAssertGuixuOperationAllowedPort(Protocol):
    def __call__(self, game_id: str, operation: str) -> None: ...

class FamilyActionsPresentPort(Protocol):
    def __call__(self, game: GameState) -> dict[str, Any]: ...

@dataclass(frozen=True, slots=True)
class FamilyActionsDependencies:
    _family_assign_office: FamilyActionsFamilyAssignOfficePort
    _family_child_npc: FamilyActionsFamilyChildNpcPort
    _family_decision_member: FamilyActionsFamilyDecisionMemberPort
    _family_elites: FamilyActionsFamilyElitesPort
    _family_equipment: FamilyActionsFamilyEquipmentPort
    _family_infusion: FamilyActionsFamilyInfusionPort
    _family_is_kin: FamilyActionsFamilyIsKinPort
    _family_log: FamilyActionsFamilyLogPort
    _family_register_children: FamilyActionsFamilyRegisterChildrenPort
    _family_relation: FamilyActionsFamilyRelationPort
    _family_total_power: FamilyActionsFamilyTotalPowerPort
    _family_world_tier: FamilyActionsFamilyWorldTierPort
    _has_family_voice: FamilyActionsHasFamilyVoicePort
    _intrigue_enabled: FamilyActionsIntrigueEnabledPort
    _intrigue_is_imprisoned: FamilyActionsIntrigueIsImprisonedPort
    _load: FamilyActionsLoadPort
    _npc_realm_name: FamilyActionsNpcRealmNamePort
    _random_npc_root: FamilyActionsRandomNpcRootPort
    _start_war: FamilyActionsStartWarPort
    assert_guixu_operation_allowed: FamilyActionsAssertGuixuOperationAllowedPort
    _get_maps: Callable[[], MapPort]
    present: FamilyActionsPresentPort
    _get_store: Callable[[], CommitPort]

    @property
    def maps(self) -> MapPort:
        return self._get_maps()

    @property
    def store(self) -> CommitPort:
        return self._get_store()


class FamilySocietyActualPlayerRealmPort(Protocol):
    def __call__(self, player: Player) -> tuple[int, int]: ...

class FamilySocietyEnsureIntrigueFactionPort(Protocol):
    def __call__(self, game: GameState, kind: str, faction_id: str) -> dict[str, Any]: ...

class FamilySocietyFamilyChildNpcPort(Protocol):
    def __call__(self, child: dict[str, Any]) -> SectNpc: ...

class FamilySocietyFamilyDecisionMemberPort(Protocol):
    def __call__(self, game: GameState, npc: SectNpc, sect: SectState) -> bool: ...

class FamilySocietyFamilyDissolvePort(Protocol):
    def __call__(self, game: GameState, reason: str, absorber: SectState | None=...) -> None: ...

class FamilySocietyFamilyElitesPort(Protocol):
    def __call__(self, game: GameState, entity: SectState) -> list[tuple[int, int]]: ...

class FamilySocietyFamilyIsKinPort(Protocol):
    def __call__(self, game: GameState, npc: SectNpc) -> bool: ...

class FamilySocietyFamilyLogPort(Protocol):
    def __call__(self, game: GameState, action: str, text: str, changes: dict[str, Any] | None=...) -> None: ...

class FamilySocietyFamilyRelationPort(Protocol):
    def __call__(self, game: GameState, other: SectState) -> dict[str, Any]: ...

class FamilySocietyFamilyTotalPowerPort(Protocol):
    def __call__(self, game: GameState, family: SectState) -> float: ...

class FamilySocietyFamilyWorldTierPort(Protocol):
    def __call__(self, world: str) -> int: ...

class FamilySocietyFindNpcPort(Protocol):
    def __call__(self, game: GameState, npc_id: str) -> SectNpc | None: ...

class FamilySocietyGovernanceThresholdPort(Protocol):
    def __call__(self, world: str) -> int: ...

class FamilySocietyIntrigueDecisionThresholdPort(Protocol):
    def __call__(self, kind: str) -> int: ...

class FamilySocietyIntrigueEnabledPort(Protocol):
    def __call__(self) -> bool: ...

class FamilySocietyIntrigueHasDecisionAuthorityPort(Protocol):
    def __call__(self, game: GameState, kind: str, faction_id: str, member_id: str=...) -> bool: ...

class FamilySocietyIntrigueIsImprisonedPort(Protocol):
    def __call__(self, game: GameState, npc_id: str) -> bool: ...

class FamilySocietyIntriguePositionSpecsPort(Protocol):
    def __call__(self, kind: str) -> dict[str, dict[str, Any]]: ...

class FamilySocietyNpcPowerPort(Protocol):
    def __call__(self, npc: SectNpc) -> float: ...

class FamilySocietyNpcRootNamePort(Protocol):
    def __call__(self, root_id: str) -> str: ...

class FamilySocietySectMembersPort(Protocol):
    def __call__(self, game: GameState, sect: SectState) -> list[SectNpc]: ...

@dataclass(frozen=True, slots=True)
class FamilySocietyDependencies:
    _actual_player_realm: FamilySocietyActualPlayerRealmPort
    _ensure_intrigue_faction: FamilySocietyEnsureIntrigueFactionPort
    _family_child_npc: FamilySocietyFamilyChildNpcPort
    _family_decision_member: FamilySocietyFamilyDecisionMemberPort
    _family_dissolve: FamilySocietyFamilyDissolvePort
    _family_elites: FamilySocietyFamilyElitesPort
    _family_is_kin: FamilySocietyFamilyIsKinPort
    _family_log: FamilySocietyFamilyLogPort
    _family_relation: FamilySocietyFamilyRelationPort
    _family_total_power: FamilySocietyFamilyTotalPowerPort
    _family_world_tier: FamilySocietyFamilyWorldTierPort
    _find_npc: FamilySocietyFindNpcPort
    _governance_threshold: FamilySocietyGovernanceThresholdPort
    _intrigue_decision_threshold: FamilySocietyIntrigueDecisionThresholdPort
    _intrigue_enabled: FamilySocietyIntrigueEnabledPort
    _intrigue_has_decision_authority: FamilySocietyIntrigueHasDecisionAuthorityPort
    _intrigue_is_imprisoned: FamilySocietyIntrigueIsImprisonedPort
    _intrigue_position_specs: FamilySocietyIntriguePositionSpecsPort
    _npc_power: FamilySocietyNpcPowerPort
    _npc_root_name: FamilySocietyNpcRootNamePort
    _sect_members: FamilySocietySectMembersPort


class FamilyViewFamilyEquipmentPort(Protocol):
    def __call__(self, player: Player, item: Item) -> tuple[float, dict[str, Any] | None] | None: ...

class FamilyViewFamilyInfusionPort(Protocol):
    def __call__(self, game: GameState, npc: SectNpc) -> dict[str, Any]: ...

class FamilyViewFamilyIsKinPort(Protocol):
    def __call__(self, game: GameState, npc: SectNpc) -> bool: ...

class FamilyViewFamilyRelationPort(Protocol):
    def __call__(self, game: GameState, other: SectState) -> dict[str, Any]: ...

class FamilyViewFamilyTotalPowerPort(Protocol):
    def __call__(self, game: GameState, family: SectState) -> float: ...

class FamilyViewFamilyWorldTierPort(Protocol):
    def __call__(self, world: str) -> int: ...

class FamilyViewFindNpcPort(Protocol):
    def __call__(self, game: GameState, npc_id: str) -> SectNpc | None: ...

class FamilyViewHasFamilyVoicePort(Protocol):
    def __call__(self, game: GameState) -> bool: ...

class FamilyViewIntrigueEnabledPort(Protocol):
    def __call__(self) -> bool: ...

class FamilyViewIntrigueIsImprisonedPort(Protocol):
    def __call__(self, game: GameState, npc_id: str) -> bool: ...

class FamilyViewNpcPowerPort(Protocol):
    def __call__(self, npc: SectNpc) -> float: ...

@dataclass(frozen=True, slots=True)
class FamilyViewDependencies:
    _family_equipment: FamilyViewFamilyEquipmentPort
    _family_infusion: FamilyViewFamilyInfusionPort
    _family_is_kin: FamilyViewFamilyIsKinPort
    _family_relation: FamilyViewFamilyRelationPort
    _family_total_power: FamilyViewFamilyTotalPowerPort
    _family_world_tier: FamilyViewFamilyWorldTierPort
    _find_npc: FamilyViewFindNpcPort
    _has_family_voice: FamilyViewHasFamilyVoicePort
    _intrigue_enabled: FamilyViewIntrigueEnabledPort
    _intrigue_is_imprisoned: FamilyViewIntrigueIsImprisonedPort
    _npc_power: FamilyViewNpcPowerPort


class GhostActionsCombatPort(Protocol):
    def __call__(self, game: GameState, target: dict[str, Any], *, lethal: bool, rng: random.Random) -> tuple[str, str]: ...

class GhostActionsLoadPort(Protocol):
    def __call__(self, game_id: str) -> GameState: ...

class GhostActionsPresentPort(Protocol):
    def __call__(self, game: GameState) -> dict[str, Any]: ...

@dataclass(frozen=True, slots=True)
class GhostActionsDependencies:
    _combat: GhostActionsCombatPort
    _load: GhostActionsLoadPort
    present: GhostActionsPresentPort
    _get_store: Callable[[], CommitPort]

    @property
    def store(self) -> CommitPort:
        return self._get_store()


class GhostStateMonsterTravelMultiplierPort(Protocol):
    def __call__(self, player: Player, destination: str) -> float: ...

class GhostStatePublicGhostPhaseTwoPort(Protocol):
    def __call__(self, game: GameState) -> dict[str, Any]: ...

@dataclass(frozen=True, slots=True)
class GhostStateDependencies:
    _monster_travel_multiplier: GhostStateMonsterTravelMultiplierPort
    _public_ghost_phase_two: GhostStatePublicGhostPhaseTwoPort
    _get_maps: Callable[[], MapPort]

    @property
    def maps(self) -> MapPort:
        return self._get_maps()


class MonsterEvolutionApplyWorldTransitionPort(Protocol):
    def __call__(self, game: GameState, plan: WorldTransitionPlan, *, entourage: Any=...) -> None: ...

class MonsterEvolutionCompleteMajorBreakthroughPort(Protocol):
    def __call__(self, game: GameState, rng: random.Random, old_label: str) -> None: ...

class MonsterEvolutionCompleteMonsterEvolutionPort(Protocol):
    def __call__(self, game: GameState, evolution_id: str, candidate: dict[str, Any], *, trial_completed: bool=..., prepared_lineage: dict[str, Any] | None=..., trial_rng: random.Random | None=...) -> dict[str, Any]: ...

class MonsterEvolutionConsumeBreakthroughAidsPort(Protocol):
    def __call__(self, player: Player, scope: str) -> None: ...

class MonsterEvolutionEnsureMarketPort(Protocol):
    def __call__(self, game: GameState, rng: random.Random) -> bool: ...

class MonsterEvolutionLoadPort(Protocol):
    def __call__(self, game_id: str) -> GameState: ...

class MonsterEvolutionManualBreakthroughKindPort(Protocol):
    def __call__(self, player: Player) -> str | None: ...

class MonsterEvolutionPlanWorldTransitionPort(Protocol):
    def __call__(self, game: GameState, destination: str, mode: str=..., *, route_id: str | None=..., arrival_location: str | None=..., reason: str=..., instance_id: str | None=...) -> WorldTransitionPlan: ...

class MonsterEvolutionStartUpperTrialPort(Protocol):
    def __call__(self, game: GameState, kind: str, *, evolution: dict[str, Any], lineage: dict[str, Any] | None) -> None: ...

class MonsterEvolutionValidateMonsterEvolutionPort(Protocol):
    def __call__(self, game: GameState, evolution_id: str) -> dict[str, Any]: ...

class MonsterEvolutionPresentPort(Protocol):
    def __call__(self, game: GameState) -> dict[str, Any]: ...

@dataclass(frozen=True, slots=True)
class MonsterEvolutionDependencies:
    _apply_world_transition: MonsterEvolutionApplyWorldTransitionPort
    _complete_major_breakthrough: MonsterEvolutionCompleteMajorBreakthroughPort
    _complete_monster_evolution: MonsterEvolutionCompleteMonsterEvolutionPort
    _consume_breakthrough_aids: MonsterEvolutionConsumeBreakthroughAidsPort
    _ensure_market: MonsterEvolutionEnsureMarketPort
    _load: MonsterEvolutionLoadPort
    _plan_world_transition: MonsterEvolutionPlanWorldTransitionPort
    _start_upper_trial: MonsterEvolutionStartUpperTrialPort
    _validate_monster_evolution: MonsterEvolutionValidateMonsterEvolutionPort
    _get_maps: Callable[[], MapPort]
    present: MonsterEvolutionPresentPort
    _get_store: Callable[[], CommitPort]

    @property
    def maps(self) -> MapPort:
        return self._get_maps()

    @property
    def store(self) -> CommitPort:
        return self._get_store()


class NatalActionsAddNatalArtifactExperiencePort(Protocol):
    def __call__(self, game: GameState, amount: int) -> tuple[int, int]: ...

class NatalActionsBindCraftedNatalArtifactPort(Protocol):
    def __call__(self, game: GameState, artifact: dict[str, Any]) -> None: ...

class NatalActionsEnsureNatalArtifactPort(Protocol):
    def __call__(self, game: GameState) -> bool: ...

class NatalActionsLoadPort(Protocol):
    def __call__(self, game_id: str) -> GameState: ...

class NatalActionsNatalArtifactCandidatePort(Protocol):
    def __call__(self, item: Item) -> bool: ...

class NatalActionsNatalArtifactConfigPort(Protocol):
    def __call__(self) -> dict[str, Any]: ...

class NatalActionsNatalArtifactMaterialDefinitionsPort(Protocol):
    def __call__(self) -> dict[str, dict[str, Any]]: ...

class NatalActionsNatalRefineAllPlanPort(Protocol):
    def __call__(self, game: GameState) -> tuple[int, int]: ...

class NatalActionsNatalRefineCostPort(Protocol):
    def __call__(self, level: int, game: GameState | None=...) -> int: ...

class NatalActionsNatalSlotsForLevelPort(Protocol):
    def __call__(self, level: int) -> int: ...

class NatalActionsSyncNatalArtifactBonusesPort(Protocol):
    def __call__(self, game: GameState) -> None: ...

class NatalActionsUnbindCraftedNatalArtifactPort(Protocol):
    def __call__(self, game: GameState, artifact_id: str) -> None: ...

class NatalActionsPresentPort(Protocol):
    def __call__(self, game: GameState) -> dict[str, Any]: ...

@dataclass(frozen=True, slots=True)
class NatalActionsDependencies:
    _add_natal_artifact_experience: NatalActionsAddNatalArtifactExperiencePort
    _bind_crafted_natal_artifact: NatalActionsBindCraftedNatalArtifactPort
    _ensure_natal_artifact: NatalActionsEnsureNatalArtifactPort
    _load: NatalActionsLoadPort
    _natal_artifact_candidate: NatalActionsNatalArtifactCandidatePort
    _natal_artifact_config: NatalActionsNatalArtifactConfigPort
    _natal_artifact_material_definitions: NatalActionsNatalArtifactMaterialDefinitionsPort
    _natal_refine_all_plan: NatalActionsNatalRefineAllPlanPort
    _natal_refine_cost: NatalActionsNatalRefineCostPort
    _natal_slots_for_level: NatalActionsNatalSlotsForLevelPort
    _sync_natal_artifact_bonuses: NatalActionsSyncNatalArtifactBonusesPort
    _unbind_crafted_natal_artifact: NatalActionsUnbindCraftedNatalArtifactPort
    present: NatalActionsPresentPort
    _get_store: Callable[[], CommitPort]

    @property
    def store(self) -> CommitPort:
        return self._get_store()


class NatalStateAddNatalArtifactExperiencePort(Protocol):
    def __call__(self, game: GameState, amount: int) -> tuple[int, int]: ...

class NatalStateBindCraftedNatalArtifactPort(Protocol):
    def __call__(self, game: GameState, artifact: dict[str, Any]) -> None: ...

class NatalStateCraftedNatalSourcePort(Protocol):
    def __call__(self, game: GameState) -> dict[str, Any] | None: ...

class NatalStateNatalArtifactConfigPort(Protocol):
    def __call__(self) -> dict[str, Any]: ...

class NatalStateNatalArtifactMaterialDefinitionsPort(Protocol):
    def __call__(self) -> dict[str, dict[str, Any]]: ...

class NatalStateNatalFlatCombatGrowthPort(Protocol):
    def __call__(self, level: int) -> float: ...

class NatalStateNatalLevelRequiredPort(Protocol):
    def __call__(self, level: int) -> int: ...

class NatalStateNatalLevelScalePort(Protocol):
    def __call__(self, level: int) -> float: ...

class NatalStateNatalRefineCostPort(Protocol):
    def __call__(self, level: int, game: GameState | None=...) -> int: ...

class NatalStateNatalSlotsForLevelPort(Protocol):
    def __call__(self, level: int) -> int: ...

class NatalStateSyncNatalArtifactBonusesPort(Protocol):
    def __call__(self, game: GameState) -> None: ...

@dataclass(frozen=True, slots=True)
class NatalStateDependencies:
    _add_natal_artifact_experience: NatalStateAddNatalArtifactExperiencePort
    _bind_crafted_natal_artifact: NatalStateBindCraftedNatalArtifactPort
    _crafted_natal_source: NatalStateCraftedNatalSourcePort
    _natal_artifact_config: NatalStateNatalArtifactConfigPort
    _natal_artifact_material_definitions: NatalStateNatalArtifactMaterialDefinitionsPort
    _natal_flat_combat_growth: NatalStateNatalFlatCombatGrowthPort
    _natal_level_required: NatalStateNatalLevelRequiredPort
    _natal_level_scale: NatalStateNatalLevelScalePort
    _natal_refine_cost: NatalStateNatalRefineCostPort
    _natal_slots_for_level: NatalStateNatalSlotsForLevelPort
    _sync_natal_artifact_bonuses: NatalStateSyncNatalArtifactBonusesPort


class NatalViewCraftedNatalSourcePort(Protocol):
    def __call__(self, game: GameState) -> dict[str, Any] | None: ...

class NatalViewEnsureNatalArtifactPort(Protocol):
    def __call__(self, game: GameState) -> bool: ...

class NatalViewNatalArtifactCandidatePort(Protocol):
    def __call__(self, item: Item) -> bool: ...

class NatalViewNatalArtifactConfigPort(Protocol):
    def __call__(self) -> dict[str, Any]: ...

class NatalViewNatalArtifactMaterialDefinitionsPort(Protocol):
    def __call__(self) -> dict[str, dict[str, Any]]: ...

class NatalViewNatalFlatCombatGrowthPort(Protocol):
    def __call__(self, level: int) -> float: ...

class NatalViewNatalLevelRequiredPort(Protocol):
    def __call__(self, level: int) -> int: ...

class NatalViewNatalLevelScalePort(Protocol):
    def __call__(self, level: int) -> float: ...

class NatalViewNatalRefineAllPlanPort(Protocol):
    def __call__(self, game: GameState) -> tuple[int, int]: ...

class NatalViewNatalRefineCostPort(Protocol):
    def __call__(self, level: int, game: GameState | None=...) -> int: ...

class NatalViewNatalSlotsForLevelPort(Protocol):
    def __call__(self, level: int) -> int: ...

@dataclass(frozen=True, slots=True)
class NatalViewDependencies:
    _crafted_natal_source: NatalViewCraftedNatalSourcePort
    _ensure_natal_artifact: NatalViewEnsureNatalArtifactPort
    _natal_artifact_candidate: NatalViewNatalArtifactCandidatePort
    _natal_artifact_config: NatalViewNatalArtifactConfigPort
    _natal_artifact_material_definitions: NatalViewNatalArtifactMaterialDefinitionsPort
    _natal_flat_combat_growth: NatalViewNatalFlatCombatGrowthPort
    _natal_level_required: NatalViewNatalLevelRequiredPort
    _natal_level_scale: NatalViewNatalLevelScalePort
    _natal_refine_all_plan: NatalViewNatalRefineAllPlanPort
    _natal_refine_cost: NatalViewNatalRefineCostPort
    _natal_slots_for_level: NatalViewNatalSlotsForLevelPort


class SageActionsAddOpportunityPort(Protocol):
    def __call__(self, player: Player, amount: float, regional_efficiencies: dict[str, float] | None=..., *, apply_efficiency: bool=...) -> float: ...

class SageActionsCombatPort(Protocol):
    def __call__(self, game: GameState, target: dict[str, Any], lethal: bool, rng: random.Random) -> tuple[str, str]: ...

class SageActionsCompleteMajorBreakthroughPort(Protocol):
    def __call__(self, game: GameState, rng: random.Random, old_label: str) -> None: ...

class SageActionsCompleteMinorBreakthroughPort(Protocol):
    def __call__(self, game: GameState, rng: random.Random, old_label: str) -> None: ...

class SageActionsEnsureSageStatePort(Protocol):
    def __call__(self, game: GameState) -> bool: ...

class SageActionsHaoranManualGainPort(Protocol):
    def __call__(self, origin_realm: int, previous: int, level: int) -> float: ...

class SageActionsLoadPort(Protocol):
    def __call__(self, game_id: str) -> GameState: ...

class SageActionsMajorBreakthroughRequirementPort(Protocol):
    def __call__(self, player: Player) -> dict[str, Any]: ...

class SageActionsOuterAdvanceBlockReasonPort(Protocol):
    def __call__(self, game: GameState) -> str: ...

class SageActionsOuterCostPort(Protocol):
    def __call__(self, action: str, player: Player) -> int: ...

class SageActionsOuterTargetPort(Protocol):
    def __call__(self, player: Player) -> tuple[int, int] | None: ...

class SageActionsPlayerDoctrinePort(Protocol):
    def __call__(self, game: GameState, world: str | None=...) -> dict[str, Any] | None: ...

class SageActionsRankMembersPort(Protocol):
    def __call__(self, doctrine: dict[str, Any]) -> list[dict[str, Any]]: ...

class SageActionsRefreshSageEffectsPort(Protocol):
    def __call__(self, game: GameState) -> None: ...

class SageActionsSageWorldPort(Protocol):
    def __call__(self, game: GameState, world: str | None=...) -> dict[str, Any] | None: ...

class SageActionsStartBreakthroughTrialPort(Protocol):
    def __call__(self, game: GameState, kind: str, source: int, target: int, old_label: str, *, major: bool, rng: random.Random) -> None: ...

class SageActionsPresentPort(Protocol):
    def __call__(self, game: GameState) -> dict[str, Any]: ...

@dataclass(frozen=True, slots=True)
class SageActionsDependencies:
    _add_opportunity: SageActionsAddOpportunityPort
    _combat: SageActionsCombatPort
    _complete_major_breakthrough: SageActionsCompleteMajorBreakthroughPort
    _complete_minor_breakthrough: SageActionsCompleteMinorBreakthroughPort
    _ensure_sage_state: SageActionsEnsureSageStatePort
    _haoran_manual_gain: SageActionsHaoranManualGainPort
    _load: SageActionsLoadPort
    _major_breakthrough_requirement: SageActionsMajorBreakthroughRequirementPort
    _outer_advance_block_reason: SageActionsOuterAdvanceBlockReasonPort
    _outer_cost: SageActionsOuterCostPort
    _outer_target: SageActionsOuterTargetPort
    _player_doctrine: SageActionsPlayerDoctrinePort
    _rank_members: SageActionsRankMembersPort
    _refresh_sage_effects: SageActionsRefreshSageEffectsPort
    _sage_world: SageActionsSageWorldPort
    _start_breakthrough_trial: SageActionsStartBreakthroughTrialPort
    present: SageActionsPresentPort
    _get_store: Callable[[], CommitPort]

    @property
    def store(self) -> CommitPort:
        return self._get_store()


class SageSocietyAddOpportunityPort(Protocol):
    def __call__(self, player: Player, amount: float, regional_efficiencies: dict[str, float] | None=..., *, apply_efficiency: bool=...) -> float: ...

class SageSocietyAdvanceSageSocietyYearPort(Protocol):
    def __call__(self, game: GameState, rng: random.Random) -> None: ...

class SageSocietyEnsureSageStatePort(Protocol):
    def __call__(self, game: GameState) -> bool: ...

class SageSocietyNormalizeSageDoctrinePort(Protocol):
    def __call__(self, doctrine: dict[str, Any], age: int, cfg: dict[str, Any]) -> None: ...

class SageSocietyNormalizeSageMemberPort(Protocol):
    def __call__(self, member: dict[str, Any]) -> None: ...

class SageSocietyPlayerDoctrinePort(Protocol):
    def __call__(self, game: GameState, world: str | None=...) -> dict[str, Any] | None: ...

class SageSocietyRefreshSageEffectsPort(Protocol):
    def __call__(self, game: GameState) -> None: ...

class SageSocietySageWorldPort(Protocol):
    def __call__(self, game: GameState, world: str | None=...) -> dict[str, Any] | None: ...

@dataclass(frozen=True, slots=True)
class SageSocietyDependencies:
    _add_opportunity: SageSocietyAddOpportunityPort
    _advance_sage_society_year: SageSocietyAdvanceSageSocietyYearPort
    _ensure_sage_state: SageSocietyEnsureSageStatePort
    _normalize_sage_doctrine: SageSocietyNormalizeSageDoctrinePort
    _normalize_sage_member: SageSocietyNormalizeSageMemberPort
    _player_doctrine: SageSocietyPlayerDoctrinePort
    _refresh_sage_effects: SageSocietyRefreshSageEffectsPort
    _sage_world: SageSocietySageWorldPort


class SageViewEnsureSageStatePort(Protocol):
    def __call__(self, game: GameState) -> bool: ...

class SageViewHaoranManualGainPort(Protocol):
    def __call__(self, origin_realm: int, previous: int, level: int) -> float: ...

class SageViewOuterAdvanceBlockReasonPort(Protocol):
    def __call__(self, game: GameState) -> str: ...

class SageViewOuterCostPort(Protocol):
    def __call__(self, action: str, player: Player) -> int: ...

class SageViewOuterTargetPort(Protocol):
    def __call__(self, player: Player) -> tuple[int, int] | None: ...

class SageViewPlayerDoctrinePort(Protocol):
    def __call__(self, game: GameState, world: str | None=...) -> dict[str, Any] | None: ...

class SageViewPublicInnerOuterPort(Protocol):
    def __call__(self, game: GameState) -> dict[str, Any]: ...

class SageViewRankMembersPort(Protocol):
    def __call__(self, doctrine: dict[str, Any]) -> list[dict[str, Any]]: ...

class SageViewSageWorldPort(Protocol):
    def __call__(self, game: GameState, world: str | None=...) -> dict[str, Any] | None: ...

@dataclass(frozen=True, slots=True)
class SageViewDependencies:
    _ensure_sage_state: SageViewEnsureSageStatePort
    _haoran_manual_gain: SageViewHaoranManualGainPort
    _outer_advance_block_reason: SageViewOuterAdvanceBlockReasonPort
    _outer_cost: SageViewOuterCostPort
    _outer_target: SageViewOuterTargetPort
    _player_doctrine: SageViewPlayerDoctrinePort
    _public_inner_outer: SageViewPublicInnerOuterPort
    _rank_members: SageViewRankMembersPort
    _sage_world: SageViewSageWorldPort


@dataclass(frozen=True, slots=True)
class AsuraCourtDependencies:
    _npc_power: Callable[[SectNpc], float]
    _combat: Callable[[GameState, dict[str, Any], bool, random.Random], tuple[str, str]]


@dataclass(frozen=True, slots=True)
class UpperInstitutionDependencies:
    _load: Callable[[str], GameState]
    advance: Callable[[str, str, int], dict[str, Any]]
    present: Callable[[GameState], dict[str, Any]]
    _get_store: Callable[[], CommitPort]
    court: AsuraCourtDependencies

    @property
    def store(self) -> CommitPort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class MonsterValidationDependencies:
    _manual_breakthrough_kind: MonsterEvolutionManualBreakthroughKindPort


@dataclass(frozen=True, slots=True)
class DemonicPreviewDependencies:
    _load: DemonicActionsLoadPort


@dataclass(frozen=True, slots=True)
class CharacterDependencies:
    monster_validation: MonsterValidationDependencies
    demonic_preview: DemonicPreviewDependencies
    upper_institution: UpperInstitutionDependencies
    buddhist_guard: BuddhistGuardDependencies
    buddhist_state: BuddhistStateDependencies
    concubine_queries: ConcubineQueriesDependencies
    demonic_actions: DemonicActionsDependencies
    demonic_combat: DemonicCombatDependencies
    demonic_growth: DemonicGrowthDependencies
    demonic_puppet_rules: DemonicPuppetRulesDependencies
    demonic_view: DemonicViewDependencies
    family_actions: FamilyActionsDependencies
    family_society: FamilySocietyDependencies
    family_view: FamilyViewDependencies
    ghost_actions: GhostActionsDependencies
    ghost_state: GhostStateDependencies
    monster_evolution: MonsterEvolutionDependencies
    natal_actions: NatalActionsDependencies
    natal_state: NatalStateDependencies
    natal_view: NatalViewDependencies
    sage_actions: SageActionsDependencies
    sage_society: SageSocietyDependencies
    sage_view: SageViewDependencies
