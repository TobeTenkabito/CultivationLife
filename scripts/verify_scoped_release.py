"""Explicit user-requested domain/upstream scope, bound to final release inputs."""
import json
import os
import argparse
import xml.etree.ElementTree as ET
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.release_evidence import inputs_digest, require
from cultivation_life.version import BASE_GAME_VERSION

AUTHORED_TESTS = [
    'tests/test_authored_techniques.py','tests/test_technique_leveling.py','tests/test_common_elemental_techniques.py',
    'tests/test_economy_v2.py','tests/test_auction_update.py','tests/test_relationship_records.py',
    'tests/test_relationship_story_update.py','tests/test_npc_custody.py','tests/test_doctrines.py',
    'tests/test_voisinage_effects.py','tests/test_combat_semantics.py','tests/test_player_combat_system.py',
    'tests/test_persistence_pipeline.py','tests/test_save_transfer.py','tests/test_extension_system.py',
    'tests/test_world_transition_system.py','tests/test_spatial_talismans.py','tests/test_release_211.py','tests/test_release_212.py',
    'tests/test_base_game_version.py','tests/test_module_dependencies.py','tests/test_android_packaging.py',
    'tests/test_windows_release_evidence.py','tests/test_android_release_checks.py',
]
SOUL_TESTS = list(dict.fromkeys(AUTHORED_TESTS + [
    'tests/test_hunt_beasts.py','tests/test_historical_skins.py','tests/test_achievement_stories.py',
    'tests/test_humorous_achievements.py','tests/test_strategic_peace.py','tests/test_release_290.py',
    'tests/test_tide_skins.py','tests/test_ui_preferences.py','tests/test_achievements.py','tests/test_secret_art_training.py',
    'tests/test_soul_lifecycle.py','tests/test_swimwear_skins.py','tests/test_ghost_system.py',
    'tests/test_ghost_phase_two.py','tests/test_ghost_reincarnation_dlc.py','tests/test_demonic_system.py',
    'tests/test_relationship_possession_audit_fixes.py','tests/test_immortal_cultivation.py',
    'tests/test_body_bounty_update.py','tests/test_combat_replay.py','tests/test_npc_social_update.py',
    'tests/test_frontier_skins.py','tests/test_release_301.py','tests/test_holiday_skins.py','tests/test_sect_tasks.py','tests/test_survival_settlement.py',
    'tests/test_intrigue_system.py','tests/test_organization_economy.py','tests/test_war_logistics.py',
    'tests/test_domain_styles.py','tests/test_visual_release.py','tests/test_pixel_assets.py',
]))
AUTHORED_BROWSERS = ['browser_authored_techniques','browser_npc_art','browser_common_elemental_techniques','browser_events_212']

UPDATE301_TESTS = [
    'tests/test_release_301.py', 'tests/test_common_elemental_techniques.py',
    'tests/test_concubine_system.py', 'tests/test_body_bounty_update.py',
    'tests/test_combat_calibration_2151.py', 'tests/test_player_combat_system.py',
    'tests/test_combat_replay.py', 'tests/test_visual_release.py', 'tests/test_pixel_assets.py',
    'tests/test_npc_social_assets.py', 'tests/test_npc_social_update.py',
    'tests/test_monster_civilizations.py', 'tests/test_monster_fox_visuals.py',
    'tests/test_path_character_visuals.py', 'tests/test_persistence_pipeline.py',
    'tests/test_world_transition_system.py', 'tests/test_spatial_talismans.py',
    'tests/test_release_211.py', 'tests/test_release_212.py', 'tests/test_base_game_version.py',
    'tests/test_save_transfer.py', 'tests/test_module_dependencies.py',
    'tests/test_android_packaging.py', 'tests/test_windows_release_evidence.py',
    'tests/test_android_release_checks.py',
]
UPDATE301_BROWSERS = ['browser_release_301', 'browser_npc_art', 'browser_monster_civilizations',
                      'browser_common_elemental_techniques', 'browser_combat_replay', 'browser_events_212']

