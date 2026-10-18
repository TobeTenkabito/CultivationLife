"""Regressions for six confirmed audits, using only disposable save roots.

Random overrides select legal rift landings/capture success. Actual annual,
combat, ownership, command validation and disk persistence remain unmodified.
"""
import copy
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.engine.world import regions
from cultivation_life.models import GameState, SectNpc, SectState
from cultivation_life.relationship_records import find_person
from cultivation_life.spatial_people import people, instance_of, accessible
from cultivation_life.regional_context import calendar_scope, CalendarGame
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.system import spatial
from cultivation_life.system.combat.npc_lifecycle import move_world
from cultivation_life.system.ghost import parades
from cultivation_life.system.ghost.calendar import advance_parade_year
from test_regional_rifts import node, enter
from test_travel_relationship_2160 import prepare_journey
from test_regional_audit_fixes import dismiss, finish_journey

ROOT = Path(__file__).resolve().parents[1]
SEED = 20261018

@pytest.fixture
def engine(tmp_path):
    return GameEngine(ROOT, tmp_path)

def local_game(engine):
    game = engine._load(engine.create_game('后续隔离查验', 'none', 'dao', SEED)['id'])
    game.pending_event = None
    game.settings.update(silent_events=True, guixu_event_popup=False)
    game.player.realm_index, game.player.layer = 4, 1
    game.player.lifespan = 10000
    game.player.next_tribulation_age = None
    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
    regions.ensure(engine._dependencies.regions, game)
    return game


def local_jump(engine, game, location):
    target = node(engine, game, 'spirit')
    locations = engine.maps.worlds[game.player.world]['locations']
    original = random.Random.choice
    def select(rng, values):
        if values is locations:
            return next(row for row in values if row['id'] == location)
        return original(rng, values)
    # Select only the naturally available local branch and its random landing.
    with patch.object(random.Random, 'choice', select):
        response = enter(engine, game.id, target, 'local')
    return engine.store.load(game.id), response


def new(engine, lost=False):
    kwargs = dict(preset_id='lost_world') if lost else dict(custom_start=dict(world='demon',realm_index=4,layer=1))
    game = engine._load(engine.create_game('受控人物隔离审计','supreme_wood','demonic',SEED,**kwargs)['id'])
    game.pending_event = None
    game.settings.update(silent_events=True, guixu_event_popup=False)
    game.player.realm_index, game.player.layer = 4, 1
    game.player.opportunity, game.player.lifespan = 1000000, 100000
    game.player.next_tribulation_age = None
    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
    return game


def captive(game, identity, *, realm=1, power=100):
    row = game.detain_person(dict(id=identity,name='查验修士',realm_index=realm,layer=1,age=30,
        lifespan=110,world=game.player.world,spirit_root='supreme_wood',path='dao',
        combat_power=power,affinity=100,source='combat'))
    game.player.prisoners.append(row)
    return row


def convert(engine, game, identity, kind='living'):
    engine.store.save(game)
    with patch.object(random.Random,'random',return_value=0):
        engine.captive_action(game.id,identity,kind)
    return engine.store.load(game.id)


def test_late_child_snapshot_matches_original_after_personal_replay(engine):
    game = local_game(engine)
    migrant = SectNpc('audit-late-child', '迟归后人', '族人', 1, 1, 30, 32,
        world='human', faction_id='audit-late-family', spirit_root='none', encountered_player=True)
    guardian = SectNpc('audit-late-guardian', '留守族老', '族人', 3, 1, 200, 10000,
        world='human', faction_id='audit-late-family', spirit_root='none', encountered_player=True)
    migrant.family_traits['kin'] = True
    guardian.family_traits['kin'] = True
    game.family = SectState('audit-late-family', '迟归查验家族', 'human', [migrant, guardian],
        kind='family', founded_by_player=True, founder_player_id=game.id, location_id='wudi_plain')
    game.family_state.update(reproduction_enabled=False, settled_age=game.player.age)
    game.player.offspring.append(dict(migrant.to_dict(), cultivation_started=True))
    cfg = WORLD_SYSTEMS.get('transcendent_combat', {})
    with calendar_scope(game, 'human', game.player.age):
        move_world(migrant, 'spirit', game.player.age, cfg)
    engine.store.save(game)
    engine.advance(game.id, 'rest', 1)
    game = engine._load(game.id)
    migrant = next(n for n in game.family.npcs if n.id == migrant.id)
    assert migrant.age == 30
    with calendar_scope(game, 'human', game.player.age):
        move_world(migrant, 'human', game.player.age, cfg)
    arrival = copy.deepcopy(game.world_simulation['arrivals'][migrant.id])
    # Real movement synchronizes the already current home region. Personal
    # catch-up runs without a new society year. Then return and read the UI.
    enter(engine, game.id, node(engine, game, 'demon'))
    game = engine.store.load(game.id)
    enter(engine, game.id, node(engine, game, 'human'))
    shown = engine.get_game(game.id)
    game = engine.store.load(game.id)
    migrant = next(n for n in game.family.npcs if n.id == migrant.id)
    child = next(c for c in shown['family']['offspring'] if c['id'] == migrant.id)
    roster = next(c for c in shown['family']['roster'] if c['id'] == migrant.id)
    result = dict(arrival=arrival, player_year=game.player.age,
        original=dict(age=migrant.age, alive=migrant.alive, death_reason=migrant.death_reason),
        shown_offspring=dict(age=child['age'], alive=child['alive'], death_reason=child.get('death_reason')),
        shown_roster=dict(age=roster['age'], alive=roster['alive'], death_reason=roster.get('death_reason')),
        arrival_consumed=migrant.id not in game.world_simulation.get('arrivals', {}))
    assert not migrant.alive and not child['alive']
    assert child['age'] == roster['age'] == migrant.age == 32
    engine.advance(game.id, 'rest', 1)
    shown = engine.get_game(game.id)
    later = engine.store.load(game.id)
    child = next(c for c in shown['family']['offspring'] if c['id'] == migrant.id)
    result['after_another_action'] = dict(player_year=later.player.age,
        child_age=child['age'], child_alive=child['alive'], family_extinct=later.family.extinct)
    assert not later.family.extinct and child['age'] == 32 and not child['alive']


