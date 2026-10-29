"""Cross-world resource conservation and real command regression for audit fixes."""
import copy

import pytest

from test_other_systems_audit_fixes import api, snapshot
from test_spirit_inheritance import prepared
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.engine.combat_capabilities import bind_capabilities
from cultivation_life.system.combat_system import BattleUnit
from cultivation_life.system.doctrine.provider import _npc_record
from cultivation_life.system.immortal_aperture import public_aperture
from cultivation_life.system.possession_system import enter_host_body, leave_host_body


def battle(game, **target):
    return bind_capabilities(game, [BattleUnit('player', '验收', 'player', 10000, 9)],
        dict(target_name='石像', target_power=1, target_realm_index=8, **target),
        WORLD_SYSTEMS['transcendent_combat'])


def start_round(binding, number=1):
    binding.battle.begin_round(number, player_condition=1, enemy_condition=1, player_mp=1, enemy_mp=1)


def activated_doctrine(game):
    key = next(k for k in game.doctrine_state['definitions'] if k.startswith('celestial:'))
    record = game.doctrine_state['player']
    record['progress'][key] = {'level': 4, 'experience': 0}
    record['voisinage_training'][key] = {'rank': 1}
    record['active'] = key
    return key


def enter_test_host(game):
    # Structure 11 starts in the body; possession requires the normal soul state first.
    from cultivation_life.system.soul_lifecycle import leave_body
    leave_body(game)
    enter_host_body(game.player, dict(id='audit-host', name='借身', race='human', path='dao',
        realm_index=9, layer=1, spirit_root='supreme_metal', alive=True, age=100,
        lifespan=None, opportunity=10**9))


@pytest.mark.parametrize('source_world', ['asura', 'nether', 'reincarnation'])
def test_personal_inheritance_does_not_change_npc_initialization(api, source_world):
    engine, act = api
    original, book = prepared(engine, source_world=source_world)
    original = copy.deepcopy(original)
    rng_before = original.rng_state
    # Preserve the same pre-initialization NPC facts on both sides of the real command.
    actors = [dict(id=str(i), world='celestial', realm_index=10, layer=1, alive=True,
                  transcendence={'conversion': 1, 'capacity': 1000, 'current': 500}) for i in range(32)]
    before = [_npc_record(original, copy.deepcopy(npc)) for npc in actors]
    act(original.id, 'aperture-action', action='inherit', manual_id=book.id)
    expanded = engine._load(original.id)
    assert book.spirit_voisinage_id in expanded.doctrine_state['definitions']
    assert len(expanded.doctrine_state['definitions']) == len(original.doctrine_state['definitions']) + 1
    after = [_npc_record(expanded, copy.deepcopy(npc)) for npc in actors]
    assert after == before
    assert all(row['active'].startswith('celestial:') for row in after)
    assert expanded.rng_state == rng_before
    # Already recorded personal/scripted traditions remain legal; only the initial pool changes.
    learned = copy.deepcopy(actors[0])
    learned['transcendence']['doctrine'] = copy.deepcopy(before[0])
    assert _npc_record(expanded, learned) == before[0]


@pytest.mark.parametrize('stage', range(6))
def test_celestial_conversion_limits_combat_and_keeps_foreign_reserve(api, stage):
    engine, _ = api
    game, _ = prepared(engine, world='asura', path='dao')
    p = game.player
    p.immortal_power_converted = False
    p.immortal_conversion_stage = stage
    p.immortal_aperture['current'] = 500
    activated_doctrine(game)
    transition = engine._plan_world_transition(game, 'celestial', 'rift',
        route_id='rift:asura:celestial', reason='test_resource_adaptation')
    engine._apply_world_transition(game, transition)
    ledger_before = copy.deepcopy(p.immortal_aperture)
    shown = public_aperture(p, game)
    assert shown['conversion'] == stage / 5
    assert shown['capacity'] == 200 * stage
    assert shown['current'] == min(500, 200 * stage)
    binding = battle(game)
    unit = binding.battle.units['player']
    accessible = unit.current
    assert accessible == shown['current']
    binding.commit(binding.battle.updates())
    assert p.immortal_aperture == ledger_before  # No-round and repeat commits cannot destroy reserves.
    binding.commit(binding.battle.updates())
    assert p.immortal_aperture == ledger_before
    start_round(binding)
    spent = accessible - unit.current
    if stage == 0:
        assert unit.unit.capabilities.resource_tier == 1
        assert not binding.battle.fields and spent == 0
    elif stage >= 2:
        assert any(field.owner == 'player' for field in binding.battle.fields)
        assert spent > 0
    binding.commit(binding.battle.updates())
    assert p.immortal_aperture['current'] == pytest.approx(500 - spent)
    engine.store.save(game)
    assert engine._load(game.id).player.immortal_aperture == p.immortal_aperture


