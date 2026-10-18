"""Static late-bound adapters for character systems and compatibility consumers."""
from __future__ import annotations
from .dependencies import (
    AsuraCourtDependencies,
    UpperInstitutionDependencies,
    MonsterValidationDependencies,
    DemonicPreviewDependencies,
    BuddhistGuardDependencies,
    BuddhistStateDependencies,
    ConcubineQueriesDependencies,
    DemonicActionsDependencies,
    DemonicCombatDependencies,
    DemonicGrowthDependencies,
    DemonicPuppetRulesDependencies,
    DemonicViewDependencies,
    FamilyActionsDependencies,
    FamilySocietyDependencies,
    FamilyViewDependencies,
    GhostActionsDependencies,
    GhostStateDependencies,
    MonsterEvolutionDependencies,
    NatalActionsDependencies,
    NatalStateDependencies,
    NatalViewDependencies,
    SageActionsDependencies,
    SageSocietyDependencies,
    SageViewDependencies,
    CharacterDependencies,
)

_OMITTED = object()


def bind_asura_court(host) -> AsuraCourtDependencies:
    return AsuraCourtDependencies(
        _npc_power=lambda npc: host._npc_power(npc),
        _combat=lambda game, encounter, lethal, rng: host._combat(game, encounter, lethal, rng),
    )


def bind_upper_institution(host) -> UpperInstitutionDependencies:
    return UpperInstitutionDependencies(
        _load=lambda game_id: host._load(game_id),
        advance=lambda game_id, action, units: host.advance(game_id, action, units),
        present=lambda game: host.present(game),
        _get_store=lambda: host.store,
        court=bind_asura_court(host),
    )

def bind_buddhist_guard(host) -> BuddhistGuardDependencies:
    def forward_load(game_id):
        return host._load(game_id)

    return BuddhistGuardDependencies(
        _load=forward_load,
    )


def bind_buddhist_state(host) -> BuddhistStateDependencies:
    def forward_advance_buddhist_society_year(game):
        return host._advance_buddhist_society_year(game)

    def forward_buddhist_burden(game):
        return host._buddhist_burden(game)

    def forward_buddhist_permissions(game):
        return host._buddhist_permissions(game)

    def forward_ensure_buddhist_state(game):
        return host._ensure_buddhist_state(game)

    return BuddhistStateDependencies(
        _get_maps=lambda: host.maps,
        _advance_buddhist_society_year=forward_advance_buddhist_society_year,
        _buddhist_burden=forward_buddhist_burden,
        _buddhist_permissions=forward_buddhist_permissions,
        _ensure_buddhist_state=forward_ensure_buddhist_state,
    )


def bind_concubine_queries(host) -> ConcubineQueriesDependencies:
    def forward_ensure_intrigue_personality(game, npc):
        return host._ensure_intrigue_personality(game, npc)

    def forward_find_npc(game, npc_id):
        return host._find_npc(game, npc_id)

    def forward_intrigue_enabled():
        return host._intrigue_enabled()

    def forward_npc_power(npc):
        return host._npc_power(npc)

    def forward_npc_realm_name(npc):
        return host._npc_realm_name(npc)

    def forward_npc_root_name(root_id):
        return host._npc_root_name(root_id)

    def forward_owner_personality(game, owner):
        return host._owner_personality(game, owner)

    def forward_personality_score(personality, scores, default=_OMITTED):
        if default is _OMITTED:
            return host._personality_score(personality, scores)
        if default is not _OMITTED:
            return host._personality_score(personality, scores, default)

    def forward_promote_cached_npc(game, npc_id, reason):
        return host._promote_cached_npc(game, npc_id, reason)

    def forward_rank(value):
        return host._rank(value)

    def forward_relation_by_id(player, target_id):
        return host._relation_by_id(player, target_id)

    def forward_relationship_protectors(game, enemy):
        return host._relationship_protectors(game, enemy)

    def forward_revenge_ready(game, family, adversary_id):
        return host._revenge_ready(game, family, adversary_id)

    def forward_sect_members(game, sect):
        return host._sect_members(game, sect)

    def forward_stable_gender(identity, name=_OMITTED):
        if name is _OMITTED:
            return host._stable_gender(identity)
        if name is not _OMITTED:
            return host._stable_gender(identity, name)

    return ConcubineQueriesDependencies(
        _ensure_intrigue_personality=forward_ensure_intrigue_personality,
        _find_npc=forward_find_npc,
        _intrigue_enabled=forward_intrigue_enabled,
        _npc_power=forward_npc_power,
        _npc_realm_name=forward_npc_realm_name,
        _npc_root_name=forward_npc_root_name,
        _owner_personality=forward_owner_personality,
        _personality_score=forward_personality_score,
        _promote_cached_npc=forward_promote_cached_npc,
        _rank=forward_rank,
        _relation_by_id=forward_relation_by_id,
        _relationship_protectors=forward_relationship_protectors,
        _revenge_ready=forward_revenge_ready,
        _sect_members=forward_sect_members,
        _stable_gender=forward_stable_gender,
    )