TESTS=['tests/test_release_260.py','tests/test_release_251.py','tests/test_upper_voisinages.py',
       'tests/test_immortal_trials.py','tests/test_asura_manifestation.py',
       'tests/test_ghost_reincarnation_dlc.py','tests/test_monster_bloodline_system.py',
       'tests/test_release_212.py','tests/test_module_dependencies.py']

COMBAT_ALPHA_TESTS = [
    'tests/test_alpha2_dlc_fixes.py','tests/test_tianji_artifacts.py','tests/test_tianji_theme_rules.py',
    'tests/test_guixu_tide.py','tests/test_guixu_companions.py','tests/test_crafting_system.py',
    'tests/test_formation_system.py','tests/test_combat_replay.py','tests/test_visual_selection.py',
    'tests/test_player_combat_system.py','tests/test_combat_semantics.py','tests/test_domain_combat.py',
    'tests/test_visual_release.py','tests/test_pixel_assets.py','tests/test_ui_preferences.py',
    'tests/test_content_registry.py','tests/test_base_game_version.py','tests/test_module_dependencies.py',
    'tests/test_world_transition_system.py','tests/test_spatial_talismans.py','tests/test_release_211.py',
    'tests/test_release_212.py','tests/test_android_packaging.py','tests/test_windows_release_evidence.py',
    'tests/test_android_release_checks.py',
]

# Explicit alpha.3 user scope: changed presentation and its combat/persistence
# upstreams. Keep the original full visual profile available by default.
VISUAL_ALPHA3_TESTS = [
    'tests/test_domain_replay.py','tests/test_domain_combat.py','tests/test_voisinage_effects.py',
    'tests/test_combat_semantics.py','tests/test_player_combat_system.py','tests/test_combat_replay.py',
    'tests/test_immortal_trials.py','tests/test_asura_manifestation.py','tests/test_upper_voisinages.py',
    'tests/test_voisinage_appearance.py','tests/test_ui_preferences.py','tests/test_npc_social_assets.py',
    'tests/test_pixel_assets.py','tests/test_visual_release.py','tests/test_visual_selection.py','tests/test_npc_social_update.py',
    'tests/test_base_game_version.py','tests/test_save_transfer.py','tests/test_release_212.py',
    'tests/test_android_packaging.py','tests/test_windows_release_evidence.py','tests/test_android_release_checks.py',
    'tests/test_module_dependencies.py','tests/test_world_transition_system.py',
    'tests/test_spatial_talismans.py','tests/test_release_211.py',
]

VISUAL_ALPHA4_TESTS = list(dict.fromkeys(VISUAL_ALPHA3_TESTS + [
    'tests/test_realm_appearance.py','tests/test_monster_fox_visuals.py','tests/test_monster_serpent_visuals.py',
    'tests/test_monster_static_assets.py','tests/test_monster_turtle_visuals.py','tests/test_monster_insect_visuals.py',
    'tests/test_monster_aquatic_visuals.py','tests/test_monster_flora_visuals.py','tests/test_monster_bloodline_system.py',
    'tests/test_extension_system.py','tests/test_content_registry.py',
]))

ECONOMY_TESTS = ['tests/test_economy_trust.py','tests/test_economy_estate_audit.py',
    'tests/test_economy_enterprises.py','tests/test_economy_network.py','tests/test_economy_governance.py',
    'tests/test_organization_economy.py','tests/test_organization_balance.py',
    'tests/test_family_expansion.py::test_finance_in_base_game_and_only_local_cash',
    'tests/test_family_expansion.py::test_financial_debt_funding_and_expulsion_persist',
    'tests/test_family_expansion.py::test_sect_appointment_preserves_family_and_ages_member_once',
    'tests/test_initial_array_positions.py','tests/test_world_transition_system.py','tests/test_spatial_talismans.py',
    'tests/test_release_211.py','tests/test_release_212.py','tests/test_base_game_version.py',
    'tests/test_android_packaging.py','tests/test_windows_release_evidence.py','tests/test_android_release_checks.py']