def test_local_rift_cancels_route_and_refreshes_actual_market(engine):
    game = local_game(engine)
    destination, total = prepare_journey(engine, game)
    origin = game.player.location_id
    engine.travel_map(game.id, destination)
    dismiss(engine, game.id)
    game = engine._load(game.id)
    assert game.map_journey['completed'] == 1
    game, shown = local_jump(engine, game, 'expanse_human_2')
    assert game.map_journey is None
    assert game.player.location_id == game.market_location_id == 'expanse_human_2'
    assert shown['map']['current'] == 'expanse_human_2'
    snapshot = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError):
        engine.spatial_action(game.id, 'enter', {'target_id': 'expired-node'})
    assert engine.store._path(game.id).read_bytes() == snapshot
    game, _ = local_jump(engine, game, origin)
    assert game.map_journey is None and game.market_location_id == origin
    start = game.player.age
    game.settings.update(silent_events=True, guixu_event_popup=False)
    engine.store.save(game)
    final = finish_journey(engine, game.id, destination)
    assert final.player.age - start == total


def test_remote_parade_freezes_then_replays_without_personal_rewards(engine):
    game = local_game(engine)
    before = copy.deepcopy(parades.get(game, 'human'))
    human_year = game.world_simulation['regions']['human']['year']
    enter(engine, game.id, node(engine, game, 'spirit'))
    while (game := engine.store.load(game.id)).player.age <= before['end_age']:
        engine.advance(game.id, 'rest', 1)
    assert parades.get(game, 'human') == before
    assert game.world_simulation['regions']['human']['year'] == human_year
    assert parades.get(game, 'spirit')['world'] == 'spirit'
    # Historical society replay must never execute the personal captor hook.
    game.player.ghost_captor = dict(id='owner', followed_years=7, location_id=game.player.location_id)
    personal = copy.deepcopy(game.player.to_dict())
    with calendar_scope(game, 'human', human_year + 1):
        advance_parade_year(engine._dependencies.ghost_flows.calendar,
                            CalendarGame(game, 'human', human_year + 1), random.Random(1))
    assert game.player.to_dict() == personal
    game.player.ghost_captor = None
    engine.store.save(game)
    enter(engine, game.id, node(engine, game, 'human'))
    game = engine.store.load(game.id)
    assert parades.get(game)['world'] == 'human'
    assert parades.get(game)['settled_year'] == game.player.age
    assert parades.get(game)['start_age'] > before['start_age']
    snapshot = copy.deepcopy(game.to_dict())
    regions.synchronize(engine._dependencies.regions, game, ['human'])
    assert game.to_dict() == snapshot
    assert GameState.from_dict(game.to_dict()).to_dict() == game.to_dict()


def test_legacy_parade_adoption_does_not_replay_already_observed_years(engine):
    game = local_game(engine)
    enter(engine, game.id, node(engine, game, 'spirit'))
    engine.advance(game.id, 'rest', 1)
    game = engine.store.load(game.id)
    # The legacy implementation had only this global row, no per-world archive.
    game.ghost_parade = copy.deepcopy(parades.get(game, 'human'))
    game.world_simulation.pop('ghost_parades', None)
    old = game.ghost_parade
    # A schema-10 event previously processed at the personal clock, while its
    # society clock was still frozen. Only the new optional metadata is absent.
    old.update(start_age=game.player.age + 20, end_age=game.player.age + 25)
    for field in ('settled_year', 'realm_index', 'unit_years'):
        old.pop(field, None)
    baseline = copy.deepcopy(old)
    engine.store.save(game)
    enter(engine, game.id, node(engine, engine.store.load(game.id), 'human'))
    loaded = engine.store.load(game.id)
    current = parades.get(loaded)
    assert {k: current[k] for k in baseline} == baseline
    assert current['settled_year'] == loaded.player.age
    assert not current['souls']
    assert loaded.world_simulation['regions']['human']['year'] == loaded.player.age