def test_partial_asura_conversion_preserves_actual_refined_foreign_reserve(api):
    engine, act = api
    game, _ = prepared(engine, world='nether', path='demonic')
    game.player.immortal_power_converted = False
    game.player.immortal_aperture['current'] = 0
    engine.store.save(game)
    for _ in range(4):
        act(game.id, 'aperture-action', action='refine')
    game = engine._load(game.id)
    assert game.player.immortal_aperture['current'] == 1000
    transition = engine._plan_world_transition(game, 'asura', 'rift',
        route_id='rift:nether:asura', reason='test_partial_conversion')
    engine._apply_world_transition(game, transition)
    game.player.asura_cultivation['conversion'] = 0
    engine.store.save(game)
    act(game.id, 'asura', action='convert')
    game = engine._load(game.id)
    assert game.player.asura_cultivation['conversion'] == 1
    binding = battle(game)
    assert binding.battle.units['player'].current == 200
    binding.commit(binding.battle.updates())
    assert game.player.immortal_aperture['current'] == 1000
    engine.store.save(game)
    assert engine._load(game.id).player.immortal_aperture['current'] == 1000


@pytest.mark.parametrize('stage', [0, 2, 5])
def test_asura_uses_its_own_conversion_and_preserves_unused_reserve(api, stage):
    engine, _ = api
    game, _ = prepared(engine, world='asura', path='demonic')
    # Completed foreign immortal conversion must not unlock unconverted asura energy.
    game.player.immortal_power_converted = True
    game.player.immortal_aperture['current'] = 1000
    game.player.asura_cultivation.update(conversion=stage, route='yaksha', level=4,
                                        domain_rank=1, domain_name='本命')
    shown = public_aperture(game.player, game)
    assert shown['conversion'] == stage / 5 and shown['current'] == stage * 200
    binding = battle(game)
    unit = binding.battle.units['player']
    assert unit.current == stage * 200
    assert unit.unit.capabilities.force_tier == (2 if stage else 1)
    binding.commit(binding.battle.updates())
    assert game.player.immortal_aperture['current'] == 1000
    start_round(binding)
    if stage == 0:
        assert not binding.battle.fields
    spent = stage * 200 - unit.current
    binding.commit(binding.battle.updates())
    assert game.player.immortal_aperture['current'] == pytest.approx(1000 - spent)


def test_partial_conversion_supply_only_refills_accessible_room(api):
    engine, _ = api
    game, _ = prepared(engine)
    game.player.immortal_power_converted = False
    game.player.immortal_conversion_stage = 3
    game.player.immortal_aperture['current'] = 1000
    activated_doctrine(game)
    binding = battle(game, resource_supplies=[dict(owner='player', amount=10000)])
    unit = binding.battle.units['player']
    assert unit.current == 600
    start_round(binding)
    spent = 600 - unit.current
    assert spent > 0
    start_round(binding, 2)
    assert unit.current <= 600
    binding.commit(binding.battle.updates())
    assert game.player.immortal_aperture['current'] == pytest.approx(400 + unit.current)
    assert game.player.immortal_aperture['current'] <= 1000


def test_lower_imitation_combat_keeps_upper_pool(api):
    from cultivation_life.system.aperture_resources import ensure_aperture
    from cultivation_life.system.spirit_voisinage import catalog, grant
    engine, _ = api
    made = engine.create_game('下界元府验收', 'supreme_metal', 'dao', 591,
        custom_start=dict(world='spirit', realm_index=6, layer=1))
    game = engine._load(made['id'])
    game.pending_event = None
    book = next(iter(catalog(game).values()))
    grant(game, book.id, 9)
    ensure_aperture(game.player)
    ledger = game.player.immortal_aperture
    ledger.update(current=500, imitation_current=60)
    binding = battle(game)
    assert binding.battle.units['player'].current == 60
    start_round(binding)
    remaining = binding.battle.units['player'].current
    assert remaining < 60
    binding.commit(binding.battle.updates())
    assert ledger['current'] == 500 and ledger['imitation_current'] == remaining


@pytest.mark.parametrize('operation,payload', [
    ('immortal-action', dict(action='advance_voisinage')),
    ('immortal-action', dict(action='train_voisinage', axis='stability')),
    ('immortal-action', dict(action='open_vein')),
    ('doctrine-action', dict(action='study')),
    ('doctrine-action', dict(action='activate')),
    ('doctrine-action', dict(action='convert')),
])
def test_possession_freezes_original_celestial_cultivation_atomically(api, operation, payload):
    engine, act = api
    game, _ = prepared(engine, path='ghost')
    key = activated_doctrine(game)
    original_opportunity = game.player.opportunity
    enter_test_host(game)
    engine.store.save(game)
    frozen = snapshot(engine, game.id)
    assert engine.get_game(game.id)['doctrines']['cultivation_blocked']
    result = act(game.id, operation, doctrine_id=key, status=400, **payload)
    assert '寄身' in str(result)
    assert engine.store._path(game.id).read_bytes() == frozen
    saved = engine._load(game.id)
    leave_host_body(saved.player)
    assert saved.player.path == 'ghost' and saved.player.opportunity == original_opportunity
    assert saved.doctrine_state['player']['voisinage_training'][key]['rank'] == 1
    engine.store.save(saved)
    act(game.id, 'immortal-action', action='advance_voisinage', doctrine_id=key)
    assert engine._load(game.id).doctrine_state['player']['voisinage_training'][key]['rank'] == 2