def bind_demonic_actions(host) -> DemonicActionsDependencies:
    def forward_complete_soul_refinement(player, soul):
        return host._complete_soul_refinement(player, soul)

    def forward_demonic_rules():
        return host._demonic_rules()

    def forward_devour_puppet(game, puppet):
        return host._devour_puppet(game, puppet)

    def forward_grant_art_experience(player, art_id, amount):
        return host._grant_art_experience(player, art_id, amount)

    def forward_load(game_id):
        return host._load(game_id)

    def forward_puppet_technique(technique_id):
        return host._puppet_technique(technique_id)

    def forward_soul_refine_gain(player):
        return host._soul_refine_gain(player)

    def forwardpresent(game):
        return host.present(game)

    def forwardtrain_owned(game_id, target_id, kind, axis, batches=_OMITTED):
        if batches is _OMITTED:
            return host.train_owned(game_id, target_id, kind, axis)
        if batches is not _OMITTED:
            return host.train_owned(game_id, target_id, kind, axis, batches)

    return DemonicActionsDependencies(
        _get_store=lambda: host.store,
        _complete_soul_refinement=forward_complete_soul_refinement,
        _demonic_rules=forward_demonic_rules,
        _devour_puppet=forward_devour_puppet,
        _grant_art_experience=forward_grant_art_experience,
        _load=forward_load,
        _puppet_technique=forward_puppet_technique,
        _soul_refine_gain=forward_soul_refine_gain,
        present=forwardpresent,
        train_owned=forwardtrain_owned,
    )


def bind_demonic_combat(host) -> DemonicCombatDependencies:
    def forward_living_puppet_party_powers(player, game=_OMITTED):
        if game is _OMITTED:
            return host._living_puppet_party_powers(player)
        if game is not _OMITTED:
            return host._living_puppet_party_powers(player, game)

    def forward_player_intrinsic_combat_power(player):
        return host._player_intrinsic_combat_power(player)

    def forward_public_party(game):
        return host._public_party(game)

    def forward_puppet_intrinsic_contribution(player):
        return host._puppet_intrinsic_contribution(player)

    return DemonicCombatDependencies(
        _living_puppet_party_powers=forward_living_puppet_party_powers,
        _player_intrinsic_combat_power=forward_player_intrinsic_combat_power,
        _public_party=forward_public_party,
        _puppet_intrinsic_contribution=forward_puppet_intrinsic_contribution,
    )


def bind_demonic_growth(host) -> DemonicGrowthDependencies:
    def forward_add_opportunity(player, amount, regional_efficiencies=_OMITTED, *, apply_efficiency=_OMITTED):
        keywords = {}
        if apply_efficiency is not _OMITTED:
            keywords["apply_efficiency"] = apply_efficiency
        if regional_efficiencies is _OMITTED:
            return host._add_opportunity(player, amount, **keywords)
        if regional_efficiencies is not _OMITTED:
            return host._add_opportunity(player, amount, regional_efficiencies, **keywords)

    def forward_demonic_rules():
        return host._demonic_rules()

    def forward_soul_refine_gain(player):
        return host._soul_refine_gain(player)

    return DemonicGrowthDependencies(
        _add_opportunity=forward_add_opportunity,
        _demonic_rules=forward_demonic_rules,
        _soul_refine_gain=forward_soul_refine_gain,
    )


def bind_demonic_puppet_rules(host) -> DemonicPuppetRulesDependencies:
    def forward_demonic_rules():
        return host._demonic_rules()

    return DemonicPuppetRulesDependencies(
        _demonic_rules=forward_demonic_rules,
    )


def bind_demonic_view(host) -> DemonicViewDependencies:
    def forward_demonic_rules():
        return host._demonic_rules()

    def forward_npc_realm_name(npc):
        return host._npc_realm_name(npc)

    def forward_puppet_technique(technique_id):
        return host._puppet_technique(technique_id)

    def forward_secluded_refining_years(player):
        return host._secluded_refining_years(player)

    def forward_stable_gender(identity, name=_OMITTED):
        if name is _OMITTED:
            return host._stable_gender(identity)
        if name is not _OMITTED:
            return host._stable_gender(identity, name)

    return DemonicViewDependencies(
        _demonic_rules=forward_demonic_rules,
        _npc_realm_name=forward_npc_realm_name,
        _puppet_technique=forward_puppet_technique,
        _secluded_refining_years=forward_secluded_refining_years,
        _stable_gender=forward_stable_gender,
    )


