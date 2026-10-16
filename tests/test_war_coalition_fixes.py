"""Original identities, coalition rights and idle-only personnel transactions."""
import copy
import math
import random
from collections import Counter
from unittest.mock import patch

import pytest

from test_strategic_war import engine, api, scenario, own_campaign, snapshot
from test_strategic_dispatch import reserve_game
from test_strategic_peace import offer_command
from test_war_negotiation_fixes import deploy
from cultivation_life.engine.composition.strategic_war import bind
from cultivation_life.models import GameState
from cultivation_life.person_assignments import research_assignment
from cultivation_life.system.strategic_war import lifecycle, dispatch, peace, willingness
from cultivation_life.system.strategic_war.materialization import materialize
from cultivation_life.system.war import requirements, logistics
from cultivation_life.system.economy import depot
from cultivation_life.system.economy.ledger import balance, transfer_value
from cultivation_life.system.economy.basket_rules import REALM_WEIGHTS
from cultivation_life.system.economy.state import ensure_regional_market
from cultivation_life.world_state import race_pair


@pytest.mark.parametrize('registry', ['world_npcs', 'notable_npcs', 'relationship_npcs'])
def test_registry_location_cannot_omit_a_deployed_person_from_real_energy_bill(engine, registry):
    g, _, child = own_campaign(engine)
    deploy(engine, g, child)
    # Relationship-only storage uses a dynamic person, not a core template whose
    # separate legacy loader would recreate its missing original roster entry.
    side = 'defender' if registry == 'relationship_npcs' else 'attacker'
    person = engine._available_warriors(g, child, side)[0]
    source = g.sects[child['roster_owner'][person.id]]
    source.npcs[:] = [n for n in source.npcs if n.id != person.id]
    person.faction_id = source.id
    getattr(g, registry)[person.id] = person
    if registry == 'relationship_npcs':
        g.player.dao_friends.append(dict(id=person.id, npc_id=person.id))
    engine.store.save(g)
    g = engine._load(g.id)
    child = next(w for w in g.wars if w['id'] == child['id'])
    eligible = engine._available_warriors(g, child, side)
    assert person.id in {n.id for n in eligible}
    assert requirements.refresh(g, child, side) == Counter(n.realm_index for n in eligible)
    for market in g.economy_v2['markets'].values():
        for product in market['commodities'].values(): product['stock'] = 0
    transfer_value(g, 'background:spirit', logistics.wallet(child, side), 10**8, 'isolated field budget')
    enemy_wallet = logistics.wallet(child, 'defender' if side == 'attacker' else 'attacker')
    transfer_value(g, enemy_wallet, 'background:spirit', balance(g, enemy_wallet), 'isolate enemy forage')
    before = balance(g, logistics.wallet(child, side))
    logistics.begin_round(g, engine.maps, child, random.Random(7), side)
    expected = math.ceil(sum(REALM_WEIGHTS[n.realm_index] for n in eligible) * 12 * 2)
    assert before - balance(g, logistics.wallet(child, side)) == expected


@pytest.mark.parametrize('state', ['dead', 'held', 'escaped', 'away', 'returning'])
def test_supply_and_actual_combat_exclude_the_same_unavailable_identity(engine, state):
    g, _, child = own_campaign(engine)
    deploy(engine, g, child)
    person = engine._available_warriors(g, child, 'attacker')[0]
    if state == 'dead': person.alive = False
    elif state == 'held': person.roster_state = 'held'
    elif state == 'escaped': child['escaped']['attacker'].append(person.id)
    elif state == 'away': person.location_id = next(r['id'] for r in engine.maps.worlds[g.player.world]['locations'] if r['id'] != child['location_id'])
    else: next(j for j in child['journeys']['attacker'] if j['person_id'] == person.id)['phase'] = 'returning'
    actual = engine._available_warriors(g, child, 'attacker')
    assert person.id not in {n.id for n in actual}
    assert requirements.refresh(g, child, 'attacker') == Counter(n.realm_index for n in actual)


