"""Real commands for political consent, automatic diplomacy and battle supply scope."""
import random
from unittest.mock import patch

import pytest

from test_strategic_war import engine, api, snapshot, own_campaign
from test_strategic_peace import finished
from cultivation_life.engine.composition.strategic_war import bind
from cultivation_life.models import GameState
from cultivation_life.system.strategic_war import lifecycle, peace
from cultivation_life.system.strategic_war.presentation import public
from cultivation_life.system.war import logistics, requirements
from cultivation_life.system.economy.ledger import balance, transfer_value
from cultivation_life.system.economy.state import ensure_regional_market


def low_authority(e, g):
    g.player.realm_index = 4
    g.player.layer = 1
    assert e._has_sect_voice(g) and not e._has_race_voice(g)


def reply(e, post, g, row, command='reply'):
    return post(g.id, 'strategic-war', action='reply_peace', reply='accept', war_id=row['id'],
                expected_revision=row['revision'], command_seq=1, command_id=command)


@pytest.mark.parametrize('race_voice', [False, True])
def test_accepting_conditions_cannot_override_representative_majority_http(api, race_voice):
    e, post = api
    g, row, _ = own_campaign(e)
    if not race_voice:
        low_authority(e, g)
    else:
        assert e._has_race_voice(g)
    peace.propose(bind(e), g, row, 'defender', 'white_peace')
    assert row['opposing_peace_vote']['yes'] == 0 and row['opposing_peace_vote']['total'] > 1
    e.store.save(g)
    old_money = balance(g, 'organization:sect:taixuan')
    reply(e, post, g, row)
    saved = e._load(g.id)
    actual = saved.strategic_war_state['wars'][0]
    assert actual['status'] == 'active' and not actual.get('treaty')
    assert actual['peace_proposal']['status'] == 'rejected'
    assert actual['opposing_peace_vote']['yes'] == int(race_voice)
    assert balance(saved, 'organization:sect:taixuan') == old_money
    before = snapshot(e, g.id)
    post(g.id, 'strategic-war', status=400, action='reply_peace', reply='accept', war_id=row['id'],
         expected_revision=actual['revision'], command_seq=2, command_id='reply-again')
    assert e.store._path(g.id).read_bytes() == before


def test_org_consent_with_actual_majority_can_pay_once_http(api):
    e, post = api
    g, row, _ = finished(e, 'defender')
    low_authority(e, g)
    proposal = peace.propose(bind(e), g, row, 'defender', 'reparations')
    assert proposal['status'] == 'pending' and row['opposing_peace_vote']['yes'] > 0
    original = balance(g, 'organization:sect:taixuan')
    e.store.save(g)
    reply(e, post, g, row)
    saved = e._load(g.id)
    assert saved.strategic_war_state['wars'][0]['treaty']['total'] > 0
    assert balance(saved, 'organization:sect:taixuan') < original
    before = snapshot(e, g.id)
    post(g.id, 'strategic-war', status=400, action='reply_peace', reply='accept', war_id=row['id'],
         expected_revision=row['revision'], command_seq=1, command_id='reply')
    assert e.store._path(g.id).read_bytes() == before


def test_reply_rechecks_current_representatives_without_phantom_votes_http(api):
    e, post = api
    g, row, _ = finished(e, 'defender')
    low_authority(e, g)
    peace.propose(bind(e), g, row, 'defender', 'reparations')
    for c in row['commitments']:
        if c['side'] == 'attacker':
            bind(e).find_person(g, c['representative']).alive = False
    e.store.save(g)
    reply(e, post, g, row)
    actual = e._load(g.id).strategic_war_state['wars'][0]
    assert actual['status'] == 'active' and not actual.get('treaty')
    assert actual['opposing_peace_vote']['total'] == 0


def test_winning_org_without_political_voice_still_receives_automatic_compensation(engine):
    e = engine
    g, row, _ = finished(e)
    low_authority(e, g)
    row['objectives_done_age'] = g.player.age
    g.player.age += 25
    before = balance(g, 'organization:sect:taixuan')
    assert not public(bind(e), g)['wars'][0]['can_peace']
    peace.advance(bind(e), g, row)
    assert row['treaty']['term'] == 'heavy_reparations' and row['treaty']['total'] > 0
    assert balance(g, 'organization:sect:taixuan') > before
    assert GameState.from_dict(g.to_dict()).strategic_war_state == g.strategic_war_state


def test_winning_race_representative_keeps_manual_negotiation(engine):
    g, row, _ = finished(engine)
    row['objectives_done_age'] = g.player.age
    g.player.age += 25
    assert engine._has_race_voice(g)
    peace.advance(bind(engine), g, row)
    assert not row.get('peace_proposal') and public(bind(engine), g)['wars'][0]['can_peace']


def deploy(e, g, c):
    c['campaign_phase'] = 'engaged'
    g.player.location_id = c['location_id']
    for side, journeys in c['journeys'].items():
        c['logistics']['sides'][side]['location'] = c['location_id']
        for j in journeys:
            j.update(phase='stationed', remaining=0)
            bind(e).find_person(g, j['person_id']).location_id = c['location_id']
    ensure_regional_market(g, e.maps, c['world'], c['location_id'])


