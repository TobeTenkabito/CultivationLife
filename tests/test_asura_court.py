import copy
from pathlib import Path

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState
from cultivation_life.rules import max_hp, max_mp
from cultivation_life.system import asura, asura_court as court
from cultivation_life.system.upper_institutions import account, advance_time, public_institution, cultivation_discount

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def ready(tmp_path, monkeypatch):
    monkeypatch.setattr(asura, 'enabled', lambda: False)
    e = GameEngine(ROOT, tmp_path)
    game = e.create_game('王庭验收', 'supreme_metal', 'demonic', 1530, preset_id='asura_upper')
    e.upper_institution_action(game['id'], 'join')
    g = e._load(game['id'])
    return e, g


def king(e, g):
    state = account(g)
    state.update(earned=10000, merit=10000, regard=100)
    g.player.realm_index = 12
    g.player.hp, g.player.mp = max_hp(g.player), max_mp(g.player)
    e.store.save(g)
    for _ in range(5):
        e.upper_institution_action(g.id, 'promote')
    return e._load(g.id)


def test_instance_seats_base_game_and_pure_view(ready):
    e, g = ready
    state = account(g)
    assert not asura.enabled()
    assert len(state['court']['holders']) == 5
    for rank, identity in state['court']['holders'].items():
        npc = e._find_npc(g, identity)
        assert npc.alive and npc.title == court.cfg()['ranks'][int(rank)]
    before = copy.deepcopy(g.to_dict())
    for _ in range(3):
        view = public_institution(g)
        assert len(view['court']['seats']) == 5
    assert g.to_dict() == before
    assert GameState.from_dict(before).upper_institutions == g.upper_institutions


def test_merit_promotions_swap_instances_and_unlock_king(ready):
    e, g = ready
    old = account(g)['court']['holders'].copy()
    g = king(e, g)
    state = account(g)
    assert court.is_king(state)
    assert state['court']['holders']['4'] == old['5']
    assert state['court']['holders']['1'] == old['2']
    assert state['obligation'] is None
    assert e._find_npc(g, old['5']).title == '摄政辅臣'
    e.upper_institution_action(g.id, 'leave')
    g = e._load(g.id)
    assert account(g)['rank'] == 0 and 'player' not in account(g)['court']['holders'].values()
    e.upper_institution_action(g.id, 'join')
    assert account(e._load(g.id))['rank'] == 0


def test_legacy_migration_keeps_dead_npcs_and_progress(ready):
    e, g = ready
    state = account(g)
    del state['court']
    state.update(rank=3, earned=1370, merit=97)
    g.sects[court.COURT].npcs = g.sects[court.COURT].npcs[:3]
    g.sects[court.COURT].npcs[0].alive = False
    rng = g.rng_state
    assert court.ensure(g)
    assert len(g.sects[court.COURT].npcs) == 7
    assert not g.sects[court.COURT].npcs[0].alive
    assert state['court']['holders']['3'] == 'player'
    assert (state['earned'], state['merit'], g.rng_state) == (1370, 97, rng)
    assert not court.ensure(g)


def test_legacy_resigned_rank_does_not_create_duplicate_title(ready):
    e, g = ready
    state = account(g)
    state.update(joined=False, rank=4)
    del state['court']
    e.store.save(g)
    e.upper_institution_action(g.id, 'join')
    g = e._load(g.id)
    assert account(g)['rank'] == 0
    assert 'player' not in account(g)['court']['holders'].values()


def test_real_blood_duel_consumes_resources_and_preserves_npc(ready):
    e, g = ready
    state = account(g)
    target = state['court']['holders']['1']
    g.player.quick_start_base_combat_power *= 100000
    g.player.hp, g.player.mp = max_hp(g.player), max_mp(g.player)
    before_energy = g.player.immortal_aperture['current']
    e.store.save(g)
    e.upper_institution_action(g.id, 'blood_duel', target)
    g = e._load(g.id)
    assert account(g)['rank'] == 1
    assert account(g)['court']['holders']['1'] == 'player'
    assert e._find_npc(g, target).alive and e._find_npc(g, target).wounds >= 1
    assert g.last_combat_report['rounds'] and g.player.immortal_aperture['current'] < before_energy
    with pytest.raises(ValueError, match='相隔'):
        e.upper_institution_action(g.id, 'blood_duel')


@pytest.mark.parametrize('incoming,result,rank', [(False,'defeat',1), (True,'defeat',0), (True,'victory',1), (False,'stalemate',1)])
def test_duel_outcomes_only_exchange_correct_adjacent_seats(ready, monkeypatch, incoming, result, rank):
    e, g = ready
    s = account(g)
    court.change_rank(g, s, 1)
    npc_id = f'{court.COURT}_4'
    if incoming:
        s['court']['challenge'] = dict(npc_id=npc_id, rank=1, deadline=4)
    def battle(game, target, lethal, rng):
        assert not lethal and target['npc_id'] == (npc_id if incoming else s['court']['holders']['2'])
        game.last_combat_report = {'rounds': [{}]}
        return result, '真实战斗结果的结算边界'
    monkeypatch.setattr(e, '_combat', battle)
    e.store.save(g)
    e.upper_institution_action(g.id, 'answer_duel' if incoming else 'blood_duel')
    g = e._load(g.id)
    assert account(g)['rank'] == rank
    assert all(n.alive for n in court.people(g).values())