BUGFIX_TESTS = list(dict.fromkeys(ECONOMY_TESTS + [
    'tests/test_release_2135.py','tests/test_other_systems_audit_fixes.py','tests/test_relationship_possession_audit_fixes.py',
    'tests/test_economy_audit_round2.py','tests/test_economy_audit_followup.py',
    'tests/test_economy_audit_round3.py',
    'tests/test_owned_training.py','tests/test_upper_institutions.py','tests/test_secret_arts.py',
    'tests/test_ghost_phase_two.py','tests/test_ghost_reincarnation_dlc.py','tests/test_npc_custody.py',
    'tests/test_relationship_records.py','tests/test_relationship_story_update.py','tests/test_demonic_system.py',
    'tests/test_concubine_system.py','tests/test_guixu_tide.py','tests/test_time_flow.py',
    'tests/test_crafting_system.py','tests/test_formation_system.py','tests/test_persistence_pipeline.py',
    'tests/test_action_time_performance.py',
    'tests/test_spirit_inheritance.py','tests/test_inheritance_audit_fixes.py',
    'tests/test_repository_followup_fixes.py','tests/test_crafting_field_audit_fixes.py',
    'tests/test_ownership_prison_fixes.py','tests/test_custody_formation_fixes.py',
    'tests/test_guard_workforce_fixes.py','tests/test_territory_system.py',
    'tests/test_war_logistics.py','tests/test_war_performance_update.py']))

NAMING_TESTS = [
    'tests/test_content_naming.py', 'tests/test_content_registry.py', 'tests/test_technique_leveling.py',
    'tests/test_puppet_crafting.py', 'tests/test_auction_update.py', 'tests/test_ghost_reincarnation_dlc.py',
    'tests/test_monster_bloodline_system.py', 'tests/test_celestial_system.py', 'tests/test_family_expansion.py',
    'tests/test_extension_system.py', 'tests/test_economy_diversity.py', 'tests/test_economy_rebalance.py',
    'tests/test_crafting_system.py', 'tests/test_talisman_economy.py', 'tests/test_tianji_artifacts.py',
    'tests/test_tianji_theme_rules.py', 'tests/test_ghost_phase_two.py', 'tests/test_audit_regressions.py',
    'tests/test_merchant_138.py', 'tests/test_world_transition_system.py', 'tests/test_spatial_talismans.py',
    'tests/test_release_211.py', 'tests/test_release_212.py',
    'tests/test_strategic_war.py', 'tests/test_strategic_war_audit.py',
    'tests/test_war_negotiation_fixes.py', 'tests/test_war_coalition_fixes.py', 'tests/test_war_presence_fixes.py',
    'tests/test_war_logistics.py', 'tests/test_war_performance_update.py',
    'tests/test_base_game_version.py', 'tests/test_android_packaging.py',
    'tests/test_windows_release_evidence.py', 'tests/test_android_release_checks.py',
    'tests/test_strategic_dispatch.py', 'tests/test_strategic_peace.py',
]

NATAL_TESTS = [
    'tests/test_natal_materials_expansion.py', 'tests/test_natal_artifact_system.py',
    'tests/test_content_naming.py', 'tests/test_content_registry.py',
    'tests/test_auction_update.py', 'tests/test_merchant_commissions.py',
    'tests/test_merchant_execution.py', 'tests/test_family_expansion.py',
    'tests/test_voisinage_effects.py', 'tests/test_guixu_tide.py',
    'tests/test_crafting_system.py', 'tests/test_tianji_artifacts.py',
    'tests/test_ownership_prison_fixes.py', 'tests/test_repository_followup_fixes.py',
    'tests/test_world_transition_system.py', 'tests/test_spatial_talismans.py',
    'tests/test_release_211.py', 'tests/test_release_212.py',
    'tests/test_base_game_version.py', 'tests/test_android_packaging.py',
    'tests/test_windows_release_evidence.py', 'tests/test_android_release_checks.py',
]