@pytest.mark.parametrize('command_authority', [False, True])
def test_real_personal_round_counts_player_and_restores_npc_demand_http(api, command_authority):
    e, post = api
    g, row, c = own_campaign(e)
    deploy(e, g, c)
    if not command_authority:
        g.sects['taixuan'].founded_by_player = False
    expected = dict(requirements.refresh(g, c, 'attacker'))
    e.store.save(g)
    observed = []
    original = e._combat
    def inspect(game, *args, **kwargs):
        child = next(w for w in game.wars if w['id'] == c['id'])
        observed.append((dict(requirements.groups(game, child, 'attacker')),
                         dict(requirements.physical(game, child, 'attacker'))))
        return original(game, *args, **kwargs)
    # Exercise both officers and ordinary members without changing political rules.
    with patch.object(e, '_player_has_war_voice', return_value=command_authority), patch.object(e, '_combat', side_effect=inspect):
        post(g.id, 'strategic-war', action='participate_round', war_id=row['id'], campaign_id=c['id'],
             expected_revision=row['revision'], command_seq=1, command_id='personal-supply')
    with_player = dict(expected)
    with_player[g.player.realm_index] = with_player.get(g.player.realm_index, 0) + 1
    assert observed and observed[0][0] == with_player
    assert observed[0][1][f'medical:{g.player.realm_index}'] > 0
    saved = e._load(g.id)
    actual = next(w for w in saved.wars if w['id'] == c['id'])
    assert requirements.groups(saved, actual, 'attacker').get(g.player.realm_index, 0) <= expected.get(g.player.realm_index, 0)
    assert actual['logistics']['sides']['attacker']['reference_need'] == logistics.need(saved, actual, 'attacker')
    assert actual['battles'] == 1 and actual['last_personal_age'] == g.player.age


def test_personal_demand_is_restored_if_detailed_combat_raises(engine):
    g, _, c = own_campaign(engine)
    deploy(engine, g, c)
    with patch.object(engine, '_combat', side_effect=ValueError('isolated failure')):
        with pytest.raises(ValueError, match='isolated failure'):
            engine._resolve_player_war_round(g, c, 'attacker', random.Random(7))
    assert requirements.groups(g, c, 'attacker') == dict(requirements.refresh(g, c, 'attacker', persist=False))


def test_automatic_forage_keeps_actual_personal_demand(engine):
    g, _, c = own_campaign(engine)
    deploy(engine, g, c)
    for market in g.economy_v2['markets'].values():
        for product in market['commodities'].values():
            product['stock'] = 0
    transfer_value(g, 'background:spirit', logistics.wallet(c, 'attacker'), 10**9, 'isolated field budget')
    with patch.object(logistics, 'strategy', wraps=logistics.strategy) as strategy:
        logistics.begin_round(g, engine.maps, c, random.Random(7), participating_player_side='attacker')
    assert any(call.args[3:5] == ('attacker', 'forage') for call in strategy.call_args_list)
    assert requirements.groups(g, c, 'attacker').get(g.player.realm_index, 0) > 0


@pytest.mark.parametrize('hold', [False, True])
def test_both_supply_collapse_is_draw_without_victory_or_claim(engine, hold):
    g, row, c = own_campaign(engine)
    deploy(engine, g, c)
    for side in ('attacker', 'defender'):
        c['morale'][side] = 25
        c['logistics']['sides'][side]['items'] = {}
        source = logistics.wallet(c, side)
        transfer_value(g, source, 'background:spirit', balance(g, source), 'isolated empty budget')
    if hold:
        c['stances'] = {'attacker': 'hold', 'defender': 'hold'}
    bind(engine).advance_campaigns(g, random.Random(7), [c])
    assert c['morale'] == {'attacker': 0., 'defender': 0.}
    assert c['winner'] is None and c['war_score'] == 0 and c['status'] == 'peace_ready'
    lifecycle.receipt(g, row, c)
    assert row['score'] == 0 and c['campaign_phase'] == 'returning'
    with pytest.raises(ValueError):
        peace.quote(bind(engine), g, row, 'defender', 'reparations')


@pytest.mark.parametrize('loser', ['attacker', 'defender'])
def test_single_side_collapse_keeps_original_winner(engine, loser):
    g, _, c = own_campaign(engine)
    c['morale'][loser] = 0
    assert engine._finish_war_by_morale(g, c)
    assert c['winner'] == ('defender' if loser == 'attacker' else 'attacker')


def test_existing_independent_ai_draw_concludes_only_white_peace(engine):
    g, _, c = own_campaign(engine)
    c.pop('strategic_war_id')
    c['morale'] = dict(attacker=0, defender=0)
    engine._advance_wars_unit(g, random.Random(7))
    assert c['status'] == 'ended' and c['winner'] is None
    assert all(d['term'] == 'white_peace' for d in c['peace_terms'])


def test_no_winner_cannot_execute_a_conditional_bundle(engine):
    g, _, c = own_campaign(engine)
    with pytest.raises(ValueError, match='只能无条件停战'):
        engine._conclude_war_bundle(g, c, [dict(term='stones')], None, automatic=True)