@pytest.mark.parametrize('kind,field', [('mechanical', 'durability'), ('corpse', 'corpse_integrity')])
def test_zero_condition_puppet_rejects_spending_and_rewards_without_death_flag(engine, kind, field):
    game = new(engine)
    puppet = dict(id='zero', name='旧残傀', type=kind, alive=True, realm_index=1,
                  layer=1, combat_power=100, **{field: 0})
    game.player.puppets.append(puppet)
    engine.store.save(game)
    engine.get_game(game.id)
    before = engine.store._path(game.id).read_bytes()
    for action in ('devour', 'pill', 'technique', 'reinforce_control', 'infuse'):
        with pytest.raises(ValueError, match='毁坏'):
            engine.puppet_action(game.id, puppet['id'], action, 'missing')
        assert engine.store._path(game.id).read_bytes() == before
    engine.puppet_action(game.id, puppet['id'], 'dismiss')
    assert not engine.store.load(game.id).player.puppets


def test_stale_living_asset_cannot_override_actual_source_death(engine):
    from cultivation_life.npc_custody import kill_person
    game = new(engine)
    captive(game, 'dead-source')
    game = convert(engine, game, 'dead-source')
    puppet = game.player.puppets[0]
    kill_person(game, 'dead-source', '真实死亡')
    assert puppet['alive'] and puppet['control'] > 0
    engine.store.save(game)
    engine.get_game(game.id)
    before = engine.store._path(game.id).read_bytes()
    with pytest.raises(ValueError, match='毁坏'):
        engine.puppet_action(game.id, puppet['id'], 'devour')
    with pytest.raises(ValueError, match='毁坏'):
        engine.train_owned(game.id, puppet['id'], 'puppet', 'cultivation', 5)
    assert engine.store._path(game.id).read_bytes() == before
    engine.puppet_action(game.id, puppet['id'], 'dismiss')
    assert not find_person(engine.store.load(game.id), 'dead-source', include_inactive=True).alive


def test_legacy_held_spatial_reference_is_adopted_without_recreating_npc(engine):
    from cultivation_life.spatial_people import family_rosters
    game = new(engine, lost=True)
    scene = spatial.current(game)
    ids = list(scene['npc_ids'])
    families = copy.deepcopy(family_rosters(scene))
    target = people(game)[0]
    row = game.detain_person(dict(id=target.id, source='combat'))
    game.player.prisoners.append(row)
    # Previously held schema-10 people were still in this free roster.
    scene['npc_ids'] = ids
    scene.pop('families', None)
    target.roster_origin = [o for o in target.roster_origin if o['container'] != 'spatial']
    game = GameState.from_dict(game.to_dict())
    original = find_person(game, target.id, include_inactive=True)
    assert game.player.prisoners[0].person is original
    assert target.id not in spatial.current(game)['npc_ids']
    assert family_rosters(spatial.current(game)) == families
    engine.store.save(game)
    engine.captive_action(game.id, target.id, 'release')
    loaded = engine.store.load(game.id)
    assert spatial.current(loaded)['npc_ids'] == ids
    assert accessible(loaded, find_person(loaded, target.id, include_inactive=True))


@pytest.mark.parametrize('legacy', [False, True])
@pytest.mark.parametrize('lifespan', [110, None])
def test_living_puppet_keeps_paid_lifespan_when_released(engine, legacy, lifespan):
    game = new(engine)
    row = captive(game, 'life-target')
    row['lifespan'] = lifespan
    game = convert(engine, game, row['id'])
    puppet = game.player.puppets[0]
    if legacy:
        puppet.pop('age', None)
        puppet.pop('lifespan', None)
    engine.store.save(game)
    before = game.player.opportunity
    engine.train_owned(game.id, puppet['id'], 'puppet', 'cultivation', 5)
    trained = engine.store.load(game.id).player.puppets[0]
    assert trained['age'] == 30
    assert trained['lifespan'] == (200 if lifespan is not None else None)
    engine.puppet_action(game.id, puppet['id'], 'dismiss')
    game = engine.store.load(game.id)
    person = find_person(game, row['id'], include_inactive=True)
    assert (person.realm_index, person.layer) == (2, 3)
    assert person.lifespan == trained['lifespan']
    assert person.alive and person.roster_state == 'active'
    assert before - game.player.opportunity == 5