def bind_family_actions(host) -> FamilyActionsDependencies:
    def forward_family_assign_office(game, npc, sect):
        return host._family_assign_office(game, npc, sect)

    def forward_family_child_npc(child):
        return host._family_child_npc(child)

    def forward_family_decision_member(game, npc, sect):
        return host._family_decision_member(game, npc, sect)

    def forward_family_elites(game, entity):
        return host._family_elites(game, entity)

    def forward_family_equipment(player, item):
        return host._family_equipment(player, item)

    def forward_family_infusion(game, npc):
        return host._family_infusion(game, npc)

    def forward_family_is_kin(game, npc):
        return host._family_is_kin(game, npc)

    def forward_family_log(game, action, text, changes=_OMITTED):
        if changes is _OMITTED:
            return host._family_log(game, action, text)
        if changes is not _OMITTED:
            return host._family_log(game, action, text, changes)

    def forward_family_register_children(game):
        return host._family_register_children(game)

    def forward_family_relation(game, other):
        return host._family_relation(game, other)

    def forward_family_total_power(game, family):
        return host._family_total_power(game, family)

    def forward_family_world_tier(world):
        return host._family_world_tier(world)

    def forward_has_family_voice(game):
        return host._has_family_voice(game)

    def forward_intrigue_enabled():
        return host._intrigue_enabled()

    def forward_intrigue_is_imprisoned(game, npc_id):
        return host._intrigue_is_imprisoned(game, npc_id)

    def forward_load(game_id):
        return host._load(game_id)

    def forward_npc_realm_name(npc):
        return host._npc_realm_name(npc)

    def forward_random_npc_root(realm_index, rng):
        return host._random_npc_root(realm_index, rng)

    def forward_start_war(game, kind, attacker, defender, *, initiated_by_player=_OMITTED, prepare_supplies=_OMITTED, strategic_war_id=_OMITTED):
        keywords = {}
        if initiated_by_player is not _OMITTED:
            keywords["initiated_by_player"] = initiated_by_player
        if prepare_supplies is not _OMITTED:
            keywords["prepare_supplies"] = prepare_supplies
        if strategic_war_id is not _OMITTED:
            keywords["strategic_war_id"] = strategic_war_id
        return host._start_war(game, kind, attacker, defender, **keywords)

    def forwardassert_guixu_operation_allowed(game_id, operation):
        return host.assert_guixu_operation_allowed(game_id, operation)

    def forwardpresent(game):
        return host.present(game)

    return FamilyActionsDependencies(
        _get_maps=lambda: host.maps,
        _get_store=lambda: host.store,
        _family_assign_office=forward_family_assign_office,
        _family_child_npc=forward_family_child_npc,
        _family_decision_member=forward_family_decision_member,
        _family_elites=forward_family_elites,
        _family_equipment=forward_family_equipment,
        _family_infusion=forward_family_infusion,
        _family_is_kin=forward_family_is_kin,
        _family_log=forward_family_log,
        _family_register_children=forward_family_register_children,
        _family_relation=forward_family_relation,
        _family_total_power=forward_family_total_power,
        _family_world_tier=forward_family_world_tier,
        _has_family_voice=forward_has_family_voice,
        _intrigue_enabled=forward_intrigue_enabled,
        _intrigue_is_imprisoned=forward_intrigue_is_imprisoned,
        _load=forward_load,
        _npc_realm_name=forward_npc_realm_name,
        _random_npc_root=forward_random_npc_root,
        _start_war=forward_start_war,
        assert_guixu_operation_allowed=forwardassert_guixu_operation_allowed,
        present=forwardpresent,
    )