TEACHINGS_TESTS = [
    'tests/test_upper_teachings.py', 'tests/test_buddhist_dharma.py', 'tests/test_buddhist_wish.py',
    'tests/test_sage_way_dlc.py', 'tests/test_sage_inner_outer.py', 'tests/test_sage_story_chains.py',
    'tests/test_key_flow_dependencies.py', 'tests/test_content_registry.py', 'tests/test_technique_leveling.py',
    'tests/test_celestial_system.py', 'tests/test_immortal_trials.py',
    'tests/test_world_transition_system.py', 'tests/test_spatial_talismans.py',
    'tests/test_release_211.py', 'tests/test_release_212.py', 'tests/test_base_game_version.py',
    'tests/test_android_packaging.py', 'tests/test_windows_release_evidence.py', 'tests/test_android_release_checks.py',
]


COMMON_TECHNIQUES_TESTS = [
    'tests/test_common_elemental_techniques.py', 'tests/test_technique_leveling.py',
    'tests/test_rules.py', 'tests/test_player_combat_system.py', 'tests/test_combat_semantics.py',
    'tests/test_economy_v2.py', 'tests/test_auction_update.py', 'tests/test_content_naming.py',
    'tests/test_content_registry.py', 'tests/test_key_flow_dependencies.py',
    'tests/test_world_transition_system.py', 'tests/test_spatial_talismans.py',
    'tests/test_release_211.py', 'tests/test_release_212.py', 'tests/test_base_game_version.py',
    'tests/test_android_packaging.py', 'tests/test_windows_release_evidence.py',
    'tests/test_android_release_checks.py', 'tests/test_module_dependencies.py',
]

COMMON_GOODS_TESTS = [
    'tests/test_combat_calibration_2151.py', 'tests/test_rules.py', 'tests/test_npc_system.py',
    'tests/test_release_240.py', 'tests/test_luo_spirit_story.py', 'tests/test_demon_world_story_expansion.py',
    'tests/test_core_dependencies.py',
    'tests/test_common_goods_2151.py', 'tests/test_secret_art_training.py',
    'tests/test_economy_v2.py', 'tests/test_economy_diversity.py', 'tests/test_economy_rebalance.py',
    'tests/test_action_time_performance.py', 'tests/test_economy_network.py',
    'tests/test_talisman_economy.py', 'tests/test_crafting_system.py',
    'tests/test_auction_update.py', 'tests/test_merchant_commissions.py',
    'tests/test_player_combat_system.py', 'tests/test_combat_semantics.py',
    'tests/test_content_registry.py', 'tests/test_common_elemental_techniques.py',
    'tests/test_world_transition_system.py', 'tests/test_spatial_talismans.py',
    'tests/test_release_211.py', 'tests/test_release_212.py', 'tests/test_base_game_version.py',
    'tests/test_android_packaging.py', 'tests/test_windows_release_evidence.py',
    'tests/test_android_release_checks.py', 'tests/test_module_dependencies.py',
    'tests/test_persistence_pipeline.py', 'tests/test_content_naming.py',
]


REGIONAL_TESTS = list(dict.fromkeys(BUGFIX_TESTS + [
    'tests/test_deferred_economy.py', 'tests/test_deferred_routing.py',
    'tests/test_regional_calendar.py', 'tests/test_travel_relationship_2160.py',
    'tests/test_regional_integration.py', 'tests/test_npc_system.py', 'tests/test_map_system.py',
    'tests/test_monster_civilizations.py',
    'tests/test_merchant_execution.py', 'tests/test_merchant_commissions.py',
    'tests/test_guixu_companions.py', 'tests/test_family_expansion.py',
    'tests/test_strategic_war.py', 'tests/test_strategic_war_audit.py',
    'tests/test_strategic_dispatch.py', 'tests/test_strategic_peace.py',
] + [str(p.relative_to(ROOT)).replace('\\','/') for p in sorted((ROOT/'tests').glob('test_heavens*.py'))]))


