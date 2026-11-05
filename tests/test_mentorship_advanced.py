"""Original actors, bounded benefits, real event submission and combat integration."""
import copy
import random
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from test_npc_development import game
from test_mentorship import school
from cultivation_life.models import GameState
from cultivation_life.engine import GameEngine
from cultivation_life.system import mentorship as m, mentorship_advanced as a
from cultivation_life.system.npc_development import service
from cultivation_life.system.npc_development.targets import candidates
from cultivation_life.npc_custody import retire_owned_people
from cultivation_life.rules import combat_power, add_item
from cultivation_life.engine.actions.mentorship import act


@pytest.fixture
def heir(game):
    row = m.admit(game, 'player', 'student')
    row.update(rank='heir', loyalty=100)
    return game


def deps(game, outcome='victory'):
    return SimpleNamespace(_npc_power=lambda n: combat_power(game.player),
                           _combat=Mock(return_value=(outcome, '实际战斗已结算。')),
                           _die=Mock())


def execute(game, action, identity='student', rng=None):
    return a.execute(deps(game), game, action, identity, rng or random.Random(1))


def make_avatar(game, consent=True):
    game.player.path = 'demonic'
    if consent: execute(game, 'pact_avatar')
    execute(game, 'refine_avatar')
    return a.avatar_person(game)


def test_contracts_save_original_id_and_reject_repeat(heir):
    execute(heir, 'pact_possession')
    row = m.record(heir, 'player', 'student')
    assert a.pact_valid(row, 'possession')
    before = copy.deepcopy(heir.to_dict())
    with pytest.raises(ValueError, match='本周期'): execute(heir, 'pact_possession')
    assert heir.to_dict() == before
    restored = GameState.from_dict(before)
    assert a.pact_valid(m.record(restored, 'player', 'student'), 'possession')
    execute(heir, 'revoke_pacts')
    assert not a.pact_valid(row, 'possession')
    with pytest.raises(ValueError, match='本周期'): execute(heir, 'pact_possession')


@pytest.mark.parametrize('change', [
    lambda g: m.record(g, 'player', 'student').update(loyalty=84),
    lambda g: m.record(g, 'player', 'student').update(rank='personal'),
    lambda g: setattr(g.world_npcs['student'], 'location_id', 'elsewhere'),
    lambda g: setattr(g.world_npcs['student'], 'world', 'spirit'),
    lambda g: setattr(g.world_npcs['student'], 'age', 17),
    lambda g: setattr(g, 'pending_event', {'id':'busy'}),
    lambda g: g.guixu_state.update(player_session={'trapped':False}),
])
def test_contract_boundaries_do_not_charge(heir, change):
    change(heir); before = copy.deepcopy(heir.to_dict())
    with pytest.raises(ValueError): execute(heir, 'pact_avatar')
    assert heir.to_dict() == before


def test_precision_uses_real_growth_cost_and_no_rank_refresh(heir):
    original = service.quote(heir, 'npc', 'student', 'body')
    quote = service.quote(heir, 'npc', 'student', 'body', 'inherit_infuse')
    assert quote['opportunity'] == round(original['opportunity'] / 2, 2)
    assert quote['result'] == original['result']
    for _ in range(3): service.apply(heir, 'npc', 'student', 'body', 'inherit_infuse')
    row = m.record(heir, 'player', 'student')
    row['rank'] = 'personal'; row['rank'] = 'heir'
    before = copy.deepcopy(heir.to_dict())
    with pytest.raises(ValueError, match='额度'): service.apply(heir, 'npc', 'student', 'body', 'inherit_infuse')
    assert heir.to_dict() == before
    row['cycle'] += 1
    assert a.precision(heir, 'student') == 3


def test_precision_material_rounding_and_invalid_batches(heir):
    material = 'npc_training_dao_body_1'; add_item(heir.player, material, 10)
    plan = service.quote(heir, 'npc', 'student', 'body', 'inherit_material')
    assert plan['material_count'] >= 1 and plan['opportunity'] == 0
    before = copy.deepcopy(heir.to_dict())
    with pytest.raises(ValueError, match='轮数'): service.apply(heir, 'npc', 'student', 'body', 'inherit_material', 2)
    assert heir.to_dict() == before
    normal = service.quote(heir, 'npc', 'student', 'body', 'material', 5)
    inherited = service.quote(heir, 'npc', 'student', 'body', 'inherit_material', 5)
    assert inherited['material_count'] == (normal['material_count'] + 1) // 2
    assert inherited['result'] == normal['result']