def bind_family_society(host) -> FamilySocietyDependencies:
    def forward_actual_player_realm(player):
        return host._actual_player_realm(player)

    def forward_ensure_intrigue_faction(game, kind, faction_id):
        return host._ensure_intrigue_faction(game, kind, faction_id)

    def forward_family_child_npc(child):
        return host._family_child_npc(child)

    def forward_family_decision_member(game, npc, sect):
        return host._family_decision_member(game, npc, sect)

    def forward_family_dissolve(game, reason, absorber=_OMITTED):
        if absorber is _OMITTED:
            return host._family_dissolve(game, reason)
        if absorber is not _OMITTED:
            return host._family_dissolve(game, reason, absorber)

    def forward_family_elites(game, entity):
        return host._family_elites(game, entity)

    def forward_family_is_kin(game, npc):
        return host._family_is_kin(game, npc)

    def forward_family_log(game, action, text, changes=_OMITTED):
        if changes is _OMITTED:
            return host._family_log(game, action, text)
        if changes is not _OMITTED:
            return host._family_log(game, action, text, changes)

    def forward_family_relation(game, other):
        return host._family_relation(game, other)

    def forward_family_total_power(game, family):
        return host._family_total_power(game, family)

    def forward_family_world_tier(world):
        return host._family_world_tier(world)

    def forward_find_npc(game, npc_id):
        return host._find_npc(game, npc_id)

    def forward_governance_threshold(world):
        return host._governance_threshold(world)

    def forward_intrigue_decision_threshold(kind):
        return host._intrigue_decision_threshold(kind)

    def forward_intrigue_enabled():
        return host._intrigue_enabled()

    def forward_intrigue_has_decision_authority(game, kind, faction_id, member_id=_OMITTED):
        if member_id is _OMITTED:
            return host._intrigue_has_decision_authority(game, kind, faction_id)
        if member_id is not _OMITTED:
            return host._intrigue_has_decision_authority(game, kind, faction_id, member_id)

    def forward_intrigue_is_imprisoned(game, npc_id):
        return host._intrigue_is_imprisoned(game, npc_id)

    def forward_intrigue_position_specs(kind):
        return host._intrigue_position_specs(kind)

    def forward_npc_power(npc):
        return host._npc_power(npc)

    def forward_npc_root_name(root_id):
        return host._npc_root_name(root_id)

    def forward_sect_members(game, sect):
        return host._sect_members(game, sect)

    return FamilySocietyDependencies(
        _actual_player_realm=forward_actual_player_realm,
        _ensure_intrigue_faction=forward_ensure_intrigue_faction,
        _family_child_npc=forward_family_child_npc,
        _family_decision_member=forward_family_decision_member,
        _family_dissolve=forward_family_dissolve,
        _family_elites=forward_family_elites,
        _family_is_kin=forward_family_is_kin,
        _family_log=forward_family_log,
        _family_relation=forward_family_relation,
        _family_total_power=forward_family_total_power,
        _family_world_tier=forward_family_world_tier,
        _find_npc=forward_find_npc,
        _governance_threshold=forward_governance_threshold,
        _intrigue_decision_threshold=forward_intrigue_decision_threshold,
        _intrigue_enabled=forward_intrigue_enabled,
        _intrigue_has_decision_authority=forward_intrigue_has_decision_authority,
        _intrigue_is_imprisoned=forward_intrigue_is_imprisoned,
        _intrigue_position_specs=forward_intrigue_position_specs,
        _npc_power=forward_npc_power,
        _npc_root_name=forward_npc_root_name,
        _sect_members=forward_sect_members,
    )


def bind_family_view(host) -> FamilyViewDependencies:
    def forward_family_equipment(player, item):
        return host._family_equipment(player, item)

    def forward_family_infusion(game, npc):
        return host._family_infusion(game, npc)

    def forward_family_is_kin(game, npc):
        return host._family_is_kin(game, npc)

    def forward_family_relation(game, other):
        return host._family_relation(game, other)

    def forward_family_total_power(game, family):
        return host._family_total_power(game, family)

    def forward_family_world_tier(world):
        return host._family_world_tier(world)

    def forward_find_npc(game, npc_id):
        return host._find_npc(game, npc_id)

    def forward_has_family_voice(game):
        return host._has_family_voice(game)

    def forward_intrigue_enabled():
        return host._intrigue_enabled()

    def forward_intrigue_is_imprisoned(game, npc_id):
        return host._intrigue_is_imprisoned(game, npc_id)

    def forward_npc_power(npc):
        return host._npc_power(npc)

    return FamilyViewDependencies(
        _family_equipment=forward_family_equipment,
        _family_infusion=forward_family_infusion,
        _family_is_kin=forward_family_is_kin,
        _family_relation=forward_family_relation,
        _family_total_power=forward_family_total_power,
        _family_world_tier=forward_family_world_tier,
        _find_npc=forward_find_npc,
        _has_family_voice=forward_has_family_voice,
        _intrigue_enabled=forward_intrigue_enabled,
        _intrigue_is_imprisoned=forward_intrigue_is_imprisoned,
        _npc_power=forward_npc_power,
    )