@pytest.mark.parametrize('kind', ['living', 'corpse'])
def test_real_battle_destroyed_puppet_cannot_be_consumed_or_sold(engine, kind):
    game = new(engine)
    captive(game, 'battle-target', realm=2, power=100)
    game = convert(engine, game, 'battle-target', kind)
    puppet = game.player.puppets[0]
    puppet['control' if kind == 'living' else 'corpse_integrity'] = 10.
    own = engine._player_battle_power(game)
    engine._combat(game, dict(target_name='强敌', target_power=own*1.5,
        target_realm_index=4, target_layer=1, combat_type='cultivator',
        members=[dict(name='强敌', power=own*1.5, realm_index=4, layer=1, path='dao', race='human')]),
        False, random.Random(19))
    assert not puppet['alive']
    game.player.hp = max(1, game.player.hp)
    game.auction_state = dict(status='black_market', world=game.player.world,
        location_id=game.player.location_id, lots=[], attendees=[], black_market_results=[])
    engine.store.save(game)
    shown = engine.get_game(game.id)
    assert not any(p['id'] == puppet['id'] for p in shown['auction_system']['black_market_sellable_puppets'])
    snapshot = engine.store._path(game.id).read_bytes()
    for action in ('devour', 'pill', 'technique', 'reinforce_control', 'infuse'):
        with pytest.raises(ValueError):
            engine.puppet_action(game.id, puppet['id'], action, 'missing')
        assert engine.store._path(game.id).read_bytes() == snapshot
    with pytest.raises(ValueError, match='毁坏|不接收活傀'):
        engine.sell_black_market_asset(game.id, 'puppet', puppet['id'])
    assert engine.store._path(game.id).read_bytes() == snapshot
    engine.puppet_action(game.id, puppet['id'], 'dismiss')
    game = engine.store.load(game.id)
    assert not game.player.puppets and not game.player.foreign_souls
    assert game.player.devouring_breakthrough_bonus == 0
    assert not find_person(game, 'battle-target', include_inactive=True).alive


@pytest.mark.parametrize('destination', ['same', 'spirit', 'other'])
def test_spatial_capture_detaches_and_release_uses_actual_instance(engine, destination):
    game = new(engine, lost=True)
    source = spatial.current(game)
    from cultivation_life.spatial_people import family_rosters
    family_memberships = copy.deepcopy(family_rosters(source))
    original_ids = list(source['npc_ids'])
    target = min((n for n in people(game) if n.alive), key=lambda n:n.realm_index)
    target.affinity, target.lifespan = 100, 100000
    identity, faction = target.id, target.faction_id
    engine.store.save(game)
    engine.contact_action(game.id, identity, 'friend')
    engine.begin_relationship_capture(game.id, 'friend', identity)
    with patch.object(random.Random, 'random', return_value=0):
        engine.choose(game.id, 'ambush', event_id='EVT_RELATION_CAPTURE_001')
        engine.choose(game.id, 'soul_seal', event_id='EVT_RELATION_CAPTURE_002')
    game = engine.store.load(game.id)
    held = find_person(game, identity, include_inactive=True)
    captured_age = held.age
    assert identity not in spatial.current(game)['npc_ids']
    assert family_rosters(spatial.current(game)) == family_memberships
    assert instance_of(game, identity) is None
    assert game.player.prisoners[0].person is held
    engine.advance(game.id, 'rest', 1)
    game = engine.store.load(game.id)
    assert find_person(game, identity, include_inactive=True).age == captured_age
    if destination != 'same':
        enter(engine, game.id, node(engine, game, 'spirit'))
        game = engine.store.load(game.id)
        if destination == 'other':
            enter(engine, game.id, node(engine, game, 'lost'))
            game = engine.store.load(game.id)
    actual_instance = game.spatial_state.get('current')
    engine.captive_action(game.id, identity, 'release')
    game = engine.store.load(game.id)
    person = find_person(game, identity, include_inactive=True)
    assert accessible(game, person) and instance_of(game, identity) == actual_instance
    assert person.faction_id == (faction if destination == 'same' else None)
    if destination != 'same':
        assert identity not in game.spatial_state['instances'][source['id']]['npc_ids']
    else:
        assert spatial.current(game)['npc_ids'] == original_ids
    assert family_rosters(game.spatial_state['instances'][source['id']]) == family_memberships
    engine.contact_action(game.id, identity, 'improve')
    game = engine.store.load(game.id)
    before = find_person(game, identity, include_inactive=True).age
    start = game.player.age
    engine.advance(game.id, 'rest', 1)
    game = engine.store.load(game.id)
    assert find_person(game, identity, include_inactive=True).age == before + game.player.age - start


