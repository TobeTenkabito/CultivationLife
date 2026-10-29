"""Original people, paid cargo, regional ownership and actual command recovery."""
import copy
import random
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.rules import add_item, max_hp, max_mp
from cultivation_life.system.economy import depot, organizations
from cultivation_life.system.economy.ledger import balance
from cultivation_life.system.heavens import operations, outposts, outpost_runtime
from cultivation_life.system.heavens.calendar import year_step, YearContext
from cultivation_life.system.heavens.state import initialize
from cultivation_life.system.heavens.outpost_definitions import target, ENDPOINTS
from cultivation_life.person_assignments import research_assignment

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def frontier(tmp_path):
    engine = GameEngine(ROOT, tmp_path / 'saves')
    key = engine.create_game('异界开拓', 'heavenly', 'dao', 4242, preset_id='core')['id']
    game = engine.store.load(key)
    p = game.player
    p.realm_index, p.layer, p.lifespan = 3, 1, None
    p.next_tribulation_age = 999999
    p.world, p.location_id, p.faction_id = 'human', 'wudi_plain', 'tianjian'
    p.hp, p.mp = max_hp(p), max_mp(p)
    p.master, p.dao_companion, p.dao_friends, p.party = None, None, [], []
    game.settings['silent_events'] = True
    entity = game.sects['tianjian']
    entity.location_id, entity.founded_by_player, entity.founder_player_id = 'wudi_plain', True, key
    for npc in entity.npcs:
        npc.location_id, npc.realm_index, npc.lifespan = 'wudi_plain', 3, 99999
        npc.next_tribulation_age = 999999
    organizations.register(game, 'sect', entity.id, 'human')
    game.intrigue_state['factions']['sect:tianjian']['resources'] = 1000000
    game.intrigue_state['factions']['sect:tianjian']['controller_id'] = 'player'
    game.intrigue_state['factions']['sect:tianjian'].setdefault('positions', {})['leader'] = 'player'
    store = depot.ensure(game, entity)
    for identity, quantity in outpost_runtime.materials('human').items():
        store['stock'][identity] = quantity * 4
    add_item(p, 'spirit_stone', 100000)
    initialize(game)
    engine.store.save(game)
    deps = replace(engine._dependencies.heavens, load_game=engine.store.load)
    return engine, key, deps


def load(bundle):
    return bundle[0].store.load(bundle[1])


def act(bundle, action, options=None, object_id=None):
    engine, key, deps = bundle
    state = load(bundle).heavens_state
    return operations.command(deps, key, state['command_seq'] + 1, state['revision'],
                              action, object_id or target('tianjian'), options or {})


def quiet(bundle):
    engine, key, deps = bundle
    def advance(game, rng, news):
        outpost_runtime.year_step(deps, game)
        year_step(deps, game, YearContext(game.heavens_state['runtime']['last_year_key'] + 1))
        return True
    return engine, key, replace(deps, advance_year=advance, settle_activity_units=Mock())


def dispatch(bundle, action='outpost_dispatch'):
    game = load(bundle)
    person = bundle[2].outpost_candidates(game, game.sects['tianjian'])[0]['id']
    act(bundle, action, {'person_id': person})
    return person


def wait(bundle, years):
    for _ in range(years):
        act(bundle, 'outpost_wait')


def arrive(bundle):
    act(bundle, 'outpost_authorize')
    person = dispatch(bundle)
    wait(bundle, 8)
    assert load(bundle).world_npcs[person].world == 'demon'
    act(bundle, 'outpost_depart')
    return person