def coalition_victory(e):
    g, row = scenario(e)
    g.player.faction_id = 'taixuan'
    g.sects['taixuan'].founded_by_player = True
    deps = bind(e)
    loser = materialize(deps, g, row['world'], row['defender'], random.Random(18))
    lifecycle.commit(deps, g, row, g.sects['taixuan'])
    lifecycle.commit(deps, g, row, loser)
    lifecycle._launch(deps, g, row)
    child = next(w for w in g.wars if w['id'] == row['campaigns'][0])
    reserve = materialize(deps, g, row['world'], row['attacker'], random.Random(19))
    lifecycle.commit(deps, g, row, reserve)
    dispatch.send(deps, g, row, child, reserve)
    travel = max([j['years'] for js in child['journeys'].values() for j in js]
                 + [c['years'] for c in child['cargo_journeys'].values()]
                 + [r['cargo']['years'] for r in child['reinforcements']])
    for _ in range(travel + 1):
        g.player.age += 1
        lifecycle._journey(deps, g, child)
    child['campaign_phase'] = 'engaged'
    ensure_regional_market(g, e.maps, child['world'], child['location_id'])
    for book in child['logistics']['sides'].values(): book['location'] = child['location_id']
    child.update(status='peace_ready', winner='attacker', battles=3)
    lifecycle.receipt(g, row, child)
    for n in deps.members(g, g.sects[child['attacker_id']]): n.alive = False
    assert e._check_sect_extinction(g, g.sects[child['attacker_id']])
    assert row['score'] == 100 and child['reinforcements'][-1]['delivered'] and not reserve.extinct
    return g, row, child, reserve


def test_actual_surviving_ally_receives_result_compensation_http_once(api):
    e, post = api
    g, row, child, reserve = coalition_victory(e)
    command = offer_command(e, g, row, 'heavy_reparations')
    demands = peace.quote(bind(e), g, row, 'attacker', 'heavy_reparations')
    assert all(a['receiver']['id'] == reserve.id for d in demands for a in d['allocations'])
    original = balance(g, depot.treasury(g, reserve))
    source = balance(g, depot.treasury(g, g.sects[child['defender_id']]))
    e.store.save(g)
    with patch.object(e, '_vote_probability', return_value=1.): post(g.id, 'strategic-war', **command)
    saved = e._load(g.id)
    amount = sum(d['amount'] for d in demands)
    assert amount > 0 and balance(saved, depot.treasury(saved, saved.sects[reserve.id])) == original + amount
    assert balance(saved, depot.treasury(saved, saved.sects[child['defender_id']])) == source - amount
    assert GameState.from_dict(saved.to_dict()).strategic_war_state == saved.strategic_war_state
    before = snapshot(e, g.id)
    post(g.id, 'strategic-war', status=400, **command)
    assert e.store._path(g.id).read_bytes() == before


def test_npc_negotiation_keeps_surviving_coalition_victory(engine):
    g, row, _, _ = coalition_victory(engine)
    g.player.realm_index = 4
    row['objectives_done_age'] = g.player.age - 25
    peace.advance(bind(engine), g, row)
    assert row['treaty']['term'] == 'heavy_reparations' and row['treaty']['total'] > 0


def test_zero_contribution_fallback_uses_actual_victorious_allies(engine):
    g, row, child, reserve = coalition_victory(engine)
    child['logistics']['sides']['attacker']['contributions'] = {}
    demands = peace.quote(bind(engine), g, row, 'attacker', 'reparations')
    assert all(a['receiver']['id'] == reserve.id for d in demands for a in d['allocations'])
    for n in reserve.npcs: n.alive = False
    engine._check_sect_extinction(g, reserve)
    with pytest.raises(ValueError): peace.quote(bind(engine), g, row, 'attacker', 'reparations')


def test_surviving_ally_can_receive_real_property_after_primary_extinction_http(api):
    from cultivation_life.system.economy.enterprise_acquisition import acquire
    e, post = api
    g, row, child, reserve = coalition_victory(e)
    loser = g.sects[child['defender_id']]
    account = depot.treasury(g, loser)
    g.intrigue_state['factions'][account.removeprefix('organization:')]['resources'] = 10**9
    estate = acquire(g, e.maps, loser.world, loser.location_id, 'farm', 'sect', loser.id, account, 8)
    original = copy.deepcopy(estate)
    e.store.save(g)
    with patch.object(e, '_vote_probability', return_value=1.):
        post(g.id, 'strategic-war', **offer_command(e, g, row, 'economic_rights'))
    saved = e._load(g.id)
    actual = saved.economy_v2['estates'][estate['id']]
    assert actual['owner_id'] == reserve.id and not actual['enabled']
    assert all(actual[k] == original[k] for k in ('world', 'location', 'stock', 'reserve', 'job'))


