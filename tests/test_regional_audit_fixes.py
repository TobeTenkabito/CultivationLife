"""Public command regressions for frozen societies, journeys and living puppets.

Every game is disposable. Fixed RNG branches choose only a legal ascension or
passage/conversion; production time, identity, resource and save paths run.
"""
import copy
import random
from unittest.mock import patch

import pytest

from test_regional_calendar import regional, ROOT
from test_regional_rifts import node, enter
from test_travel_relationship_2160 import prepare_journey
from cultivation_life.engine import GameEngine
from cultivation_life.engine.world import regions
from cultivation_life.models import GameState, SectNpc, SectState
from cultivation_life.regional_context import CalendarGame
from cultivation_life.rules import add_item, learn_technique, max_hp, max_mp
from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.system.buddhist.rules import buddhist_config, site_state
from cultivation_life.system.teleport_system import public_teleport
from cultivation_life.time_flow import completed_action_units


def clan(game, members):
    game.family = SectState('audit-family', '验收家族', 'human', members, kind='family',
        founded_by_player=True, founder_player_id=game.id, location_id='wudi_plain')
    game.family_state.update(reproduction_enabled=False, settled_age=game.player.age)
    for npc in members:
        npc.family_traits['kin'] = True
    return game.family


def test_family_governance_freezes_then_replays_only_its_society(regional):
    engine, game = regional
    game.player.realm_index, game.player.layer = 4, 1
    home = SectNpc('audit-home', '留守', '族人', 1, 1, 20, 10000,
        world='human', faction_id='audit-family', spirit_root='none')
    clan(game, [home])
    baseline = game.player.age
    enter(engine, game.id, node(engine, game, 'spirit'))
    engine.advance(game.id, 'rest', 1)
    game = engine.store.load(game.id)
    assert game.player.age >= baseline + 3
    assert not game.family.extinct and game.family.pressure == 0
    assert game.family.npcs[0].age == home.age
    assert game.family_state['settled_age'] == baseline
    assert game.world_simulation['regions']['human']['year'] == baseline
    enter(engine, game.id, node(engine, game, 'human'))
    game = engine.store.load(game.id)
    assert game.family.extinct and game.family.pressure == 3
    assert game.family_state['settled_age'] == baseline + 3
    before = copy.deepcopy(game.to_dict())
    regions.synchronize(engine._dependencies.regions, game, ['human'])
    assert game.to_dict() == before


def test_family_governance_rejects_personal_replay_and_reverse_year(regional):
    engine, game = regional
    clan(game, [])
    game.family_state['settled_age'] = game.player.age + 5
    view = CalendarGame(game, 'human', game.player.age)
    assert engine._family_annual_governance(view, random.Random(1)) == []
    assert game.family.pressure == 0
    object.__setattr__(view, '_regional_single_person', 'audit-home')
    game.family_state['settled_age'] = game.player.age - 1
    assert engine._family_annual_governance(view, random.Random(1)) == []
    assert game.family.pressure == 0


@pytest.mark.parametrize('dies', [False, True])
def test_ascended_family_member_ages_in_destination_without_copy(regional, dies):
    engine, game = regional
    game.player.realm_index, game.player.layer = 4, 1
    game.player.hp, game.player.mp = max_hp(game.player), max_mp(game.player)
    migrant = SectNpc('audit-ascender', '飞升族人', '族人', 5, 3, 1210, 10000,
        world='human', faction_id='audit-family', spirit_root='supreme_wood', encountered_player=True)
    migrant.cultivation_progress = 100000
    home = SectNpc('audit-home', '留守', '族人', 3, 1, 200, 10000,
        world='human', faction_id='audit-family', spirit_root='supreme_wood', encountered_player=True)
    clan(game, [migrant, home])
    game.player.offspring.append(dict(migrant.to_dict(), cultivation_started=True))
    with patch.object(engine, '_npc_breakthrough_probability', return_value=1):
        game.player.age += 1
        regions.advance(engine._dependencies.regions, game, [])
    assert migrant.world == 'spirit'
    start_age, start_year = migrant.age, game.player.age
    if dies:
        migrant.lifespan = migrant.age + 1
    enter(engine, game.id, node(engine, game, 'spirit'))
    engine.advance(game.id, 'rest', 1)
    game = engine.store.load(game.id)
    original = next(n for n in game.family.npcs if n.id == migrant.id)
    assert original.age == start_age + (1 if dies else game.player.age - start_year)
    assert original.alive is not dies
    child = next(c for c in game.player.offspring if c['id'] == original.id)
    assert (child['world'], child['age'], child['alive'], child.get('death_reason')) == (
        original.world, original.age, original.alive, original.death_reason)
    assert original.id not in game.world_npcs and original.id not in game.notable_npcs
    restored = GameState.from_dict(game.to_dict())
    regions.synchronize(engine._dependencies.regions, restored, ['spirit'])
    assert restored.family.npcs[0].age == original.age


