import copy
import random

import pytest

from test_immortal_cultivation import prepared
from cultivation_life.system.court_lifecycle import private_combat
from cultivation_life.system.doctrine.daomen import preview
from cultivation_life.system.doctrine.provider import config as doctrine_config
from cultivation_life.system.yaochi_system import experience, config, commission_reward


def occupy(game, count=4):
    court = game.heavenly_court
    for i, key in enumerate(court['offices']):
        court['offices'][key] = dict(holder_id='player', holder_name=game.player.name,
            start_unit=0, end_unit=100, votes=25) if i < count else None


def test_offices_keep_fourteen_units_without_repeat_elections(prepared):
    e, g, _ = prepared
    rng = random.Random(200)
    for _ in range(7):
        e._advance_heavenly_court_unit(g, rng)
    first = copy.deepcopy(g.heavenly_court['offices'])
    for _ in range(7):
        e._advance_heavenly_court_unit(g, rng)
    assert g.heavenly_court['offices'] == first
    e._advance_heavenly_court_unit(g, rng)
    assert g.heavenly_court['offices']['sun']['start_unit'] == 15
    assert g.heavenly_court['offices']['sun']['end_unit'] == 29


def test_setting_resolves_pending_without_age_or_seat_loss(prepared):
    e, g, _ = prepared
    occupy(g, 1)
    g.heavenly_court['player_grade'] = 4
    e._court_open_election(g, 'moon', random.Random(12))
    original = copy.deepcopy(g.heavenly_court['offices']['sun'])
    e.store.save(g)
    shown = e.update_setting(g.id, 'court_election_popup', False)
    saved = e._load(g.id)
    assert saved.player.age == g.player.age
    assert not shown['heavenly_court']['election']
    assert saved.heavenly_court['offices']['sun'] == original
    assert not saved.settings['court_election_popup']
    e._advance_heavenly_court_unit(saved, random.Random(1))
    assert not saved.heavenly_court['open_election']


def test_election_does_not_block_cultivation(prepared):
    e, g, _ = prepared
    g.heavenly_court['player_grade'] = 4
    e._court_open_election(g, 'sun', random.Random(1))
    e.store.save(g)
    shown = e.advance(g.id, 'rest')
    assert shown['player']['age'] > g.player.age
    assert e._load(g.id).heavenly_court['offices']['sun']['holder_id'] != 'player'


class DirectedVote(random.Random):
    def __init__(self, player):
        super().__init__(7)
        self.player = player

    def choices(self, population, weights, k):
        return ['player' if self.player else next(key for key in population if key != 'player')]


@pytest.mark.parametrize('wins', [True, False])
def test_promises_only_bind_the_elected_candidate(prepared, wins):
    e, g, _ = prepared
    g.heavenly_court['player_grade'] = 4
    e._court_open_election(g, 'sun', random.Random(2))
    e._court_resolve_election_round(g, DirectedVote(wins), 'promise_decree', 'relief')
    assert bool(g.heavenly_court['pledges']) == wins
    if wins:
        assert g.heavenly_court['pledges'][0]['deadline_unit'] == g.heavenly_court['unit'] + 7
    else:
        support = g.heavenly_court['player_support']
        for _ in range(9):
            e._advance_heavenly_court_unit(g, random.Random(5))
        assert g.heavenly_court['player_support'] == support


@pytest.mark.parametrize('pair', [('official_system','assistant_officials'),
    ('direct_appointment_law','recommendation_law'), ('wide_domain','traveling_palace'),
    ('universal_protection','immortal_slaughter')])
def test_conflicting_laws_reject_before_spending(prepared, pair):
    e, g, _ = prepared
    occupy(g)
    g.heavenly_court['laws'][pair[0]] = True
    before = g.heavenly_court['treasury']
    with pytest.raises(ValueError, match='互斥'):
        e._court_vote_law(g, pair[1], True, random.Random(1))
    assert g.heavenly_court['treasury'] == before
    e._court_vote_law(g, pair[0], False, random.Random(1))
    e._court_vote_law(g, pair[1], True, random.Random(1))
    assert g.heavenly_court['laws'][pair[1]] and not g.heavenly_court['laws'][pair[0]]