def test_real_paid_frontier_build_reload_supply_and_return(frontier):
    bundle = quiet(frontier)
    before = load(bundle)
    person = arrive(bundle)
    wait(bundle, 10)
    g = load(bundle)
    row = outpost_runtime.get(g, target('tianjian'))
    assert row['status'] == 'active' and row['progress'] == 10
    assert g.sects['tianjian'].world == 'human' and g.sects['tianjian'].location_id == 'wudi_plain'
    assert g.player.world == g.world_npcs[person].world == 'demon'
    assert g.world_npcs[person].id not in {n.id for n in g.sects['tianjian'].npcs}
    assert research_assignment(g, person)['phase'] == 'stationed'
    completed = next(h['year'] for h in row['history'] if '施工完成' in h['text'])
    local_cash = 10000 - (g.player.age - completed) * 100
    assert balance(g, outpost_runtime.wallet(row)) == local_cash
    assert depot.find(g, g.sects['tianjian'])['stock']['item:econ_human_2_ore_structure'] == before.economy_v2['depots']['human:tianjian:wudi_plain']['stock']['item:econ_human_2_ore_structure'] - 6
    assert row['stock']['item:econ_human_2_ore_structure'] == 0
    act(bundle, 'outpost_appoint', {'person_id': person})
    act(bundle, 'outpost_suspend')
    wait(bundle, 2)
    assert balance(load(bundle), outpost_runtime.wallet(row)) == local_cash
    act(bundle, 'outpost_activate')
    wait(bundle, 1)
    assert balance(load(bundle), outpost_runtime.wallet(row)) == local_cash - 100
    act(bundle, 'outpost_return')
    g = load(bundle)
    assert g.player.world == 'human' and g.player.faction_id == 'tianjian'
    courier = dispatch(bundle, 'outpost_supply')
    wait(bundle, 9)
    g = load(bundle)
    assert g.world_npcs[courier].world == 'demon'
    assert g.player.world == 'human'
    assert outpost_runtime.get(g, target('tianjian'))['visit']['return_fare'] == 0


def test_read_and_preview_are_pure_retry_does_not_pay_twice(frontier):
    bundle = quiet(frontier)
    act(bundle, 'outpost_authorize')
    g = load(bundle)
    identity = bundle[2].outpost_candidates(g, g.sects['tianjian'])[0]['id']
    path = bundle[0].store._path(bundle[1])
    before = path.read_bytes()
    operations.view(bundle[2], bundle[1], 'known', target('tianjian'))
    quote = operations.preview(bundle[2], bundle[1], 'outpost_dispatch', target('tianjian'), {'person_id': identity})
    assert quote['costs']['organization_stones'] == 21600
    assert path.read_bytes() == before
    state = load(bundle).heavens_state
    result = act(bundle, 'outpost_dispatch', {'person_id': identity})
    after = path.read_bytes()
    assert operations.command(bundle[2], bundle[1], state['command_seq'] + 1, state['revision'],
        'outpost_dispatch', target('tianjian'), {'person_id': identity}) == result
    assert path.read_bytes() == after
    with pytest.raises(ValueError, match='参数不一致'):
        operations.command(bundle[2], bundle[1], state['command_seq'] + 1, state['revision'],
            'outpost_supply', target('tianjian'), {'person_id': identity})


@pytest.mark.parametrize('block', ['pending', 'prison', 'poor', 'stock', 'busy', 'dead', 'foreign', 'stale'])
def test_rejection_is_atomic(frontier, block):
    bundle = quiet(frontier)
    act(bundle, 'outpost_authorize')
    g = load(bundle)
    identity = bundle[2].outpost_candidates(g, g.sects['tianjian'])[0]['id']
    if block == 'pending': g.pending_event = {'id': 'EVT_TEST', 'title': '占用事件', 'options': []}
    if block == 'prison': g.player.imprisonment = {'years': 1}
    if block == 'poor': g.intrigue_state['factions']['sect:tianjian']['resources'] = 0
    if block == 'stock': depot.find(g, g.sects['tianjian'])['stock'] = {}
    if block == 'busy': g.player.party = [{'id': identity, 'name': '原门人'}]
    if block == 'dead': next(n for n in g.sects['tianjian'].npcs if n.id == identity).alive = False
    if block == 'foreign': g.player.world, g.player.location_id = 'demon', 'red_marrow_city'
    bundle[0].store.save(g)
    before = bundle[0].store._path(bundle[1]).read_bytes()
    if block == 'stale':
        with pytest.raises(ValueError, match='过期'):
            operations.command(bundle[2], bundle[1], g.heavens_state['command_seq'] + 1, g.heavens_state['revision'] - 1,
                               'outpost_dispatch', target('tianjian'), {'person_id': identity})
    else:
        with pytest.raises(ValueError):
            act(bundle, 'outpost_dispatch', {'person_id': identity})
    assert bundle[0].store._path(bundle[1]).read_bytes() == before


