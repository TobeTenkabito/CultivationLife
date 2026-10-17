"""Measured standards, genuine birth training and untouched attained lives."""
import copy
from pathlib import Path
import random

import pytest

from cultivation_life.content_registry import WORLD_SYSTEMS, REALMS
from cultivation_life.engine import GameEngine
from cultivation_life.models import Player, SectNpc
from cultivation_life.rules import combat_power, expected_combat_power, standard_combat_power_dlc_bonus
from cultivation_life.system.npc_system import npc_combat_power

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('rank,values', [
    (1,(140,188,236)), (2,(600,1000,1150)), (3,(2500,6100,8800)),
    (4,(35200,47700,64500)), (5,(194000,255000,317000)),
    (6,(1140000,1500000,1860000)), (7,(8400000,11100000,13900000)),
    (8,(46600000,60600000,74100000)),
    (9,(251000000,331320000,411640000)),
    (10,(990000000,1306800000,1623600000)),
    (11,(5580000000,7365600000,9151200000)),
    (12,(34900000000,46068000000,57236000000)),
])
def test_authored_stage_table_and_live_dlc_sum(rank,values):
    for layer,value in zip((1,5,9),values):
        assert expected_combat_power(rank,layer) == pytest.approx(value*(1+standard_combat_power_dlc_bonus()))
    assert WORLD_SYSTEMS['combat_expectations'] == WORLD_SYSTEMS['player_combat_recommendations']


def test_npc_reads_authoritative_table_without_mutating_character():
    npc = SectNpc('sample','sample','wanderer',7,5,3000,None,world='spirit')
    before = copy.deepcopy(npc)
    assert npc_combat_power(npc,expected_combat_power,1) == pytest.approx(round(expected_combat_power(7,5)*.98,1))
    assert npc == before


@pytest.mark.parametrize('preset,minimum', [
    ('nascent',43690), ('spirit',209898), ('void',1182498),
    ('monster_void',1040000), ('ghost_void',1043218), ('confucian_void',1133535),
    ('buddhist_void',1133535), ('demonic_void',1072769),
    ('integration',8552857), ('mahayana',45986323), ('true_immortal',586671812),
    ('asura_upper',292633679), ('nether_upper',292633679), ('reincarnation_upper',292633679),
])
def test_real_birth_and_reload_preserve_genuine_combat_books(tmp_path,preset,minimum):
    engine = GameEngine(ROOT,tmp_path)
    cfg = next(p for p in WORLD_SYSTEMS['quick_start_presets'] if p['id']==preset)
    made = engine.create_game('校准','supreme_metal','dao',2151,preset_id=preset,
        monster_species_id='fox' if cfg['path']=='monster' else None)
    game = engine._load(made['id'])
    assert combat_power(game.player) >= minimum
    assert all(t.level==cfg['combat_technique_level'] for t in game.player.combat_techniques)
    for identity in cfg.get('supplementary_combat_techniques',[]):
        assert any(t.id==identity for t in game.player.combat_techniques)
    # Loading an attained life must not reapply the birth preset.
    game.player.combat_techniques[0].level = 2
    for t in game.player.known_techniques:
        if t.id==game.player.combat_techniques[0].id:
            t.level = 2
    for t in (game.player.technique,game.player.support_technique):
        if t and t.id==game.player.combat_techniques[0].id:
            t.level = 2
    engine.store.save(game)
    assert engine._load(game.id).player.combat_techniques[0].level == 2


def test_custom_start_does_not_inherit_preset_training_or_supplements():
    from cultivation_life.engine.orchestration.custom_start import preset
    data = dict(realm_index=6,layer=1,world='spirit',inventory=[],additional_roots=[],
        body_training=0,divine_sense_rank=17,immortal_body_level=0)
    custom = preset(data,'supreme_metal','dao')
    assert not {'combat_technique_level','supplementary_combat_techniques','combat_techniques'} & custom.keys()


def test_story_ui_and_actual_threat_scale_once_but_luo_stays_independent(tmp_path):
    engine = GameEngine(ROOT,tmp_path)
    game = engine._load(engine.create_game('剧情','supreme_metal','dao',2151,preset_id='integration')['id'])
    event = engine.events_by_id['EVT_TWO_REALMS_002']
    choice = next(c for c in event['choices'] if c['id']=='hold')
    effect = next(e for e in choice['effects'] if e.get('type')=='attribute_check')
    check = next(c for c in effect['checks'] if c['stat']=='combat_power')
    assert check['value']==9800000 and '9,800,000' in choice['text']
    from types import SimpleNamespace
    from cultivation_life.engine.engine_event_runtime import _resolve_story_combat_check, _story_unit_full_power
    captured = []
    deps = SimpleNamespace(_story_unit_full_power=_story_unit_full_power,
        _combat=lambda game,target,lethal,rng:(captured.append(target) or 'victory',''))
    _resolve_story_combat_check(deps,effect,game,{'id':event['id'],'_choice_id':'hold'},random.Random(0))
    assert captured[0]['target_power']==9800000
    assert sum(m['power'] for m in captured[0]['members'])==pytest.approx(9800000)
    luo = engine.events_by_id['EVT_MA_LIANG_005']
    attack = next(c for c in luo['choices'] if c['id']=='attack_bottle')
    assert '124,000,000' in attack['text'] and '135,000,000' in luo['body']
    _resolve_story_combat_check(deps,attack['effects'][0],game,{'id':luo['id'],'_choice_id':'attack_bottle'},random.Random(0))
    assert captured[-1]['target_power']==55000000