def dismiss(engine, identity):
    event = engine.get_game(identity)['pending_event']
    if event:
        choice = next(c['id'] for c in event['choices'] if c.get('enabled', True))
        engine.choose(identity, choice, event_id=event['id'])


def finish_journey(engine, identity, destination):
    for _ in range(30):
        game = engine.store.load(identity)
        if game.player.location_id == destination:
            return game
        if game.pending_event:
            dismiss(engine, identity)
        else:
            engine.travel_map(identity, destination)
    pytest.fail('journey did not complete')


@pytest.mark.parametrize('interrupt_on_arrival,legacy', [(False, False), (True, False), (False, True)])
def test_real_notification_and_reload_do_not_double_round_travel(regional, interrupt_on_arrival, legacy):
    engine, game = regional
    destination, years = prepare_journey(engine, game)
    if interrupt_on_arrival:
        dungeon = next(d for d in engine._guixu_definitions().values() if d['world'] == 'human')
        game.guixu_state['cycles'][dungeon['id']].update(next_announce_age=game.player.age + years,
            next_open_age=game.player.age + years + dungeon['announce_lead_years'])
        engine.store.save(game)
    age, units = game.player.age, game.diplomacy_unit
    engine.travel_map(game.id, destination)
    first = engine.store.load(game.id)
    assert first.map_journey['completed'] == (years if interrupt_on_arrival else 1)
    assert first.map_journey['unit_years'] == 5
    if legacy:
        first.map_journey.pop('unit_years')
        engine.store.save(first)
    after = finish_journey(engine, game.id, destination)
    assert after.player.age - age == years
    assert after.diplomacy_unit - units == completed_action_units(years, 5)
    assert after.map_journey is None


def test_teleport_cancels_old_journey_even_after_return(regional):
    engine, game = regional
    destination, years = prepare_journey(engine, game)
    origin = game.player.location_id
    engine.travel_map(game.id, destination)
    dismiss(engine, game.id)
    game = engine._load(game.id)
    assert game.map_journey['completed'] == 1
    add_item(game.player, 'spirit_stone', 100000)
    target = next(t['id'] for t in public_teleport(game, engine.maps)['destinations'] if t['id'] != destination)
    engine.store.save(game)
    # A rejected destination must preserve the valid unfinished journey.
    with pytest.raises(ValueError):
        engine.teleport_action(game.id, 'bribe', origin)
    assert engine.store.load(game.id).map_journey['completed'] == 1
    engine.teleport_action(game.id, 'bribe', target)
    assert engine.store.load(game.id).map_journey is None
    engine.teleport_action(game.id, 'bribe', origin)
    game = engine.store.load(game.id)
    assert game.map_journey is None
    game.settings.update(silent_events=True, guixu_event_popup=False)
    engine.store.save(game)
    start = game.player.age
    after = finish_journey(engine, game.id, destination)
    assert after.player.age - start == years


def upper_game(tmp_path, path):
    engine = GameEngine(ROOT, tmp_path / 'saves')
    game = engine._load(engine.create_game('异界教化', 'supreme_wood', path, 20261018,
        custom_start=dict(world='spirit', realm_index=6, layer=1))['id'])
    game.settings.update(silent_events=True, guixu_event_popup=False)
    game.pending_event = None
    game.player.lifespan = 100000
    game.player.next_tribulation_age = None
    regions.ensure(engine._dependencies.regions, game)
    return engine, game


@pytest.mark.parametrize('path', ['confucian', 'buddhist'])
def test_remote_teaching_freezes_then_catches_up_without_personal_rewards(tmp_path, path):
    engine, game = upper_game(tmp_path, path)
    if path == 'buddhist':
        site_state(game.buddhist_state, 'human', 'wudi_plain').update(temple=1, followers=1000.)
        engine._ensure_buddhist_state(game)
        state = game.buddhist_state
    else:
        state = game.sage_state
    before = copy.deepcopy(state['worlds']['human'])
    start = game.player.age
    engine.store.save(game)
    engine.advance(game.id, 'rest', 1)
    game = engine.store.load(game.id)
    state = game.buddhist_state if path == 'buddhist' else game.sage_state
    assert state['worlds']['human'] == before
    assert game.world_simulation['regions']['human']['year'] == start
    personal = (game.player.to_dict(), copy.deepcopy(game.buddhist_state.get('last_settlement')),
        copy.deepcopy(game.sage_state.get('action_result')))
    regions.synchronize(engine._dependencies.regions, game, ['human'])
    assert state['worlds']['human'] != before
    if path == 'buddhist':
        temple = buddhist_config()['temples'][1]
        assert state['worlds']['human']['sites']['wudi_plain']['followers'] == pytest.approx(
            max(temple['floor'], 1000. * (1-temple['decay']) ** (game.player.age-start)))
        assert game.buddhist_state['last_settlement']['age'] == game.player.age
    assert (game.player.to_dict(), game.buddhist_state.get('last_settlement'),
        game.sage_state.get('action_result')) == personal
    engine.store.save(game)
    restored = engine.store.load(game.id)
    before = copy.deepcopy(restored.to_dict())
    regions.synchronize(engine._dependencies.regions, restored, ['human'])
    assert restored.to_dict() == before