def test_withdrawal_returns_original_cargo_and_clears_occupation(frontier):
    bundle = quiet(frontier)
    person = arrive(bundle)
    wait(bundle, 10)
    act(bundle, 'outpost_withdraw')
    wait(bundle, 9)
    assert load(bundle).world_npcs[person].world == 'human'
    act(bundle, 'outpost_return')
    wait(bundle, 1)
    g = load(bundle)
    row = outpost_runtime.get(g, target('tianjian'))
    assert row['units'][0]['phase'] == 'home'
    assert research_assignment(g, person) is None
    # The final closure is settled only on the owning destination calendar.
    from cultivation_life.regional_context import CalendarGame
    outpost_runtime.year_step(bundle[2], CalendarGame(g, 'demon', g.player.age + 1))
    assert row['status'] == 'closed'


def test_save_failure_rolls_back_actual_identity_and_money(frontier, monkeypatch):
    bundle = quiet(frontier)
    act(bundle, 'outpost_authorize')
    path = bundle[0].store._path(bundle[1])
    before = path.read_bytes()
    with monkeypatch.context() as scope:
        scope.setattr(bundle[0].store, 'save', Mock(side_effect=OSError('disk full')))
        with pytest.raises(OSError): dispatch(bundle)
    assert path.read_bytes() == before


def test_frozen_destination_cannot_build_before_actual_arrival_and_replay_is_once(frontier):
    from cultivation_life.regional_context import CalendarGame
    from cultivation_life.engine.world.regions import ensure
    original = load(frontier)
    ensure(frontier[0]._dependencies.regions, original)
    frontier[0].store.save(original)
    bundle = quiet(frontier)
    act(bundle, 'outpost_authorize')
    person = dispatch(bundle)
    wait(bundle, 9)
    g = load(bundle)
    row = outpost_runtime.get(g, target('tianjian'))
    age = row['units'][0]['last_year']
    for year in range(age - 8, age + 1):
        outpost_runtime.year_step(bundle[2], CalendarGame(g, 'demon', year))
    assert row['progress'] == 0
    assert row['units'][0]['person_id'] == person
    before = copy.deepcopy(g.to_dict())
    outpost_runtime.year_step(bundle[2], CalendarGame(g, 'demon', age))
    assert g.to_dict() == before
    outpost_runtime.year_step(bundle[2], CalendarGame(g, 'demon', age + 1))
    assert row['progress'] == 1


def test_two_original_people_share_one_lane_and_player_cannot_overtake(frontier):
    bundle = quiet(frontier)
    act(bundle, 'outpost_authorize')
    first, second = dispatch(bundle), dispatch(bundle)
    wait(bundle, 2)
    g = load(bundle)
    row = outpost_runtime.get(g, target('tianjian'))
    assert sorted(u['progress'] for u in row['units']) == [0, 2]
    before = bundle[0].store._path(bundle[1]).read_bytes()
    with pytest.raises(ValueError, match='通道'):
        act(bundle, 'outpost_depart')
    assert bundle[0].store._path(bundle[1]).read_bytes() == before
    wait(bundle, 7)
    g = load(bundle)
    assert sum(g.world_npcs[i].world == 'demon' for i in (first, second)) == 1
    wait(bundle, 8)
    g = load(bundle)
    assert all(g.world_npcs[i].world == 'demon' for i in (first, second))


