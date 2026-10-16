"""Original battlefield people, participant intelligence and atomic peace guards."""
import copy
import random
from unittest.mock import patch

import pytest

from test_strategic_war import engine, api, own_campaign, snapshot
from test_strategic_dispatch import reserve_game
from test_war_negotiation_fixes import deploy
from cultivation_life.engine.composition.strategic_war import bind
from cultivation_life.system.strategic_war import dispatch, lifecycle
from cultivation_life.system.economy import depot
from cultivation_life.system.economy.ledger import balance
from cultivation_life.system.war.presentation import _public_war_system


def returned_reserve(e):
    g, row, child, reserve = reserve_game(e)
    deploy(e, g, child)  # Isolated front; the reserve still makes its real trip.
    dispatch.send(bind(e), g, row, child, reserve)
    identity = next(j['person_id'] for j in child['journeys']['attacker']
                    if child['roster_owner'][j['person_id']] == reserve.id)
    for _ in range(2):
        g.player.age += 1
        lifecycle._journey(bind(e), g, child)
    assert not dispatch.recall(g, child, reserve)
    journey = next(j for j in child['journeys']['attacker'] if j['person_id'] == identity)
    for _ in range(journey['remaining'] + 1):
        g.player.age += 1
        lifecycle._journey(bind(e), g, child)
    person = bind(e).find_person(g, identity)
    assert journey['phase'] == 'home' and person.location_id == journey['origin'] != child['location_id']
    g.player.faction_id = None
    return g, child, person


def encounter(e, g, *, prefer=None):
    g.map_war_last_encounter_unit = g.diplomacy_unit - 2
    rng = random.Random(3)
    seen = set()
    def choose(values):
        seen.update(n.id for n in values if hasattr(n, 'id'))
        return next((n for n in values if getattr(n, 'id', None) == prefer), values[0])
    with patch.object(rng, 'random', return_value=0), patch.object(rng, 'choice', side_effect=choose):
        result = e._maybe_map_war_encounter(g, rng)
    return result, seen


def test_returned_reserve_never_ambushes_from_its_remote_home(engine):
    g, child, person = returned_reserve(engine)
    eligible = {n.id for s in ('attacker', 'defender') for n in engine._available_warriors(g, child, s)}
    assert eligible and person.id not in eligible
    original_place = (person.world, person.location_id)
    success, candidates = encounter(engine, g, prefer=person.id)
    assert success and candidates <= eligible and person.id not in candidates
    assert g.pending_event['runtime']['npc_id'] in eligible
    assert (person.world, person.location_id) == original_place


def test_stationed_original_enemy_can_really_trigger_an_encounter(engine):
    g, _, child = own_campaign(engine)
    deploy(engine, g, child)
    enemies = {n.id for n in engine._available_warriors(g, child, 'defender')}
    assert enemies and all(engine._find_npc(g, identity) is None for identity in enemies)
    success, candidates = encounter(engine, g)
    assert success and candidates == enemies
    assert g.pending_event['runtime']['npc_id'] in enemies


@pytest.mark.parametrize('state', ['escaped', 'suppressed', 'prison', 'away', 'returning'])
def test_map_encounter_excludes_unavailable_enemies(engine, state):
    g, _, child = own_campaign(engine)
    deploy(engine, g, child)
    target = engine._available_warriors(g, child, 'defender')[0]
    if state == 'escaped': child['escaped']['defender'].append(target.id)
    elif state == 'suppressed': child['voisinage_suppressed'] = [target.id]
    elif state == 'prison': g.intrigue_state.setdefault('npc_prisons', {})[target.id] = 'sect:' + child['defender_id']
    elif state == 'away': target.location_id = next(r['id'] for r in engine.maps.worlds[g.player.world]['locations'] if r['id'] != child['location_id'])
    else: next(j for j in child['journeys']['defender'] if j['person_id'] == target.id)['phase'] = 'returning'
    _, candidates = encounter(engine, g, prefer=target.id)
    assert target.id not in candidates