def bind_ghost_actions(host) -> GhostActionsDependencies:
    def forward_combat(game, target, *, lethal, rng):
        return host._combat(game, target, lethal=lethal, rng=rng)

    def forward_load(game_id):
        return host._load(game_id)

    def forwardpresent(game):
        return host.present(game)

    return GhostActionsDependencies(
        _get_store=lambda: host.store,
        _combat=forward_combat,
        _load=forward_load,
        present=forwardpresent,
    )


def bind_ghost_state(host) -> GhostStateDependencies:
    def forward_monster_travel_multiplier(player, destination):
        return host._monster_travel_multiplier(player, destination)

    def forward_public_ghost_phase_two(game):
        return host._public_ghost_phase_two(game)

    return GhostStateDependencies(
        _get_maps=lambda: host.maps,
        _monster_travel_multiplier=forward_monster_travel_multiplier,
        _public_ghost_phase_two=forward_public_ghost_phase_two,
    )


def bind_monster_evolution(host) -> MonsterEvolutionDependencies:
    def forward_apply_world_transition(game, plan, *, entourage=_OMITTED):
        keywords = {}
        if entourage is not _OMITTED:
            keywords["entourage"] = entourage
        return host._apply_world_transition(game, plan, **keywords)

    def forward_complete_major_breakthrough(game, rng, old_label):
        return host._complete_major_breakthrough(game, rng, old_label)

    def forward_complete_monster_evolution(game, evolution_id, candidate, *, trial_completed=_OMITTED, prepared_lineage=_OMITTED, trial_rng=_OMITTED):
        keywords = {}
        if trial_completed is not _OMITTED:
            keywords["trial_completed"] = trial_completed
        if prepared_lineage is not _OMITTED:
            keywords["prepared_lineage"] = prepared_lineage
        if trial_rng is not _OMITTED:
            keywords["trial_rng"] = trial_rng
        return host._complete_monster_evolution(game, evolution_id, candidate, **keywords)

    def forward_consume_breakthrough_aids(player, scope):
        return host._consume_breakthrough_aids(player, scope)

    def forward_ensure_market(game, rng):
        return host._ensure_market(game, rng)

    def forward_load(game_id):
        return host._load(game_id)


    def forward_plan_world_transition(game, destination, mode=_OMITTED, *, route_id=_OMITTED, arrival_location=_OMITTED, reason=_OMITTED, instance_id=_OMITTED):
        keywords = {}
        if route_id is not _OMITTED:
            keywords["route_id"] = route_id
        if arrival_location is not _OMITTED:
            keywords["arrival_location"] = arrival_location
        if reason is not _OMITTED:
            keywords["reason"] = reason
        if instance_id is not _OMITTED:
            keywords["instance_id"] = instance_id
        if mode is _OMITTED:
            return host._plan_world_transition(game, destination, **keywords)
        if mode is not _OMITTED:
            return host._plan_world_transition(game, destination, mode, **keywords)

    def forward_start_upper_trial(game, kind, *, evolution, lineage):
        keywords = {}
        keywords["evolution"] = evolution
        keywords["lineage"] = lineage
        return host._start_upper_trial(game, kind, **keywords)

    def forward_validate_monster_evolution(game, evolution_id):
        return host._validate_monster_evolution(game, evolution_id)

    def forwardpresent(game):
        return host.present(game)

    return MonsterEvolutionDependencies(
        _get_maps=lambda: host.maps,
        _get_store=lambda: host.store,
        _apply_world_transition=forward_apply_world_transition,
        _complete_major_breakthrough=forward_complete_major_breakthrough,
        _complete_monster_evolution=forward_complete_monster_evolution,
        _consume_breakthrough_aids=forward_consume_breakthrough_aids,
        _ensure_market=forward_ensure_market,
        _load=forward_load,
        _plan_world_transition=forward_plan_world_transition,
        _start_upper_trial=forward_start_upper_trial,
        _validate_monster_evolution=forward_validate_monster_evolution,
        present=forwardpresent,
    )