def test_custody_pauses_crossing_and_death_never_replaces_original(frontier):
    bundle = quiet(frontier)
    act(bundle, 'outpost_authorize')
    person = dispatch(bundle)
    wait(bundle, 2)
    g = load(bundle)
    row = outpost_runtime.get(g, target('tianjian'))
    progress, purse = row['units'][0]['progress'], balance(g, row['units'][0]['wallet'])
    g.intrigue_state.setdefault('npc_prisons', {})[person] = {'test': True}
    bundle[0].store.save(g)
    wait(bundle, 2)
    g = load(bundle)
    unit = outpost_runtime.get(g, target('tianjian'))['units'][0]
    assert unit['progress'] == progress and balance(g, unit['wallet']) == purse
    g.intrigue_state['npc_prisons'].pop(person)
    g.world_npcs[person].alive = False
    bundle[0].store.save(g)
    wait(bundle, 1)
    g = load(bundle)
    unit = outpost_runtime.get(g, target('tianjian'))['units'][0]
    assert unit['phase'] == 'lost' and not g.world_npcs[person].alive
    assert unit['stock'] == {} and balance(g, unit['wallet']) == 0


def test_last_year_event_keeps_original_reward_and_zero_time_resume(frontier):
    bundle = quiet(frontier)
    act(bundle, 'outpost_authorize')
    dispatch(bundle)
    wait(bundle, 9)
    original = bundle[2].advance_year
    def interrupted(game, rng, news):
        outcome = original(game, rng, news)
        task = game.heavens_state['runtime']['tasks'][-1]
        if task['action'] == 'outpost_depart' and task['progress'] == 8:
            game.pending_event = bundle[0]._prepare_treasure_reward_event(game, random.Random(2))
            return False
        return outcome
    interrupted_bundle = bundle[0], bundle[1], replace(bundle[2], advance_year=interrupted)
    result = act(interrupted_bundle, 'outpost_depart')
    assert result['status'] == 'paused'
    g = load(bundle)
    assert g.player.world == 'human' and g.pending_event
    age = g.player.age
    event_id, choice = g.pending_event['id'], g.pending_event['choices'][0]['id']
    bundle[0].choose(bundle[1], choice, event_id=event_id)
    g = load(bundle)
    assert not g.pending_event
    act(bundle, 'resume', object_id=result['task_id'])
    g = load(bundle)
    assert g.player.world == 'demon' and g.player.age == age
    assert outpost_runtime.get(g, target('tianjian'))['visit']['return_fare'] == 800


def test_prepaid_return_survives_loss_of_organization_control(frontier):
    bundle = quiet(frontier)
    arrive(bundle)
    g = load(bundle)
    g.player.faction_id = None
    bundle[0].store.save(g)
    with pytest.raises(ValueError, match='授权'):
        act(bundle, 'outpost_suspend')
    act(bundle, 'outpost_return')
    assert load(bundle).player.world == 'human'


def test_actual_foreign_load_preserves_chartered_control_without_remote_governance(frontier):
    bundle = quiet(frontier)
    arrive(bundle)
    public = bundle[0].get_game(bundle[1])
    assert public['player']['world'] == 'demon'
    g = load(bundle)
    entity = g.sects['tianjian']
    row = outpost_runtime.get(g, target('tianjian'))
    assert bundle[2].outpost_control(g, entity, row)
    assert not bundle[0]._intrigue_has_control(g, 'sect', entity.id)
    record = bundle[0]._ensure_intrigue_faction(g, 'sect', entity.id)
    assert record['controller_id'] == record['positions']['leader'] == 'player'
    assert entity.world == 'human' and entity.location_id == 'wudi_plain'


