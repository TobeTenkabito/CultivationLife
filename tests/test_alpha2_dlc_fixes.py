"""Alpha.2: truthful Guixu tooltips and real opponent artifact intelligence."""
import copy
import math
import random
from dataclasses import asdict, replace
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.content_registry import ITEM_CATALOG, TECHNIQUE_CATALOG
from cultivation_life.engine import GameEngine
from cultivation_life.guixu_items import describe, recovery_profile, material_potency
from cultivation_life.rules import add_item, max_hp, max_mp
from cultivation_life.system.tianji.npcs import _tianji_combat_clues

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fight(tmp_path):
    engine = GameEngine(ROOT, tmp_path/'saves')
    identity = engine.create_game('神机交锋验收', 'heavenly', 'dao', 622, preset_id='core')['id']
    game = engine.store.load(identity)
    game.pending_event = None
    add_item(game.player, 'starfall_blade', 10000)
    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
    artifact_id, holder = next(iter(game.tianji_state['holders'].items()))
    target = dict(npc_id=holder['npc_id'], target_name='持宝同道', target_power=100,
                  combat_type='cultivator', target_realm_index=game.player.realm_index)
    return engine, game, artifact_id, holder, target


@pytest.mark.parametrize('kind', ['true_body', 'replica'])
@pytest.mark.parametrize('level', [0, 1, 2, 3, 4, 5])
def test_actual_combat_advances_exactly_one_level_for_both_holder_kinds(fight, kind, level):
    engine, game, artifact_id, holder, target = fight
    holder['kind'] = kind
    game.tianji_state['knowledge'][artifact_id] = level
    engine._combat(game, target, False, random.Random(65))
    assert game.last_combat_report['rounds']
    assert holder['npc_id'] in {r['id'] for r in game.last_combat_report['enemy_roster']}
    assert game.tianji_state['knowledge'][artifact_id] == min(5, level+1)
    assert game.tianji_state['holders'][artifact_id] == holder
    if level<5:
        assert game.tianji_state['discovery_log'][-1]['from'] == level
        assert ('仿制品' if kind=='replica' else '真体') in game.tianji_state['discovery_log'][-1]['source']
    engine.store.save(game)
    restored = engine.store.load(game.id)
    before = copy.deepcopy(restored.tianji_state)
    for _ in range(3):
        engine.get_game(game.id)
    assert engine.store.load(game.id).tianji_state == before


def test_preview_injection_and_blocked_combat_do_not_grant_intelligence(fight):
    engine, game, artifact_id, holder, target = fight
    before = copy.deepcopy(game.tianji_state)
    engine._tianji_preview_npc_power(game, target)
    engine._inject_tianji_npc_artifacts(game, target)
    engine._inject_tianji_npc_artifacts(game, target)
    assert game.tianji_state == before
    game.player.combat_techniques = [copy.deepcopy(TECHNIQUE_CATALOG['TECH_BASIC_QI'])]
    with patch('cultivation_life.engine.engine_combat_runtime.can_player_practice_technique', return_value=False):
        result, _ = engine._combat(game, target, False, random.Random(65))
    assert result == 'technique_blocked'
    assert game.tianji_state == before


def test_same_artifact_once_per_actual_fight_and_all_real_opponents_not_display_cap(fight):
    engine, game, artifact_id, holder, target = fight
    definitions = game.tianji_state['artifacts'][:5]
    people = [n for n in game.world_npcs.values() if n.alive and n.world==game.player.world][:5]
    assert len(people)==5
    game.tianji_state['holders'] = {r['id']:dict(npc_id=n.id,kind='replica',replica_ratio=.3,world=game.player.world)
                                    for r,n in zip(definitions,people)}
    game.tianji_state['knowledge'] = {r['id']:2 for r in definitions}
    target['npc_id'] = people[0].id
    target['members'] = [dict(npc_id=n.id,name=n.name,power=100) for n in people]
    duplicate = copy.deepcopy(game)
    engine._tianji_combat_clues(duplicate, [dict(id=people[0].id),dict(id=people[0].id)])
    assert duplicate.tianji_state['knowledge'][definitions[0]['id']] == 3
    for repeat in range(2):
        engine._combat(game, copy.deepcopy(target), False, random.Random(65))
        assert all(game.tianji_state['knowledge'][r['id']] == 3+repeat for r in definitions)
    assert len(game.last_combat_report['visual']['teams']['npc']) == 3