def test_avatar_conserves_actor_growth_and_outside_party(heir):
    original = heir.world_npcs['student']; before = original.body_training
    npc = make_avatar(heir)
    assert npc is original and npc is heir.inactive_npcs['student']
    assert 'student' not in heir.world_npcs and not heir.player.disciples
    assert npc.custody['kind'] == 'external_avatar'
    assert [t.identity for t in candidates(heir)].count('student') == 1
    assert a.avatar_unit(heir, lambda n:100).power == 120
    service.apply(heir, 'npc', npc.id, 'body')
    assert npc.body_training > before
    assert heir.player.party == []
    restored = GameState.from_dict(heir.to_dict())
    assert a.avatar_person(restored).body_training == npc.body_training
    execute(heir, 'avatar_toggle', '')
    assert a.avatar_unit(heir, lambda n:100) is None


def test_forced_avatar_has_no_consent_bonus(heir):
    make_avatar(heir, consent=False)
    assert a.avatar_unit(heir, lambda n:100).power == 100


@pytest.mark.parametrize('change', [
    lambda g: setattr(g.player, 'world', 'lost'),
    lambda g: setattr(g.player, 'world', 'rift'),
    lambda g: setattr(g.player, 'world', 'spirit'),
    lambda g: setattr(g.player, 'sealed_cultivation', {'realm_index':9}),
    lambda g: g.guixu_state.update(player_session={'trapped':False}),
    lambda g: setattr(g.inactive_npcs['student'], 'realm_index', 9),
    lambda g: setattr(g.inactive_npcs['student'], 'alive', False),
    lambda g: setattr(g.inactive_npcs['student'], 'spirit_state', {'mode':'wandering', 'body_intact':False}),
])
def test_avatar_boundaries_block_training_and_combat(heir, change):
    make_avatar(heir); change(heir)
    before = copy.deepcopy(heir.to_dict())
    assert a.avatar_unit(heir, lambda n:100) is None
    with pytest.raises(ValueError): service.apply(heir, 'npc', 'student', 'body')
    assert heir.to_dict() == before


def test_avatar_time_once_and_permanent_departure(heir):
    npc = make_avatar(heir); age = npc.age
    heir.player.age += 2; a.tick_avatar(heir); a.tick_avatar(heir)
    assert npc.age == age + 2
    retire_owned_people(heir)
    assert npc.alive and a.avatar_person(heir) is None
    assert a.avatar_unit(heir, lambda n:100) is None


def test_avatar_keeps_native_resource_owner_and_tribulation_clock(heir):
    npc = make_avatar(heir)
    from cultivation_life.content_registry import WORLD_SYSTEMS
    from cultivation_life.system.combat_adapter import bind_capabilities
    from cultivation_life.system.combat.npc_lifecycle import initialize_native
    from cultivation_life.system.combat_system import BattleUnit
    heir.player.world = npc.world = 'celestial'
    heir.player.realm_index = npc.realm_index = 9
    config = WORLD_SYSTEMS['transcendent_combat']
    initialize_native(npc, config, now=heir.player.age)
    npc.transcendence['current'] = 17
    units = [BattleUnit('player', '玩家', 'player', 100, 9), a.avatar_unit(heir, lambda n:100)]
    target = dict(target_name='测试对手',target_power=100,target_realm_index=9,path='dao',world='celestial')
    binding = bind_capabilities(heir, units, target, config)
    assert binding.owners[npc.id] is npc
    assert binding.resources[npc.id].ledger is npc.transcendence
    assert npc.transcendence['current'] == 17
    binding.commit([dict(id=npc.id, resource_link='independent', current=7,
                         vitality=.5, body=.7, suppressed=False)])
    assert npc.transcendence['current'] == 7 and npc.wounds == 2
    tick = Mock()
    heir.player.age += 1
    a.tick_avatar(heir, random.Random(1), tick)
    a.tick_avatar(heir, random.Random(1), tick)
    tick.assert_called_once()
    assert tick.call_args.args[1] is npc