@pytest.mark.parametrize('membership', ['member', 'officer', 'family', 'guest', 'observer'])
def test_supply_visibility_follows_membership_instead_of_command_authority(engine, membership):
    g, _, child = own_campaign(engine)
    if membership == 'member':
        g.sects['taixuan'].founded_by_player = False
        g.player.realm_index, g.player.layer = 1, 1
        assert not engine._has_sect_voice(g)
    elif membership == 'family':
        family = g.sects.pop(child['attacker_id'])
        family.kind = 'family'
        family.founded_by_player = False
        g.family = family
        g.player.faction_id = None
        # Match the original approved organization identity; no duplicate entity.
        for row in g.strategic_war_state['wars'][0]['commitments']:
            if row['org']['id'] == family.id: row['org']['kind'] = 'family'
        g.player.realm_index, g.player.layer = 1, 1
        assert not engine._has_family_voice(g)
    elif membership == 'guest':
        g.player.faction_id = None
        record = engine._ensure_intrigue_faction(g, 'sect', child['defender_id'])
        record['guests'].append({'npc_id': 'player', 'defense_required': True, 'offense_opt_in': False})
    elif membership == 'observer': g.player.faction_id = None
    engine.store.save(g)
    shown = engine.get_game(g.id)['war_system']['strategic']['wars'][0]
    field = next(c for c in shown['campaigns'] if c['id'] == child['id'])['field']
    assert (field['attacker']['supplies'] is not None) == (membership != 'guest')
    assert (field['defender']['supplies'] is not None) == (membership in {'guest', 'observer'})


def independent_peace(e):
    made = e.create_game('和谈边界验收', 'supreme_metal', 'dao', 8712)
    g = e._load(made['id'])
    g.player.realm_index, g.player.layer = 4, 1
    g.player.faction_id = 'tianjian'
    g.sects['tianjian'].founded_by_player = True
    war = e._start_war(g, 'sect', 'tianjian', 'wanmo', initiated_by_player=True)
    war.update(war_score=100, battles=2, controller='player', status='peace_ready', winner='attacker')
    debtor = g.sects['wanmo']
    depot.ensure(g, debtor)
    key = depot.treasury(g, debtor)
    g.intrigue_state['factions'][key.removeprefix('organization:')]['resources'] = 100000
    return g, war


@pytest.mark.parametrize('blocked', ['event', 'trial', 'prison', 'captive', 'dead'])
def test_old_peace_rejects_blocked_states_before_vote_or_payment_http(api, blocked):
    e, post = api
    g, war = independent_peace(e)
    if blocked == 'event': g.pending_event = e._prepare_treasure_reward_event(g, random.Random(22))
    elif blocked == 'trial':
        g.player.realm_index = 6
        g.player.next_tribulation_age = g.player.age
        e._check_tribulation(g, random.Random(23))
        assert g.active_trial and g.pending_event
    elif blocked == 'prison': g.player.imprisonment = {'captor_name': '狱卒', 'years_remaining': 10}
    elif blocked == 'captive': g.player.ghost_captor = {'id': 'warden', 'name': '拘魂者', 'world': 'human'}
    else: g.player.alive = False
    e.store.save(g)
    e._load(g.id)
    before = e.store._path(g.id).read_bytes()
    projected = _public_war_system(e._dependencies.war.presentation, g)
    view = next(w for w in projected['wars'] if w['id'] == war['id'])
    assert view['action_blocked'] and not view['player_controls'] and not view['can_negotiate'] and not view['can_participate']
    with patch.object(e, '_intrigue_resolve', side_effect=AssertionError('blocked peace must not vote')):
        post(g.id, 'war-peace', status=400, war_id=war['id'], term='stones')
    assert e.store._path(g.id).read_bytes() == before


def test_event_reward_then_legal_peace_pays_exactly_once_http(api):
    e, post = api
    g, war = independent_peace(e)
    g.pending_event = e._prepare_treasure_reward_event(g, random.Random(22))
    reward = copy.deepcopy(g.pending_event)
    e.store.save(g)
    before = snapshot(e, g.id)
    post(g.id, 'war-peace', status=400, war_id=war['id'], term='stones')
    assert e.store._path(g.id).read_bytes() == before
    assert e._load(g.id).pending_event == reward
    post(g.id, 'choice', choice_id=reward['choices'][0]['id'], event_id=reward['id'])
    ready = e._load(g.id)
    assert ready.pending_event is None
    source, destination = 'organization:sect:wanmo', 'organization:sect:tianjian'
    original = (balance(ready, source), balance(ready, destination))
    with patch.object(e, '_vote_probability', return_value=1.):
        post(g.id, 'war-peace', war_id=war['id'], term='stones')
    saved = e._load(g.id)
    paid = original[0] - balance(saved, source)
    assert paid > 0 and balance(saved, destination) - original[1] == paid
    before = snapshot(e, g.id)
    post(g.id, 'war-peace', status=400, war_id=war['id'], term='stones')
    assert e.store._path(g.id).read_bytes() == before
