from unittest.mock import patch
"""Base-world acquisition, growth, resources and neutral combat projection."""
import copy
import random

import pytest

from test_immortal_cultivation import prepared
from cultivation_life.models import Player
from cultivation_life.rules import add_item, max_hp, max_mp, opportunity_required
from cultivation_life.system.upper_voisinage import (
    config, public_upper_voisinages, player_source, quote, world_config,
)
from cultivation_life.system.combat.contracts import Combatant, CombatCapabilities, resolve_source
from cultivation_life.system.combat.voisinages import VoisinageBattle
from cultivation_life.system.immortal_aperture import energy_state, public_aperture
from cultivation_life.system.crafting_system import crafting_material_definitions, make_crafting_material_instance


@pytest.fixture(params=['asura', 'nether', 'reincarnation'])
def upper(prepared, request):
    e, g, _ = prepared
    p = g.player
    p.world = request.param
    p.location_id = e.maps.normalize_location(p.world, None)
    p.immortal_power_converted = True
    p.opportunity = opportunity_required(p)
    p.hp, p.mp = max_hp(p), max_mp(p)
    g.doctrine_state = {}
    e.store.save(g)
    return e, e._load(g.id)


def test_acquire_switch_and_nine_levels_are_persistent_and_bounded(upper):
    e, g = upper
    world = world_config(g.player)
    key, other = [r['id'] for r in world['fields']]
    age = g.player.age
    before = quote(g.player, 1)
    e.upper_voisinage_action(g.id, 'train', key)
    saved = e._load(g.id)
    assert saved.player.opportunity == opportunity_required(saved.player) - before['opportunity']
    assert player_source(saved.player).voisinages[0].id == key
    assert not saved.doctrine_state
    e.upper_voisinage_action(g.id, 'train', other)
    e.upper_voisinage_action(g.id, 'select', other)
    assert player_source(e._load(g.id).player).voisinages[0].id == other
    definition = crafting_material_definitions()[world['material_id']]
    for target in range(2, 10):
        saved = e._load(g.id)
        saved.player.realm_index = config()['realms'][target - 1]
        saved.player.opportunity = opportunity_required(saved.player)
        add_item(saved.player, 'spirit_stone', 10**8)
        for _ in range(config()['material_counts'][target - 1]):
            saved.player.crafting_materials.append(make_crafting_material_instance(definition, random.Random(1), source='test', origin_world=g.player.world))
        e.store.save(saved)
        e.upper_voisinage_action(g.id, 'train', key)
    saved = e._load(g.id)
    assert saved.player.age == age
    assert saved.player.world_voisinages[g.player.world]['levels'] == {key: 9, other: 1}
    with pytest.raises(ValueError, match='九级'):
        e.upper_voisinage_action(g.id, 'train', key)


def test_rejections_preserve_resources_and_materials(upper):
    e, g = upper
    key = world_config(g.player)['fields'][0]['id']
    g.player.world_voisinages[g.player.world] = {'levels': {key: 3}, 'active': key}
    e.store.save(g)
    before = e._load(g.id).to_dict()
    with pytest.raises(ValueError, match='第 10 阶'):
        e.upper_voisinage_action(g.id, 'train', key)
    assert e.store.load(g.id).to_dict() == before
    g = e._load(g.id)
    g.player.realm_index = 10
    g.player.opportunity = opportunity_required(g.player)
    e.store.save(g)
    before = e._load(g.id).to_dict()
    with pytest.raises(ValueError, match='材料不足'):
        e.upper_voisinage_action(g.id, 'train', key)
    assert e.store.load(g.id).to_dict() == before
    other_world = next(w for w in config()['worlds'] if w != g.player.world)
    with pytest.raises(ValueError, match='本界'):
        e.upper_voisinage_action(g.id, 'train', config()['worlds'][other_world]['fields'][0]['id'])
    with pytest.raises(ValueError, match='先领悟'):
        e.upper_voisinage_action(g.id, 'select', world_config(g.player)['fields'][1]['id'])


def test_material_consumption_prefers_lower_quality_without_substitutions(upper):
    e, g = upper
    p = g.player
    key = world_config(p)['fields'][0]['id']
    p.realm_index = 10
    p.opportunity = opportunity_required(p)
    p.world_voisinages[p.world] = {'levels': {key: 3}, 'active': key}
    definition = crafting_material_definitions()[world_config(p)['material_id']]
    m = make_crafting_material_instance(definition, random.Random(1), source='test', origin_world=p.world)
    p.crafting_materials = [dict(m, id='best', quality=1.2), dict(m, id='worn', quality=.7),
                            dict(m, id='rare', quality=.65, dynamic_definition=definition)]
    e.store.save(g)
    e.upper_voisinage_action(g.id, 'train', key)
    assert [m['id'] for m in e._load(g.id).player.crafting_materials] == ['best', 'rare']