def test_late_supply_cannot_pay_for_earlier_frozen_years(frontier):
    from cultivation_life.regional_context import CalendarGame
    bundle = quiet(frontier)
    arrive(bundle)
    wait(bundle, 10)
    act(bundle, 'outpost_return')
    g = load(bundle)
    row = outpost_runtime.get(g, target('tianjian'))
    # Start an explicitly insolvent local budget. The next real consignment
    # must not retroactively rescue those earlier historical upkeep years.
    g.economy_v2['accounts'][outpost_runtime.wallet(row)]['balance'] = 50
    baseline = row['last_year']
    bundle[0].store.save(g)
    courier = dispatch(bundle, 'outpost_supply')
    wait(bundle, 8)
    g = load(bundle)
    row = outpost_runtime.get(g, target('tianjian'))
    unit = next(u for u in row['units'] if u['person_id'] == courier)
    arrival = unit['last_year']
    assert g.world_npcs[courier].world == 'demon' and not unit['delivered']
    assert balance(g, outpost_runtime.wallet(row)) == 50
    g.player.age = arrival + 1
    for year in range(baseline + 1, arrival + 1):
        outpost_runtime.year_step(bundle[2], CalendarGame(g, 'demon', year))
    assert row['status'] == 'suspended' and balance(g, outpost_runtime.wallet(row)) == 50
    outpost_runtime.year_step(bundle[2], CalendarGame(g, 'demon', arrival + 1))
    assert unit['delivered'] and unit['phase'] == 'returning'
    assert balance(g, outpost_runtime.wallet(row)) == 10050
    assert row['status'] == 'suspended'
    before = copy.deepcopy(g.to_dict())
    outpost_runtime.year_step(bundle[2], CalendarGame(g, 'demon', arrival + 1))
    assert g.to_dict() == before


@pytest.mark.parametrize('malformation', ['unknown_goods', 'duplicate_person', 'duplicate_purse', 'future_progress'])
def test_invalid_frontier_document_is_rejected(frontier, malformation):
    from cultivation_life.system.heavens.schema import validate_state, validate_references
    bundle = quiet(frontier)
    act(bundle, 'outpost_authorize')
    dispatch(bundle)
    dispatch(bundle)
    g = load(bundle)
    row = outpost_runtime.get(g, target('tianjian'))
    if malformation == 'unknown_goods': row['stock']['item:fake'] = 1
    if malformation == 'duplicate_person': row['units'][1]['person_id'] = row['units'][0]['person_id']
    if malformation == 'duplicate_purse': row['units'][1]['wallet'] = row['units'][0]['wallet']
    if malformation == 'future_progress': row['units'][0]['progress'] = 999
    with pytest.raises(ValueError):
        validate_state(g.heavens_state)
        validate_references(g)


def test_reverse_family_charter_uses_same_original_family_and_people(frontier):
    engine, key, deps = frontier
    g = load(frontier)
    family = g.sects.pop('blood_prison')
    family.kind, family.location_id = 'family', 'red_marrow_city'
    family.founded_by_player, family.founder_player_id = True, key
    g.family = family
    g.player.faction_id, g.player.world, g.player.location_id = None, 'demon', 'red_marrow_city'
    for npc in family.npcs:
        npc.location_id, npc.realm_index, npc.layer = 'red_marrow_city', 3, 1
    organizations.register(g, 'family', family.id, 'demon')
    g.intrigue_state['factions']['family:' + family.id]['resources'] = 100000
    store = depot.ensure(g, family)
    store['stock'].update(outpost_runtime.materials('demon'))
    engine.store.save(g)
    state = g.heavens_state
    operations.command(deps, key, state['command_seq']+1, state['revision'], 'outpost_authorize', target(family.id), {})
    g = engine.store.load(key)
    assert outpost_runtime.get(g, target(family.id))['destination'] == 'human'
    assert g.family.id == family.id and g.family.world == 'demon'


def test_deployed_child_updates_existing_growth_record_without_a_second_npc(frontier):
    bundle = quiet(frontier)
    g = load(bundle)
    identity = bundle[2].outpost_candidates(g, g.sects['tianjian'])[0]['id']
    npc = next(n for n in g.sects['tianjian'].npcs if n.id == identity)
    g.player.offspring = [npc.to_dict()]
    bundle[0].store.save(g)
    act(bundle, 'outpost_authorize')
    act(bundle, 'outpost_dispatch', {'person_id': identity})
    wait(bundle, 8)
    g = load(bundle)
    assert g.player.offspring[0]['id'] == identity
    assert g.player.offspring[0]['world'] == g.world_npcs[identity].world == 'demon'
    assert identity not in {n.id for n in g.sects['tianjian'].npcs}
    bundle[0].get_game(bundle[1])
    g = load(bundle)
    assert identity in g.world_npcs and identity not in {n.id for n in g.sects['tianjian'].npcs}