def test_disabled_and_nonparticipating_holders_are_not_revealed(fight):
    engine, game, artifact_id, holder, target = fight
    before = copy.deepcopy(game.tianji_state)
    engine._tianji_combat_clues(game, [dict(id='somebody-else')])
    deps = replace(engine._dependencies.tianji.npcs, tianji_content_available=lambda:False)
    _tianji_combat_clues(deps, game, [dict(id=holder['npc_id'])])
    assert game.tianji_state == before


def test_intelligence_does_not_change_damage_ownership_or_rng(fight):
    engine, game, artifact_id, holder, target = fight
    a,b = copy.deepcopy(game),copy.deepcopy(game)
    ra,rb = random.Random(65),random.Random(65)
    first = engine._combat(a,copy.deepcopy(target),False,ra)
    with patch.object(engine,'_tianji_combat_clues'):
        second = engine._combat(b,copy.deepcopy(target),False,rb)
    assert first == second and ra.getstate() == rb.getstate()
    assert a.last_combat_report == b.last_combat_report
    a.tianji_state['knowledge'] = b.tianji_state['knowledge']
    a.tianji_state['discovery_log'] = b.tianji_state['discovery_log']
    assert a.to_dict() == b.to_dict()


def test_every_guixu_item_explains_actual_passive_active_and_material_uses():
    rows = [r for r in ITEM_CATALOG.values() if 'guixu_tide' in r.tags]
    assert len(rows) == 440
    for item in rows:
        text = item.description
        assert text == describe(item)
        if any((item.hp_bonus,item.mp_bonus,item.combat_bonus,item.opportunity_bonus)):
            assert '携带每件' in text and '承载' in text
        if {'guixu_consumable','spirit_plant'}.intersection(item.tags):
            assert '消耗1件' in text and '真实境界基础机缘' in text and '不永久增加上限' in text
            recovery,opportunity = recovery_profile(item)
            assert f'{recovery:.2%}' in text and f'{opportunity:.2%}' in text
        if {'crafting_material','spirit_plant'}.intersection(item.tags):
            assert all(word in text for word in ('主材','辅材','淬火','布阵','消耗原物'))
            assert f'{material_potency(item):.2%}' in text
    ordinary = copy.deepcopy(ITEM_CATALOG['healing_pill'])
    assert describe(ordinary) == ordinary.description


def test_shared_description_formulae_preserve_all_original_values():
    for item in ITEM_CATALOG.values():
        if 'guixu_tide' not in item.tags:
            continue
        if 'guixu_consumable' in item.tags:
            n = max(1,int(item.id.rsplit('_',1)[-1]))
            assert recovery_profile(item) == (min(.55,.18+n*.035),.20+n*.04)
        elif 'spirit_plant' in item.tags:
            n = max(1.,math.log10(max(10.,float(item.plant_value or 10))))
            assert recovery_profile(item) == (min(.45,.08+n*.04),min(.90,.10+n*.06))
        n = max(.02,min(.30,math.log10(max(10.,float(item.plant_value or item.combat_bonus or 10)))*.035))
        assert material_potency(item) == n


def test_old_inventory_descriptions_refresh_without_changing_item_stats(fight):
    engine, game, *_ = fight
    add_item(game.player,'guixu_canghai_equipment_01',2)
    item = next(r for r in game.player.inventory if r.id=='guixu_canghai_equipment_01')
    item.description = '只写了来历的旧说明'
    before = asdict(item)
    engine.store.save(game)
    shown = engine.get_game(game.id)
    public = next(r for r in shown['player']['inventory'] if r['id']==item.id)
    assert public['description'] == ITEM_CATALOG[item.id].description
    assert {k:v for k,v in public.items() if k!='description'} == {k:v for k,v in before.items() if k!='description'}