def test_shared_combat_kernel_spends_actual_energy_and_domains_go_dormant(upper):
    from cultivation_life.engine.combat_capabilities import bind_capabilities
    from cultivation_life.system.combat_system import BattleUnit
    from cultivation_life.content_registry import WORLD_SYSTEMS
    e, g = upper
    key = world_config(g.player)['fields'][0]['id']
    e.upper_voisinage_action(g.id, 'train', key)
    g = e._load(g.id)
    energy = g.player.immortal_aperture['current'] = 500
    target = dict(target_name='测试敌手', target_power=100, target_realm_index=9, combat_type='cultivator')
    binding = bind_capabilities(g, [BattleUnit('player', g.player.name, 'player', 100, 9)], target, WORLD_SYSTEMS['transcendent_combat'])
    battle = binding.battle
    frame = battle.begin_round(1, player_condition=1, enemy_condition=1, player_mp=1, enemy_mp=1)
    assert frame.relations['enemy-0']['relation'] == 'dominated'
    assert battle.units['enemy-0'].vitality < 1
    binding.commit(battle.updates())
    assert 0 < g.player.immortal_aperture['current'] < energy
    ledger = copy.deepcopy(g.player.world_voisinages)
    world = g.player.world
    for away in ('celestial', 'spirit', next(w for w in config()['worlds'] if w != world)):
        g.player.world = away
        assert not player_source(g.player).voisinages
    g.player.world = world
    assert player_source(g.player).voisinages[0].id == key
    assert g.player.world_voisinages == ledger


def test_refinement_costs_local_origin_and_never_refills_on_reads(upper):
    e, g = upper
    p = g.player
    p.immortal_aperture['current'] = 0
    p.immortal_power_converted = False  # native worlds do not need celestial conversion
    e.store.save(g)
    before = public_aperture(p)
    assert before['conversion'] == 1 and before['native']
    e.aperture_action(g.id, 'refine')
    saved = e._load(g.id)
    assert saved.player.immortal_aperture['current'] == before['refine_gain']
    assert saved.player.mp < p.mp
    assert (saved.player.hp < p.hp) == (p.world == 'asura')
    snap = copy.deepcopy(saved.player.immortal_aperture)
    for _ in range(3):
        public_aperture(saved.player)
        public_upper_voisinages(saved.player)
        player_source(saved.player)
    assert saved.player.immortal_aperture == snap


def test_old_players_have_no_grant_and_unsupported_worlds_stay_hidden():
    p = Player.from_dict(Player('旧档', 'supreme_metal').to_dict())
    assert p.world_voisinages == {}
    for world in ['human', 'spirit', 'celestial']:
        p.world = world
        p.realm_index = 12
        assert not public_upper_voisinages(p)['available']
        assert not player_source(p).voisinages


def test_cultivation_rejects_death_short_resources_and_unknown_action(upper):
    e, g = upper
    key = world_config(g.player)['fields'][0]['id']
    for changes, action, message in [({'alive': False}, 'train', '当前状态'),
                                    ({'opportunity': 0}, 'train', '机缘不足'),
                                    ({'inventory': []}, 'train', '灵石不足'),
                                    ({}, 'unknown', '未知')]:
        original = copy.deepcopy(g)
        for attr, value in changes.items():
            setattr(original.player, attr, value)
        e.store.save(original)
        before = e._load(g.id).to_dict()
        with pytest.raises(ValueError, match=message):
            e.upper_voisinage_action(g.id, action, key)
        assert e.store.load(g.id).to_dict() == before


def test_all_configured_domains_project_and_grow_without_randomness():
    for world in config()['worlds']:
        p = Player('成长', 'supreme_metal', world=world, realm_index=12)
        for field in world_config(p)['fields']:
            previous = None
            for rank in range(1, 10):
                p.world_voisinages[world] = {'levels': {field['id']: rank}, 'active': field['id']}
                current = player_source(p).voisinages[0]
                if previous:
                    assert current.stability > previous.stability
                    assert current.incursion > previous.incursion
                    assert current.authority > previous.authority
                previous = current
        assert any('strike' in f['effects'] for f in world_config(p)['fields'])


@pytest.fixture(autouse=True)
def base_without_asura_dlc():
    with patch('cultivation_life.system.asura.enabled', return_value=False):
        yield