def test_possession_contract_cannot_resurrect_or_bypass_count(heir):
    execute(heir, 'pact_possession')
    before = copy.deepcopy(heir.to_dict())
    with pytest.raises(ValueError, match='神游'): execute(heir, 'possess_heir')
    assert heir.to_dict() == before
    heir.player.spirit_state = {'mode':'wandering', 'body_intact':True}
    heir.player.possession_count = 100
    before = copy.deepcopy(heir.to_dict())
    with pytest.raises(ValueError, match='最多'): execute(heir, 'possess_heir')
    assert heir.to_dict() == before


def test_possession_uses_original_body_and_retires_original_actor(heir):
    execute(heir, 'pact_possession')
    heir.player.spirit_state = {'mode':'wandering', 'body_intact':True}
    original = heir.world_npcs['student']
    execute(heir, 'possess_heir')
    assert heir.player.possession_count == 1
    assert heir.player.ghost_host_body['npc_id'] == original.id
    assert not original.alive and not heir.player.disciples


def test_rebellion_warning_actual_event_and_stale_participants(heir):
    row = m.record(heir, 'player', 'student'); row['loyalty'] = 10
    port = deps(heir)
    port.events_by_id = {a.EVENT:{'id':a.EVENT}}
    port._instantiate_event = lambda event, game, rng: copy.deepcopy(event)
    a.maybe_rebellion(port, heir, random.Random(1))
    assert not heir.pending_event and heir.mentorship_state['rebellion']['ids'] == ['student']
    heir.player.age += row['period']
    a.maybe_rebellion(port, heir, random.Random(1))
    pending = heir.pending_event
    assert pending['id'] == a.EVENT
    heir.world_npcs['student'].location_id = 'elsewhere'
    outcome, _ = a.resolve_rebellion(port, heir, pending, 'fight', random.Random(1))
    assert outcome == 'dispersed' and not port._combat.called


def test_rebellion_real_members_debuff_and_surrender(heir):
    row = m.record(heir, 'player', 'student');row['loyalty'] = 10
    port = deps(heir)
    pending = {'id':a.EVENT, 'runtime':{'rebels':['student']}}
    a.resolve_rebellion(port, heir, pending, 'fight', random.Random(1))
    target = port._combat.call_args.args[1]
    assert target['mentorship_betrayal'] and target['player_defending']
    assert target['exclude_allied_ids'] == ['student']
    assert target['members'][0]['npc_id'] == 'student'
    assert not heir.player.disciples


def test_recovery_resets_warning_without_resetting_cooldown(heir):
    row = m.record(heir, 'player', 'student');row['loyalty'] = 10
    port = deps(heir);a.maybe_rebellion(port, heir, random.Random(1))
    row['loyalty'] = 60; heir.player.age += row['period']
    a.maybe_rebellion(port, heir, random.Random(1))
    assert heir.mentorship_state['rebellion']['ids'] == []
    row['loyalty'] = 10;a.maybe_rebellion(port, heir, random.Random(1))
    assert not heir.pending_event


def test_player_plot_requires_contact_and_transfers_only_personal_school(school):
    m.admit(school, 'teacher', 'player')
    peer = next(k for k in m.rows(school, 'teacher') if k != 'player')
    npc = m.person(school, peer);npc.affinity = 80
    row = m.record(school, 'teacher', peer);row['loyalty'] = 20
    execute(school, 'plot', peer)
    own_sect = school.player.faction_id
    old_npc = npc
    port = deps(school)
    a.execute(port, school, 'challenge_master', '', random.Random(1))
    assert school.player.master is None and school.player.faction_id == own_sect
    assert m.person(school, peer) is old_npc
    assert m.record(school, 'player', peer)['loyalty'] == 45
    assert port._combat.call_args.args[1]['mentorship_allies'] == [peer]


def test_registered_cannot_plot(school):
    m.admit(school, 'teacher', 'player')['rank'] = 'registered'
    with pytest.raises(ValueError, match='记名'): execute(school, 'challenge_master', '')


@pytest.mark.parametrize('state', [
    {'avatar':{'id':'student','consented':1,'enabled':True,'last_age':0}},
    {'rebellion':{'ids':['student','student'],'at':1,'cooldown_until':2}},
])
def test_malformed_persistent_state_rejected(game, state):
    document = game.to_dict();document['mentorship_state'] = state
    with pytest.raises(ValueError): GameState.from_dict(document)