def bind_natal_actions(host) -> NatalActionsDependencies:
    def forward_add_natal_artifact_experience(game, amount):
        return host._add_natal_artifact_experience(game, amount)

    def forward_bind_crafted_natal_artifact(game, artifact):
        return host._bind_crafted_natal_artifact(game, artifact)

    def forward_ensure_natal_artifact(game):
        return host._ensure_natal_artifact(game)

    def forward_load(game_id):
        return host._load(game_id)

    def forward_natal_artifact_candidate(item):
        return host._natal_artifact_candidate(item)

    def forward_natal_artifact_config():
        return host._natal_artifact_config()

    def forward_natal_artifact_material_definitions():
        return host._natal_artifact_material_definitions()

    def forward_natal_refine_all_plan(game):
        return host._natal_refine_all_plan(game)

    def forward_natal_refine_cost(level, game=_OMITTED):
        if game is _OMITTED:
            return host._natal_refine_cost(level)
        if game is not _OMITTED:
            return host._natal_refine_cost(level, game)

    def forward_natal_slots_for_level(level):
        return host._natal_slots_for_level(level)

    def forward_sync_natal_artifact_bonuses(game):
        return host._sync_natal_artifact_bonuses(game)

    def forward_unbind_crafted_natal_artifact(game, artifact_id):
        return host._unbind_crafted_natal_artifact(game, artifact_id)

    def forwardpresent(game):
        return host.present(game)

    return NatalActionsDependencies(
        _get_store=lambda: host.store,
        _add_natal_artifact_experience=forward_add_natal_artifact_experience,
        _bind_crafted_natal_artifact=forward_bind_crafted_natal_artifact,
        _ensure_natal_artifact=forward_ensure_natal_artifact,
        _load=forward_load,
        _natal_artifact_candidate=forward_natal_artifact_candidate,
        _natal_artifact_config=forward_natal_artifact_config,
        _natal_artifact_material_definitions=forward_natal_artifact_material_definitions,
        _natal_refine_all_plan=forward_natal_refine_all_plan,
        _natal_refine_cost=forward_natal_refine_cost,
        _natal_slots_for_level=forward_natal_slots_for_level,
        _sync_natal_artifact_bonuses=forward_sync_natal_artifact_bonuses,
        _unbind_crafted_natal_artifact=forward_unbind_crafted_natal_artifact,
        present=forwardpresent,
    )


def bind_natal_state(host) -> NatalStateDependencies:
    def forward_add_natal_artifact_experience(game, amount):
        return host._add_natal_artifact_experience(game, amount)

    def forward_bind_crafted_natal_artifact(game, artifact):
        return host._bind_crafted_natal_artifact(game, artifact)

    def forward_crafted_natal_source(game):
        return host._crafted_natal_source(game)

    def forward_natal_artifact_config():
        return host._natal_artifact_config()

    def forward_natal_artifact_material_definitions():
        return host._natal_artifact_material_definitions()

    def forward_natal_flat_combat_growth(level):
        return host._natal_flat_combat_growth(level)

    def forward_natal_level_required(level):
        return host._natal_level_required(level)

    def forward_natal_level_scale(level):
        return host._natal_level_scale(level)

    def forward_natal_refine_cost(level, game=_OMITTED):
        if game is _OMITTED:
            return host._natal_refine_cost(level)
        if game is not _OMITTED:
            return host._natal_refine_cost(level, game)

    def forward_natal_slots_for_level(level):
        return host._natal_slots_for_level(level)

    def forward_sync_natal_artifact_bonuses(game):
        return host._sync_natal_artifact_bonuses(game)

    return NatalStateDependencies(
        _add_natal_artifact_experience=forward_add_natal_artifact_experience,
        _bind_crafted_natal_artifact=forward_bind_crafted_natal_artifact,
        _crafted_natal_source=forward_crafted_natal_source,
        _natal_artifact_config=forward_natal_artifact_config,
        _natal_artifact_material_definitions=forward_natal_artifact_material_definitions,
        _natal_flat_combat_growth=forward_natal_flat_combat_growth,
        _natal_level_required=forward_natal_level_required,
        _natal_level_scale=forward_natal_level_scale,
        _natal_refine_cost=forward_natal_refine_cost,
        _natal_slots_for_level=forward_natal_slots_for_level,
        _sync_natal_artifact_bonuses=forward_sync_natal_artifact_bonuses,
    )


def bind_natal_view(host) -> NatalViewDependencies:
    def forward_crafted_natal_source(game):
        return host._crafted_natal_source(game)

    def forward_ensure_natal_artifact(game):
        return host._ensure_natal_artifact(game)

    def forward_natal_artifact_candidate(item):
        return host._natal_artifact_candidate(item)

    def forward_natal_artifact_config():
        return host._natal_artifact_config()

    def forward_natal_artifact_material_definitions():
        return host._natal_artifact_material_definitions()

    def forward_natal_flat_combat_growth(level):
        return host._natal_flat_combat_growth(level)

    def forward_natal_level_required(level):
        return host._natal_level_required(level)

    def forward_natal_level_scale(level):
        return host._natal_level_scale(level)

    def forward_natal_refine_all_plan(game):
        return host._natal_refine_all_plan(game)

    def forward_natal_refine_cost(level, game=_OMITTED):
        if game is _OMITTED:
            return host._natal_refine_cost(level)
        if game is not _OMITTED:
            return host._natal_refine_cost(level, game)

    def forward_natal_slots_for_level(level):
        return host._natal_slots_for_level(level)

    return NatalViewDependencies(
        _crafted_natal_source=forward_crafted_natal_source,
        _ensure_natal_artifact=forward_ensure_natal_artifact,
        _natal_artifact_candidate=forward_natal_artifact_candidate,
        _natal_artifact_config=forward_natal_artifact_config,
        _natal_artifact_material_definitions=forward_natal_artifact_material_definitions,
        _natal_flat_combat_growth=forward_natal_flat_combat_growth,
        _natal_level_required=forward_natal_level_required,
        _natal_level_scale=forward_natal_level_scale,
        _natal_refine_all_plan=forward_natal_refine_all_plan,
        _natal_refine_cost=forward_natal_refine_cost,
        _natal_slots_for_level=forward_natal_slots_for_level,
    )