BUILDING_VISIT_TESTS = [
    'tests/test_city_management.py',
    'tests/test_building_visits.py','tests/test_building_system.py','tests/test_city_buildings.py',
    'tests/test_economy_enterprises.py','tests/test_economy_estate_audit.py','tests/test_economy_network.py',
    'tests/test_buddhist_dharma.py','tests/test_buddhist_wish.py','tests/test_upper_teachings.py',
    'tests/test_debug_capabilities.py','tests/test_debug_console.py','tests/test_persistence_pipeline.py',
    'tests/test_content_registry.py','tests/test_world_transition_system.py','tests/test_spatial_talismans.py',
    'tests/test_release_211.py','tests/test_release_212.py','tests/test_base_game_version.py',
    'tests/test_android_packaging.py','tests/test_windows_release_evidence.py','tests/test_android_release_checks.py',
    'tests/test_module_dependencies.py','tests/test_save_transfer.py',
]


def balanced_test_shards(modules, count, histories):
    """Use past durations for scheduling only; every selected module still runs."""
    stems={name:name.removesuffix('.py').replace('/','.') for name in modules}
    durations={name:0.0 for name in modules}
    for path in histories:
        if not path.is_file():continue
        for case in ET.parse(path).getroot().iter('testcase'):
            identity=case.get('classname','')
            module=next((name for name,stem in stems.items() if identity==stem or identity.startswith(stem+'.')),None)
            if module:durations[module]+=float(case.get('time','0'))
    shards=[[] for _ in range(count)];loads=[0.0]*count
    for module in sorted(modules,key=lambda name:(-durations[name],name)):
        target=min(range(count),key=lambda i:(loads[i],i))
        shards[target].append(module);loads[target]+=max(1.0,durations[module])
    flattened=[name for shard in shards for name in shard]
    require(len(flattened)==len(modules) and set(flattened)==set(modules),'Balanced scheduling changed test coverage')
    return shards


VISUAL_ALPHA5_TESTS = list(dict.fromkeys(VISUAL_ALPHA3_TESTS + [
    'tests/test_path_character_visuals.py','tests/test_monster_flora_visuals.py',
    'tests/test_buddhist_dharma.py','tests/test_buddhist_wish.py','tests/test_sage_way_dlc.py',
    'tests/test_ghost_reincarnation_dlc.py','tests/test_content_registry.py','tests/test_extension_system.py',
]))