def test_debug_uses_same_contract_training_and_avatar_actions(heir, tmp_path):
    from cultivation_life.debug.runtime import Runtime
    from cultivation_life.debug.capabilities import BY_OPERATION
    assert set(a.ACTIONS) <= set(next(arg.choices for arg in BY_OPERATION['mentorship-action'].arguments if arg.name == 'action'))
    engine = GameEngine(Path(__file__).resolve().parents[1], tmp_path/'normal')
    heir.player.path = 'demonic'
    heir.player.location_id = engine.maps.default_location('human')
    heir.world_npcs['student'].location_id = heir.player.location_id
    engine.store.save(heir)
    source = engine.store._path(heir.id).read_bytes()
    manager = Runtime(Path(__file__).resolve().parents[1], tmp_path/'debug', engine.store)
    sid = manager.start(heir.id)['session_id']
    def run(command, args, key):
        return manager.execute(command, arguments=args, session_id=sid,
                               expected_revision=manager.load(sid)['revision'], request_key=key)
    run('mentorship action', dict(action='pact_avatar', npc_id='student'), 'pact')
    run('npc development', dict(action='train',kind='npc',target_id='student',axis='body',method='inherit_infuse',batches=1), 'precision')
    run('mentorship action', dict(action='refine_avatar',npc_id='student'), 'refine')
    run('mentorship action', dict(action='avatar_toggle'), 'toggle')
    saved = GameState.from_dict(manager.load(sid)['current']['game'])
    assert a.avatar_person(saved).id == 'student'
    assert not saved.mentorship_state['avatar']['enabled']
    assert a.avatar_person(saved).body_training > heir.world_npcs['student'].body_training
    assert engine.store._path(heir.id).read_bytes() == source


def test_real_combat_and_event_submit(tmp_path):
    engine = GameEngine(Path(__file__).resolve().parents[1], tmp_path)
    view = engine.create_game('师徒战斗', 'supreme_metal', 'demonic', 123,
                              custom_start={'world':'human','realm_index':4,'layer':5,'sect':'new'})
    game = engine._load(view['id']);game.pending_event = None
    from cultivation_life.models import SectNpc
    npc = SectNpc('actual-avatar', '原弟子', '', 2, 3, 40, 500, world=game.player.world,
                  location_id=game.player.location_id, spirit_root='supreme_metal', body_training=10, divine_sense_rank=17)
    game.world_npcs[npc.id] = npc
    game.player.disciples.append(game.link_relationship({'id':npc.id}))
    m.admit(game, 'player', npc.id).update(rank='heir', loyalty=100)
    game.player.opportunity = 10**9
    a.execute(engine, game, 'refine_avatar', npc.id, random.Random(1))
    units = engine._player_combat_units(game)
    assert [u.id for u in units].count(npc.id) == 1
    assert next(u for u in units if u.id == npc.id).kind == 'external_avatar'
    enemy = SectNpc('actual-enemy', '来犯之人', '', 1, 1, 20, 200, world=game.player.world,
                    location_id=game.player.location_id, spirit_root='supreme_metal')
    game.world_npcs[enemy.id] = enemy
    target = a.battle_target(enemy, engine._npc_power)
    result, summary = engine._combat(game, target, False, random.Random(5))
    assert summary and result
    assert npc is a.avatar_person(game)
    visual = game.last_combat_report['visual']
    actor = next(r for r in visual['teams']['hero'] if r['id'] == npc.id)
    assert actor['kind'] == 'external_avatar' and actor['asset']
    # The official event loader and choice submit path must consume this event.
    game.pending_event = engine._instantiate_event(engine.events_by_id[a.EVENT], game, random.Random(1))
    game.player.disciples.append(game.link_relationship({'id':enemy.id}))
    m.admit(game, 'player', enemy.id).update(rank='true', loyalty=10)
    game.pending_event['runtime'] = {'rebels':[enemy.id]}
    engine.store.save(game)
    result = engine.choose(game.id, 'fight')
    assert engine.store.load(game.id).pending_event is None
    saved = engine.store.load(game.id)
    assert not saved.player.disciples
    assert saved.last_combat_report['player_defending']
    assert '快速结算' not in saved.last_combat_report['mode']
    assert saved.last_combat_report['visual']['teams']['npc'][0]['id'] == enemy.id
    # Permanent progression uses the existing authoritative retirement path.
    plan = engine._plan_world_transition(saved, 'spirit')
    engine._apply_world_transition(saved, plan)
    assert a.avatar_person(saved) is None
    assert saved.inactive_npcs[npc.id].roster_state == 'retired'