def bind_sage_actions(host) -> SageActionsDependencies:
    def forward_add_opportunity(player, amount, regional_efficiencies=_OMITTED, *, apply_efficiency=_OMITTED):
        keywords = {}
        if apply_efficiency is not _OMITTED:
            keywords["apply_efficiency"] = apply_efficiency
        if regional_efficiencies is _OMITTED:
            return host._add_opportunity(player, amount, **keywords)
        if regional_efficiencies is not _OMITTED:
            return host._add_opportunity(player, amount, regional_efficiencies, **keywords)

    def forward_combat(game, target, lethal, rng):
        return host._combat(game, target, lethal, rng)

    def forward_complete_major_breakthrough(game, rng, old_label):
        return host._complete_major_breakthrough(game, rng, old_label)

    def forward_complete_minor_breakthrough(game, rng, old_label):
        return host._complete_minor_breakthrough(game, rng, old_label)

    def forward_ensure_sage_state(game):
        return host._ensure_sage_state(game)

    def forward_haoran_manual_gain(origin_realm, previous, level):
        return host._haoran_manual_gain(origin_realm, previous, level)

    def forward_load(game_id):
        return host._load(game_id)

    def forward_major_breakthrough_requirement(player):
        return host._major_breakthrough_requirement(player)

    def forward_outer_advance_block_reason(game):
        return host._outer_advance_block_reason(game)

    def forward_outer_cost(action, player):
        return host._outer_cost(action, player)

    def forward_outer_target(player):
        return host._outer_target(player)

    def forward_player_doctrine(game, world=_OMITTED):
        if world is _OMITTED:
            return host._player_doctrine(game)
        if world is not _OMITTED:
            return host._player_doctrine(game, world)

    def forward_rank_members(doctrine):
        return host._rank_members(doctrine)

    def forward_refresh_sage_effects(game):
        return host._refresh_sage_effects(game)

    def forward_sage_world(game, world=_OMITTED):
        if world is _OMITTED:
            return host._sage_world(game)
        if world is not _OMITTED:
            return host._sage_world(game, world)

    def forward_start_breakthrough_trial(game, kind, source, target, old_label, *, major, rng):
        return host._start_breakthrough_trial(game, kind, source, target, old_label, major=major, rng=rng)

    def forwardpresent(game):
        return host.present(game)

    return SageActionsDependencies(
        _get_store=lambda: host.store,
        _add_opportunity=forward_add_opportunity,
        _combat=forward_combat,
        _complete_major_breakthrough=forward_complete_major_breakthrough,
        _complete_minor_breakthrough=forward_complete_minor_breakthrough,
        _ensure_sage_state=forward_ensure_sage_state,
        _haoran_manual_gain=forward_haoran_manual_gain,
        _load=forward_load,
        _major_breakthrough_requirement=forward_major_breakthrough_requirement,
        _outer_advance_block_reason=forward_outer_advance_block_reason,
        _outer_cost=forward_outer_cost,
        _outer_target=forward_outer_target,
        _player_doctrine=forward_player_doctrine,
        _rank_members=forward_rank_members,
        _refresh_sage_effects=forward_refresh_sage_effects,
        _sage_world=forward_sage_world,
        _start_breakthrough_trial=forward_start_breakthrough_trial,
        present=forwardpresent,
    )