def test_no_skipping_ranks_and_no_posthumous_combat(ready):
    e, g = ready
    with pytest.raises(ValueError, match='持有人'):
        e.upper_institution_action(g.id, 'blood_duel', f'{court.COURT}_0')
    identity = account(g)['court']['holders']['1']
    e._find_npc(g, identity).alive = False
    e.store.save(g)
    e.upper_institution_action(g.id, 'blood_duel')
    g = e._load(g.id)
    assert account(g)['rank'] == 1 and not e._find_npc(g, identity).alive


def test_assessment_is_pure_and_accounts_for_resources_and_puppets(ready):
    e, g = ready
    npc = e._find_npc(g, f'{court.COURT}_4')
    before = copy.deepcopy(g.to_dict())
    full = court.assessment(g, npc)
    assert g.to_dict() == before
    g.player.hp /= 4
    assert court.assessment(g, npc)['player'] < full['player']
    g.player.puppets.append(dict(id='guard',name='卫傀', type='mechanical',alive=True,combat_power=1e15,realm_index=9,durability=100))
    assert court.assessment(g, npc)['player'] > full['player']


def test_challenges_respect_protection_and_global_individual_cooldowns(ready, monkeypatch):
    e, g = ready
    g = king(e, g)
    state = account(g)
    monkeypatch.setattr(court, 'assessment', lambda *a: dict(player=1, enemy=100))
    units = []
    for _ in range(200):
        advance_time(g, 100, 100)
        challenge = state['court']['challenge']
        if challenge:
            units.append(state['unit'])
            state['court']['challenge'] = None  # won a defence, same subordinate
            state['court']['protected_until'] = state['unit'] + 8
    assert len(units) >= 2 and units[0] >= 8
    assert all(b - a >= 24 for a,b in zip(units, units[1:]))
    assert g.pending_event is None


def test_strong_player_not_challenged_and_dead_challenge_cancels(ready, monkeypatch):
    e, g = ready
    g = king(e, g)
    state = account(g)
    monkeypatch.setattr(court, 'assessment', lambda *a: dict(player=1000, enemy=1))
    advance_time(g, 5000, 100)
    assert state['court']['challenge'] is None
    npc_id = state['court']['holders']['4']
    state['court']['challenge'] = dict(npc_id=npc_id, rank=5, deadline=state['unit'])
    e._find_npc(g,npc_id).alive = False
    advance_time(g, 100, 100)
    assert state['rank'] == 5 and state['court']['challenge'] is None


def test_expired_challenge_and_explicit_yield_swap_once(ready):
    e, g = ready
    g = king(e, g)
    state = account(g)
    npc_id = state['court']['holders']['4']
    state['court']['challenge'] = dict(npc_id=npc_id, rank=5, deadline=2)
    advance_time(g, 200, 100)
    assert state['rank'] == 5
    advance_time(g, 100, 100)
    assert state['rank'] == 4 and state['court']['holders']['5'] == npc_id
    advance_time(g, 100, 100)
    assert state['rank'] == 4


def test_king_policy_is_persistent_and_nonking_cannot_govern(ready):
    e, g = ready
    for action,target in [('appoint', f'treasury:{court.COURT}_1'), ('build','market'), ('decree','levy')]:
        with pytest.raises(ValueError, match='修罗王'):
            e.upper_institution_action(g.id, action, target)
    g = king(e, g)
    before = account(g)['merit']
    e.upper_institution_action(g.id, 'policy', 'trade')
    g = e._load(g.id)
    advance_time(g, 600, 100)
    assert account(g)['policy'] == 'trade' and account(g)['merit'] == before
    assert account(g)['court']['public_support'] == 56
    assert account(g)['obligation'] is None


def test_appointments_have_actual_income_costs_and_cannot_stack(ready):
    e, g = ready
    g = king(e, g)
    npc_id = f'{court.COURT}_1'
    e.upper_institution_action(g.id, 'appoint', f'treasury:{npc_id}')
    g = e._load(g.id)
    state = account(g)
    benefits = court.benefits(g,state)
    before = state['treasury']
    advance_time(g, 100, 100)
    assert state['treasury'] == before + int(600000 * benefits['revenue']) - 30000 - 60000
    e.store.save(g)
    with pytest.raises(ValueError, match='不得兼任'):
        e.upper_institution_action(g.id, 'appoint', f'ritual:{npc_id}')
    e.upper_institution_action(g.id, 'appoint', 'treasury:')
    g = e._load(g.id)
    assert court.benefits(g,account(g))['wages'] == 0


def test_construction_actual_completion_and_cannot_mint_on_reads(ready):
    e, g = ready
    g = king(e, g)
    e.upper_institution_action(g.id, 'build', 'sanctum')
    g = e._load(g.id)
    state = account(g)
    before = cultivation_discount(g)
    for _ in range(5): public_institution(g)
    assert state['court']['buildings']['sanctum'] == 0
    advance_time(g, 399, 100)
    assert state['court']['buildings']['sanctum'] == 0
    advance_time(g, 1, 100)
    assert state['court']['buildings']['sanctum'] == 1
    assert cultivation_discount(g) == pytest.approx(before + .03)
    assert state['court']['project'] is None


def test_decree_costs_cooldown_and_loyalty(ready):
    e, g = ready
    g = king(e, g)
    before = account(g)['treasury']
    e.upper_institution_action(g.id, 'decree', 'levy')
    g = e._load(g.id)
    assert account(g)['treasury'] == before + 300000
    assert account(g)['court']['public_support'] == 35
    with pytest.raises(ValueError, match='相隔'):
        e.upper_institution_action(g.id, 'decree', 'reward')
    advance_time(g, 400, 100)
    e.store.save(g)
    e.upper_institution_action(g.id, 'decree', 'reward')
    g = e._load(g.id)
    assert all(v == 62 for v in account(g)['court']['loyalty'].values())