VISUAL_ALPHA6_TESTS = list(dict.fromkeys(VISUAL_ALPHA3_TESTS + [
    'tests/test_home_scenes.py','tests/test_map_system.py','tests/test_building_system.py',
    'tests/test_city_buildings.py','tests/test_city_management.py','tests/test_building_visits.py',
    'tests/test_economy_network.py','tests/test_territory_system.py',
    'tests/test_path_character_visuals.py','tests/test_ghost_reincarnation_dlc.py',
    'tests/test_demonic_system.py','tests/test_extension_system.py',
]))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--profile',choices=['legacy','economy','bugfix','naming','natal','teachings','common-techniques','secret-arts','common-goods','regional','architecture','buildings','building-visits','visual','combat-alpha','update301','authored','soul-lifecycle'],default='legacy')
    parser.add_argument('--shards',type=int,choices=range(1,7),default=3)
    parser.add_argument('--workers',type=int,choices=range(1,7),default=4)
    parser.add_argument('--balance-tests',action='store_true',help='Schedule full regressions by prior XML timings; never reuse prior results')
    parser.add_argument('--focused-visual',action='store_true',help='Explicit alpha.3 changed-domain/upstream scope; no full regression claim')
    parser.add_argument('--monster-visuals',action='store_true',help='Alpha.4 eight-species appearance/combat and package isolation scope')
    parser.add_argument('--path-characters',action='store_true',help='Alpha.5 three-path hero/NPC art and optional package scope')
    parser.add_argument('--home-scenes',action='store_true',help='Alpha.6 home map modes, legacy layout, mirror actors and trial CG scope')
    options=parser.parse_args()
    if options.home_scenes and (not options.focused_visual or options.profile!='visual' or options.path_characters or options.monster_visuals):
        parser.error('--home-scenes requires visual --focused-visual, without other asset scopes')
    if options.path_characters and (not options.focused_visual or options.profile!='visual' or options.monster_visuals):
        parser.error('--path-characters requires visual --focused-visual, without --monster-visuals')
    if options.monster_visuals and (not options.focused_visual or options.profile!='visual'):
        parser.error('--monster-visuals requires --profile visual --focused-visual')
    profile=options.profile
    if options.focused_visual and profile!='visual':
        parser.error('--focused-visual requires --profile visual')
    tag=BASE_GAME_VERSION.replace('.','');before=inputs_digest(ROOT);runs=[]
    selected=TEACHINGS_TESTS if profile=='teachings' else NATAL_TESTS if profile=='natal' else NAMING_TESTS if profile=='naming' else BUGFIX_TESTS if profile=='bugfix' else ECONOMY_TESTS if profile=='economy' else TESTS
    if profile=='common-techniques':selected=COMMON_TECHNIQUES_TESTS
    if profile=='combat-alpha':selected=[COMBAT_ALPHA_TESTS[i::options.shards] for i in range(options.shards)]
    if profile=='soul-lifecycle':selected=[SOUL_TESTS[i::options.shards] for i in range(options.shards)]
    if profile=='authored':selected=[AUTHORED_TESTS[i::options.shards] for i in range(options.shards)]
    if profile=='update301':selected=[UPDATE301_TESTS[i::options.shards] for i in range(options.shards)]
    if profile=='common-goods':selected=[COMMON_GOODS_TESTS[i::3] for i in range(3)]
    if profile=='regional':selected=[REGIONAL_TESTS[i::options.shards] for i in range(options.shards)]
    if profile=='secret-arts':
        modules=[str(p.relative_to(ROOT)).replace('\\','/') for p in sorted((ROOT/'tests').rglob('test_*.py'))]
        selected=[modules[i::4] for i in range(4)]
    if profile in {'architecture','buildings','visual'}:
        modules=[str(p.relative_to(ROOT)).replace('\\','/') for p in sorted((ROOT/'tests').rglob('test_*.py'))]
        selected=[modules[i::options.shards] for i in range(options.shards)]
        if options.balance_tests:
            history=[ROOT/f'build/scoped-{tag}-{i}.xml' for i in range(options.shards)]
            if not any(p.is_file() for p in history):history=[ROOT/'build/scoped-2170.xml']
            selected=balanced_test_shards(modules,options.shards,history)
    if profile=='building-visits':selected=[BUILDING_VISIT_TESTS[i::options.shards] for i in range(options.shards)]
    if options.focused_visual:
        selected=[(VISUAL_ALPHA6_TESTS if options.home_scenes else VISUAL_ALPHA5_TESTS if options.path_characters else VISUAL_ALPHA4_TESTS if options.monster_visuals else VISUAL_ALPHA3_TESTS)[i::options.shards] for i in range(options.shards)]
    if profile in {'economy','bugfix','naming','natal','teachings','common-techniques','secret-arts','common-goods','regional','architecture','buildings','building-visits','visual','combat-alpha','update301','authored','soul-lifecycle'}:
        jobs=[(f'related-tests-{i}',['-m','pytest',*(module if isinstance(module,list) else [module]),'-q','--tb=short',
                                   '--maxfail=0' if profile in {'architecture','buildings'} or (profile=='visual' and not options.focused_visual) else '--maxfail=3',f'--junitxml=build/scoped-{tag}-{i}.xml'])
              for i,module in enumerate(selected)]
    else:
        jobs=[('related-tests',['-m','pytest',*selected,'-q','--tb=short',f'--junitxml=build/scoped-{tag}.xml'])]
    jobs += [(name,[f'tools/{name}.py']) for name in ['check_world_transition_contract','check_module_dependencies','check_documentation']]
    browsers=['browser_economy_trust','browser_economy_enterprises','browser_organization_economy','browser_events_212'] if profile=='economy' else ['browser_release_260','browser_release_251','browser_events_212']
    if profile=='bugfix':
        browsers=['browser_release_2135','browser_other_systems_audit_fixes','browser_relationship_possession_audit_fixes',
                   'browser_economy_round2','browser_economy_audit_followup','browser_economy_trust','browser_events_212',
                   'browser_spirit_inheritance','browser_inheritance_audit_fixes','browser_repository_followup_fixes',
                   'browser_crafting_field_audit_fixes','browser_ownership_prison_fixes',
                   'browser_custody_formation_fixes','browser_guard_workforce_fixes']
    if profile=='naming':
        browsers=['browser_content_naming','browser_strategic_war','browser_war_coalition_fixes',
                  'browser_war_presence_fixes','browser_events_212','browser_strategic_peace']
    if profile=='natal':
        browsers=['browser_natal_materials','browser_content_naming','browser_events_212']
    if profile=='teachings':
        browsers=['browser_upper_teachings','browser_events_212']
    if profile=='common-techniques':
        browsers=['browser_common_elemental_techniques','browser_events_212']
    if profile=='secret-arts':
        browsers=['browser_secret_art_training','browser_common_elemental_techniques','browser_merchant_138','browser_events_212']
    if profile=='common-goods':
        browsers=['browser_common_goods','browser_secret_art_training','browser_quick_start_1411','browser_events_212']
    if profile=='regional':
        browsers=['browser_regional_calendar','browser_economy_trust','browser_strategic_war','browser_events_212']
    if profile=='architecture':
        browsers=['browser_events_212','browser_release_251','browser_upper_teachings',
                  'browser_natal_materials','browser_regional_calendar','browser_regional_rifts',
                  'browser_custody_formation_fixes']
    if profile=='buildings':
        browsers=['browser_buildings','browser_city_buildings','browser_economy_enterprises','browser_events_212']
    if profile=='building-visits':
        browsers=['browser_building_visits','browser_buildings','browser_city_buildings','browser_economy_enterprises','browser_events_212']
    if profile=='visual':
        browsers=['browser_visual_release','browser_pixel_ui','browser_themes_139','browser_events_212','browser_building_visits','browser_npc_art','browser_voisinage_editor','browser_domain_replay','browser_combat_replay','browser_combat_groups']
    if profile=='combat-alpha':
        browsers=['browser_alpha2_dlc_fixes','browser_combat_replay','browser_combat_groups','browser_events_212']
    if profile=='soul-lifecycle':browsers=['browser_combat_groups','browser_combat_replay','browser_historical_skins','browser_story_achievements','browser_tide_theme','browser_themes_139','browser_desktop_navigation','browser_secret_art_training','browser_frontier_skins','browser_release_301','browser_soul_lifecycle','browser_swimwear_skins','browser_holiday_skins','browser_sect_tasks','browser_authored_techniques','browser_events_212']
    if profile=='authored':browsers=AUTHORED_BROWSERS
    if profile=='update301':browsers=UPDATE301_BROWSERS
    if options.monster_visuals:browsers += ['browser_monster_release','browser_monster_flora_visuals']
    if options.path_characters:browsers += ['browser_path_characters']
    if options.home_scenes:browsers += ['browser_home_scenes']
    if profile=='visual' and not options.focused_visual:
        browsers += ['browser_monster_release','browser_monster_flora_visuals','browser_path_characters',
                     'browser_asura_characters','browser_home_scenes','browser_spell_domains',
                     'browser_asura_prison','browser_trial_variants','browser_monster_aquatic_visuals',
                     'browser_monster_fox_visuals','browser_monster_insect_visuals',
                     'browser_monster_serpent_visuals','browser_monster_turtle_visuals']
    jobs += [(name,[f'tests/{name}.py']) for name in browsers]
    if profile=='common-goods':
        jobs.append(('combat-upstream',['tools/verify_combat_upstream_2151.py']))
    def run(job):
        name,args=job
        log=ROOT/f'build/{name}-{tag}.log'
        with log.open('w',encoding='utf-8') as stream:
            code=subprocess.call([sys.executable,'-X','utf8',*args],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,
                                 env=os.environ | ({} if profile=='soul-lifecycle' else {'CULTIVATION_BROWSER_LOW_MEMORY':'1'}))
        require(code==0,f'{name} failed; see {log}')
        require(inputs_digest(ROOT)==before,'Release source changed during checks')
        print(name+' passed',flush=True)
        return dict(name=name,log=str(log.relative_to(ROOT)),status='passed')
    if profile in {'secret-arts','common-goods','regional','architecture','buildings','building-visits','visual','combat-alpha','update301','authored','soul-lifecycle'}:
        # Isolate the declared selection while bounding host memory.
        with ThreadPoolExecutor(max_workers=options.workers) as executor:
            runs.extend(executor.map(run,jobs[:len(selected)]))
        jobs=jobs[len(selected):]
    for job in jobs:
        runs.append(run(job))
    if profile in {'economy','bugfix','naming','natal','teachings','common-techniques','secret-arts','common-goods','regional','architecture','buildings','building-visits','visual','combat-alpha','update301','authored','soul-lifecycle'}:
        combined=ET.Element('testsuites')
        for i in range(len(selected)):
            for suite in ET.parse(ROOT/f'build/scoped-{tag}-{i}.xml').getroot().iter('testsuite'): combined.append(suite)
        ET.ElementTree(combined).write(ROOT/f'build/scoped-{tag}.xml',encoding='utf-8',xml_declaration=True)
    (ROOT/f'build/scoped-{tag}.json').write_text(json.dumps(dict(version=BASE_GAME_VERSION,inputs_sha256=before,
        profile=profile,regression_scope='alpha6-focused' if options.home_scenes else 'alpha5-focused' if options.path_characters else 'alpha4-focused' if options.monster_visuals else 'alpha3-focused' if options.focused_visual else 'standard',scope='User-requested alpha.6 home map, event animation, mirror combat, buildings and related upstreams; not full repository regression' if options.home_scenes else 'User-requested alpha.5 ghost/Confucian/Buddhist hero and NPC art, optional package ownership and presentation/combat/persistence upstreams; not full repository regression' if options.path_characters else 'User-requested alpha.4 eight-species realm appearance, optional asset isolation and presentation/combat/persistence upstreams; not full repository regression' if options.monster_visuals else 'User-requested alpha.3 presentation, combat and persistence upstream tests; not full repository regression' if options.focused_visual else 'Full repository regression, optional pixel UI and original four-theme controls, real inventory/natal, eleven maps and event browser acceptance' if profile=='visual' else 'Full repository regression, eleven-world cities, building projects, finite event rewards, estates and real event browser acceptance' if profile=='buildings' else 'Full repository regression plus character, event and regional browser acceptance; explicit character composition' if profile=='architecture' else 'Full repository regression plus secret-art, common-technique and real event browser acceptance' if profile=='secret-arts' else 'User-requested economic, related interaction and release tests only; not full repository regression' if profile=='economy' else 'User-requested related and upstream tests only; not full repository regression',tests=selected,runs=runs),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