def bind_sage_society(host) -> SageSocietyDependencies:
    def forward_add_opportunity(player, amount, regional_efficiencies=_OMITTED, *, apply_efficiency=_OMITTED):
        keywords = {}
        if apply_efficiency is not _OMITTED:
            keywords["apply_efficiency"] = apply_efficiency
        if regional_efficiencies is _OMITTED:
            return host._add_opportunity(player, amount, **keywords)
        if regional_efficiencies is not _OMITTED:
            return host._add_opportunity(player, amount, regional_efficiencies, **keywords)

    def forward_advance_sage_society_year(game, rng):
        return host._advance_sage_society_year(game, rng)

    def forward_ensure_sage_state(game):
        return host._ensure_sage_state(game)

    def forward_normalize_sage_doctrine(doctrine, age, cfg):
        return host._normalize_sage_doctrine(doctrine, age, cfg)

    def forward_normalize_sage_member(member):
        return host._normalize_sage_member(member)

    def forward_player_doctrine(game, world=_OMITTED):
        if world is _OMITTED:
            return host._player_doctrine(game)
        if world is not _OMITTED:
            return host._player_doctrine(game, world)

    def forward_refresh_sage_effects(game):
        return host._refresh_sage_effects(game)

    def forward_sage_world(game, world=_OMITTED):
        if world is _OMITTED:
            return host._sage_world(game)
        if world is not _OMITTED:
            return host._sage_world(game, world)

    return SageSocietyDependencies(
        _add_opportunity=forward_add_opportunity,
        _advance_sage_society_year=forward_advance_sage_society_year,
        _ensure_sage_state=forward_ensure_sage_state,
        _normalize_sage_doctrine=forward_normalize_sage_doctrine,
        _normalize_sage_member=forward_normalize_sage_member,
        _player_doctrine=forward_player_doctrine,
        _refresh_sage_effects=forward_refresh_sage_effects,
        _sage_world=forward_sage_world,
    )


def bind_sage_view(host) -> SageViewDependencies:
    def forward_ensure_sage_state(game):
        return host._ensure_sage_state(game)

    def forward_haoran_manual_gain(origin_realm, previous, level):
        return host._haoran_manual_gain(origin_realm, previous, level)

    def forward_outer_advance_block_reason(game):
        return host._outer_advance_block_reason(game)

    def forward_outer_cost(action, player):
        return host._outer_cost(action, player)

    def forward_outer_target(player):
        return host._outer_target(player)

    def forward_player_doctrine(game, world=_OMITTED):
        if world is _OMITTED:
            return host._player_doctrine(game)
        if world is not _OMITTED:
            return host._player_doctrine(game, world)

    def forward_public_inner_outer(game):
        return host._public_inner_outer(game)

    def forward_rank_members(doctrine):
        return host._rank_members(doctrine)

    def forward_sage_world(game, world=_OMITTED):
        if world is _OMITTED:
            return host._sage_world(game)
        if world is not _OMITTED:
            return host._sage_world(game, world)

    return SageViewDependencies(
        _ensure_sage_state=forward_ensure_sage_state,
        _haoran_manual_gain=forward_haoran_manual_gain,
        _outer_advance_block_reason=forward_outer_advance_block_reason,
        _outer_cost=forward_outer_cost,
        _outer_target=forward_outer_target,
        _player_doctrine=forward_player_doctrine,
        _public_inner_outer=forward_public_inner_outer,
        _rank_members=forward_rank_members,
        _sage_world=forward_sage_world,
    )


def bind_character(host) -> CharacterDependencies:
    return CharacterDependencies(
        monster_validation=bind_monster_validation(host),
        demonic_preview=bind_demonic_preview(host),
        upper_institution=bind_upper_institution(host),
        buddhist_guard=bind_buddhist_guard(host),
        buddhist_state=bind_buddhist_state(host),
        concubine_queries=bind_concubine_queries(host),
        demonic_actions=bind_demonic_actions(host),
        demonic_combat=bind_demonic_combat(host),
        demonic_growth=bind_demonic_growth(host),
        demonic_puppet_rules=bind_demonic_puppet_rules(host),
        demonic_view=bind_demonic_view(host),
        family_actions=bind_family_actions(host),
        family_society=bind_family_society(host),
        family_view=bind_family_view(host),
        ghost_actions=bind_ghost_actions(host),
        ghost_state=bind_ghost_state(host),
        monster_evolution=bind_monster_evolution(host),
        natal_actions=bind_natal_actions(host),
        natal_state=bind_natal_state(host),
        natal_view=bind_natal_view(host),
        sage_actions=bind_sage_actions(host),
        sage_society=bind_sage_society(host),
        sage_view=bind_sage_view(host),
    )


def bind_monster_validation(host) -> MonsterValidationDependencies:
    return MonsterValidationDependencies(
        _manual_breakthrough_kind=lambda player: host._manual_breakthrough_kind(player),
    )


def bind_demonic_preview(host) -> DemonicPreviewDependencies:
    return DemonicPreviewDependencies(_load=lambda game_id: host._load(game_id))