def idle_vassal(e):
    g, row = scenario(e)
    g.player.faction_id = 'taixuan'
    g.sects['taixuan'].founded_by_player = True
    source = g.sects['xinghe']
    relation = dict(status='vassal', overlord='taixuan', subject=source.id, affinity=60)
    g.sect_relations[race_pair('taixuan', source.id)] = relation
    person = next(n for n in source.npcs if n.alive and n.realm_index <= g.player.realm_index)
    return g, source, person, relation


@pytest.mark.parametrize('phase', ['outbound', 'stationed', 'returning'])
def test_vassal_transfer_rejects_every_deployment_phase_atomically_http(api, phase):
    e, post = api
    g, row, own = own_campaign(e)
    other = next(w for w in g.wars if w.get('strategic_war_id') == row['id'] and w['id'] != own['id'])
    source = g.sects[other['attacker_id']]
    person = bind(e).find_person(g, other['journeys']['attacker'][0]['person_id'])
    if phase == 'stationed': deploy(e, g, other)
    elif phase == 'returning': lifecycle.withdraw(g, other)
    relation = dict(status='vassal', overlord='taixuan', subject=source.id, affinity=60)
    g.sect_relations[race_pair('taixuan', source.id)] = relation
    assert research_assignment(g, person.id)['phase'] == phase
    assert not e._vassal_transfer_candidates(g, 'sect', 'taixuan', source.id, relation)
    e.store.save(g)
    before = snapshot(e, g.id)
    post(g.id, 'vassal-transfer', status=400, kind='sect', target_id=source.id, npc_id=person.id)
    assert e.store._path(g.id).read_bytes() == before


@pytest.mark.parametrize('blocked', ['source', 'destination'])
def test_idle_person_cannot_bypass_whole_organization_occupancy_http(api, blocked):
    e, post = api
    g, source, person, relation = idle_vassal(e)
    busy_org = source if blocked == 'source' else g.sects['taixuan']
    enemy = next(o for o in g.sects.values() if o.world == g.player.world and o.id not in {source.id, 'taixuan'} and not o.extinct and o.kind == 'sect')
    e._start_war(g, 'sect', busy_org.id, enemy.id, initiated_by_player=True)
    assert not research_assignment(g, person.id)
    assert not e._vassal_transfer_candidates(g, 'sect', 'taixuan', source.id, relation)
    e.store.save(g)
    before = snapshot(e, g.id)
    post(g.id, 'vassal-transfer', status=400, kind='sect', target_id=source.id, npc_id=person.id)
    assert e.store._path(g.id).read_bytes() == before


def test_legal_idle_transfer_preserves_identity_and_location_http(api):
    e, post = api
    g, source, person, relation = idle_vassal(e)
    assert person.id in {n['id'] for n in e._vassal_transfer_candidates(g, 'sect', 'taixuan', source.id, relation)}
    place = (person.world, person.location_id)
    e.store.save(g)
    post(g.id, 'vassal-transfer', kind='sect', target_id=source.id, npc_id=person.id)
    saved = e._load(g.id)
    actual = bind(e).find_person(saved, person.id)
    assert actual.faction_id == 'taixuan' and (actual.world, actual.location_id) == place
    assert not any(n.id == person.id for n in saved.sects[source.id].npcs)
    assert sum(n.id == person.id for n in saved.sects['taixuan'].npcs) == 1


def test_task_odds_ignore_withdrawn_power_but_include_remaining_actual_forces(engine):
    g, row, child, reserve = reserve_game(engine)
    dispatch.send(bind(engine), g, row, child, reserve)
    primary = g.sects[child['attacker_id']]
    assert not dispatch.recall(g, child, primary)
    enemy = child['defender_id']
    before = willingness.evaluate(bind(engine), g, row)[enemy]['task']
    for n in bind(engine).members(g, primary): n.combat_factor = 10**6
    assert willingness.evaluate(bind(engine), g, row)[enemy]['task'] == before
    for n in bind(engine).members(g, reserve): n.combat_factor = 10**6
    assert willingness.evaluate(bind(engine), g, row)[enemy]['task'] < before
