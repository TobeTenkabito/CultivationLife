"""Explicit user-requested domain/upstream scope, bound to final release inputs."""
import json
import argparse
import xml.etree.ElementTree as ET
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.release_evidence import inputs_digest, require
from cultivation_life.version import BASE_GAME_VERSION

TESTS=['tests/test_release_260.py','tests/test_release_251.py','tests/test_upper_voisinages.py',
       'tests/test_immortal_trials.py','tests/test_asura_manifestation.py',
       'tests/test_ghost_reincarnation_dlc.py','tests/test_monster_bloodline_system.py',
       'tests/test_release_212.py','tests/test_module_dependencies.py']

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


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--profile',choices=['legacy','economy','bugfix'],default='legacy')
    profile=parser.parse_args().profile
    tag=BASE_GAME_VERSION.replace('.','');before=inputs_digest(ROOT);runs=[]
    selected=BUGFIX_TESTS if profile=='bugfix' else ECONOMY_TESTS if profile=='economy' else TESTS
    if profile in {'economy','bugfix'}:
        jobs=[(f'related-tests-{i}',['-m','pytest',module,'-q','--tb=short',f'--junitxml=build/scoped-{tag}-{i}.xml'])
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
    jobs += [(name,[f'tests/{name}.py']) for name in browsers]
    for name,args in jobs:
        log=ROOT/f'build/{name}-{tag}.log'
        with log.open('w',encoding='utf-8') as stream:
            code=subprocess.call([sys.executable,'-X','utf8',*args],cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
        require(code==0,f'{name} failed; see {log}')
        require(inputs_digest(ROOT)==before,'Release source changed during checks')
        runs.append(dict(name=name,log=str(log.relative_to(ROOT)),status='passed'))
        print(name+' passed',flush=True)
    if profile in {'economy','bugfix'}:
        combined=ET.Element('testsuites')
        for i in range(len(selected)):
            for suite in ET.parse(ROOT/f'build/scoped-{tag}-{i}.xml').getroot().iter('testsuite'): combined.append(suite)
        ET.ElementTree(combined).write(ROOT/f'build/scoped-{tag}.xml',encoding='utf-8',xml_declaration=True)
    (ROOT/f'build/scoped-{tag}.json').write_text(json.dumps(dict(version=BASE_GAME_VERSION,inputs_sha256=before,
        profile=profile,scope='User-requested economic, related interaction and release tests only; not full repository regression' if profile=='economy' else 'User-requested related and upstream tests only; not full repository regression',tests=selected,runs=runs),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