@pytest.mark.parametrize('path', ['confucian', 'buddhist'])
def test_legacy_teaching_adoption_does_not_replay_already_observed_years(tmp_path, path):
    engine, game = upper_game(tmp_path, path)
    if path == 'buddhist':
        site_state(game.buddhist_state, 'human', 'wudi_plain').update(temple=1, followers=1000.)
    engine.store.save(game)
    engine.advance(game.id, 'rest', 1)
    game = engine.store.load(game.id)
    state = game.buddhist_state if path == 'buddhist' else game.sage_state
    for network in state['worlds'].values():
        network.pop('settled_year', None)
    # Model an old schema-10 save: society records were observed at the current
    # age although their regional clock is still frozen in the past.
    engine.store.save(game)
    adopted = engine._load(game.id)
    state = adopted.buddhist_state if path == 'buddhist' else adopted.sage_state
    before = copy.deepcopy(state['worlds']['human'])
    assert before['settled_year'] == adopted.player.age
    regions.synchronize(engine._dependencies.regions, adopted, ['human'])
    assert state['worlds']['human'] == before
    adopted.player.age += 1
    regions.synchronize(engine._dependencies.regions, adopted, ['human'])
    assert state['worlds']['human'] != before


@pytest.mark.parametrize('axis', ['cultivation', 'body', 'sense'])
def test_living_puppet_replacement_never_stacks_and_preserves_paid_training(tmp_path, axis):
    engine = GameEngine(ROOT, tmp_path / 'saves')
    game = engine._load(engine.create_game('活傀复核', 'supreme_wood', 'demonic', 20261018,
        custom_start=dict(world='demon', realm_index=4, layer=1))['id'])
    game.pending_event = None
    game.player.body_training, game.player.divine_sense_rank = 80, 30
    game.player.opportunity, game.player.mp = 100000, max_mp(game.player)
    techniques = [copy.deepcopy(TECHNIQUE_CATALOG[i]) for i in ('TECH_BLOOD_RIVER', 'TECH_DEMON_BREATHING')]
    for technique in techniques:
        learn_technique(game.player, technique)
    game.player.prisoners.append(game.detain_person(dict(id='audit-source', name='活傀原身',
        realm_index=1, layer=1, age=30, lifespan=200, world='demon', spirit_root='supreme_wood',
        path='dao', combat_power=100, affinity=100, source='combat')))
    engine.store.save(game)
    with patch('random.Random.random', return_value=0):
        engine.captive_action(game.id, 'audit-source', 'living')
    game = engine.store.load(game.id)
    puppet = game.player.puppets[0]
    identity = puppet['id']
    a, b = (t.id for t in techniques)
    engine.puppet_action(game.id, identity, 'technique', a)
    initial = engine.store.load(game.id).player.puppets[0]['combat_power']
    for _ in range(3):
        before = engine.store._path(game.id).read_bytes()
        with pytest.raises(ValueError, match='已经修习'):
            engine.puppet_action(game.id, identity, 'technique', a)
        assert engine.store._path(game.id).read_bytes() == before
        engine.puppet_action(game.id, identity, 'technique', b)
        engine.puppet_action(game.id, identity, 'technique', a)
        assert engine.store.load(game.id).player.puppets[0]['combat_power'] == initial
    engine.train_owned(game.id, identity, 'puppet', axis, 1)
    trained = engine.store.load(game.id)
    trained_power = trained.player.puppets[0]['combat_power']
    assert trained_power > initial and trained.player.opportunity < 100000
    for _ in range(3):
        engine.puppet_action(game.id, identity, 'technique', b)
        engine.puppet_action(game.id, identity, 'technique', a)
        restored = engine.store.load(game.id)
        assert restored.player.puppets[0]['combat_power'] == trained_power
        assert restored.player.opportunity == trained.player.opportunity
        assert restored.player.mp == trained.player.mp and restored.player.age == trained.player.age