def test_legacy_migration_preserves_progress_and_repairs_conflicts(prepared):
    e, g, _ = prepared
    occupy(g, 1)
    c = g.heavenly_court
    c.pop('experience_version', None)
    c['offices']['sun']['end_unit'] = 7
    c['laws'].update(official_system=True, assistant_officials=True)
    c['law_changed_at'] = {'assistant_officials': 3, 'official_system': 1}
    c['pledges'] = [dict(kind='law', id='martial_gods', deadline_unit=0)]
    e.store.save(g)
    loaded = e._load(g.id).heavenly_court
    assert loaded['laws']['assistant_officials'] and not loaded['laws']['official_system']
    assert loaded['offices']['sun']['end_unit'] == 14
    assert not loaded['pledges']
    assert loaded['player_merit'] == c['player_merit']


def test_authorized_events_and_self_defense_are_not_private_combat(prepared):
    e, g, _ = prepared
    for key in ['EVT_CELESTIAL_COMBAT_STAR_ARENA_001', 'EVT_CELESTIAL_COMBAT_LAW_BEAST_001']:
        runtime = e._instantiate_event(e.events_by_id[key], g, random.Random(8))['runtime']
        assert runtime['court_authorized']
        assert not private_combat(runtime, set())
    assert private_combat(dict(combat_type='cultivator'), set())
    assert not private_combat(dict(combat_type='cultivator', player_defending=True), set())
    assert not private_combat(dict(combat_type='cultivator', npc_id='wanted'), {'wanted'})


def test_stipends_rise_with_grade_and_only_pay_on_time_progress(prepared):
    e, g, _ = prepared
    c = g.heavenly_court
    before = sum(i.quantity for i in g.player.inventory if i.id == 'spirit_stone')
    from cultivation_life.system.economy import organizations as finance
    row = finance.register(g, 'court', 'heavenly', 'celestial')
    finance.settle_institution(g, row, 1)
    first = c['stipend_total']
    c['player_grade'] = 1
    finance.settle_institution(g, row, 1)
    assert c['stipend_total'] - first > first
    assert sum(i.quantity for i in g.player.inventory if i.id == 'spirit_stone') == before + c['stipend_total']
    e.store.save(g)
    e.get_game(g.id)
    assert e._load(g.id).heavenly_court['stipend_total'] == c['stipend_total']


def test_peer_previews_never_expand_roster_until_retained(prepared):
    e, g, d = prepared
    count = len(g.notable_npcs)
    levels = set()
    for _ in range(100):
        candidate = preview(g, d['id'], d, doctrine_config()['words'])
        levels.add(candidate['level'])
        if candidate['level'] == 9:
            break
    assert 9 in levels and len(g.notable_npcs) == count
    e.store.save(g)
    shown = e.doctrine_action(g.id, 'retain_peer', doctrine_id=d['id'], npc_id=candidate['id'])
    saved = e._load(g.id)
    assert saved.player.age == g.player.age and len(saved.notable_npcs) == count + 1
    row = next(r for r in shown['doctrines']['rows'] if r['id'] == d['id'])
    assert row['peers'][0]['level'] == 9 and row['peer_preview'] is None
    with pytest.raises(ValueError, match='离开'):
        e.doctrine_action(g.id, 'retain_peer', doctrine_id=d['id'], npc_id=candidate['id'])


def test_yaochi_experience_rewards_completion_not_refresh_or_trading(prepared):
    e, g, _ = prepared
    g.player.location_id = config()['location_id']
    g.yaochi_state['experience'] = 200
    g.yaochi_state['job'] = dict(name='试验委托', years=100, progress=99, reward=400)
    e.store.save(g)
    with pytest.raises(ValueError, match='尚未完成'):
        e.yaochi_action(g.id, 'claim_job')
    g.yaochi_state['job']['progress'] = 100
    e.store.save(g)
    shown = e.yaochi_action(g.id, 'claim_job')
    assert shown['yaochi']['experience']['level'] == 2
    assert shown['yaochi']['commissions'][0]['reward'] == 440
    with pytest.raises(ValueError):
        e.yaochi_action(g.id, 'claim_job')
    g = e._load(g.id)
    assert experience(g)['total'] == 300
    g.yaochi_state['experience'] = 300 * 100000
    assert experience(g)['level'] == 100001
    assert commission_reward(g.player, config()['commissions'][0], g) == 4000400
