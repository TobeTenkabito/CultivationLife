import copy
import random
from pathlib import Path
from unittest.mock import patch

import pytest

from cultivation_life.engine import GameEngine
from cultivation_life.engine.composition.strategic_war import bind
from cultivation_life.models import GameState
from cultivation_life.system import race_council as council
from cultivation_life.system.race_faction_directory import local_sects
from cultivation_life.system.strategic_war.materialization import materialize
from cultivation_life.system.economy.ledger import balance
from cultivation_life.system.economy.organization_accounts import register


@pytest.fixture(scope='module')
def setup(tmp_path_factory):
    engine = GameEngine(Path(__file__).resolve().parents[1], tmp_path_factory.mktemp('race-council')/'saves')
    made = engine.create_game('族议验收', 'supreme_metal', 'dao', 442,
                              custom_start=dict(world='spirit', realm_index=8, layer=1))
    return engine, engine._load(made['id'])


def meeting(game, race, motion, target='', roll=0):
    rng = random.Random(3)
    with patch.object(rng, 'random', return_value=roll):
        return council.convene(game, 'spirit', race, motion, target, rng)


def test_soft_votes_rejection_counteroffer_appeal_and_expiry(setup):
    _, original = setup
    game = copy.deepcopy(original)
    before = set(game.sects), copy.deepcopy(game.economy_v2), game.rng_state
    race = 'human'
    ids = [k for k, r in local_sects(game, 'spirit').items() if r['allegiance'] == race]
    target = ids[0]
    meeting(game, race, 'sponsor', target, roll=.999)
    record = council.minutes(game, 'spirit', race)
    assert record['counter'] == target and not record.get('places')
    with pytest.raises(ValueError):
        meeting(game, race, 'sponsor', target)
    meeting(game, race, 'amend', target)
    assert record['places'][target] == 2 and sum(record['places'].values()) == 6
    with pytest.raises(ValueError):
        meeting(game, race, 'amend', target)
    game.player.age += 10
    assert not council.remaining(record, game.player.age)
    meeting(game, race, 'sponsor', target)
    poorest = min(ids, key=lambda k: record['places'].get(k, 0))
    prior = record['places'].get(poorest, 0)
    meeting(game, race, 'mediate', poorest)
    assert record['places'][poorest] == prior + 1 and record['places'][target] == 2
    assert sum(record['places'].values()) == 6 and len(record['recent']) == 3
    assert (set(game.sects), game.economy_v2, game.rng_state) == before
    assert GameState.from_dict(game.to_dict()).strategic_war_state == game.strategic_war_state


def test_pledge_preserves_identity_at_founding_and_war_mobilization(setup):
    engine, original = setup
    game = copy.deepcopy(original)
    rows = local_sects(game, 'spirit')
    guest = next(r for r in rows.values() if r.get('home_race') == 'woodborn' and r['origin'] == 'seeded')
    meeting(game, 'human', 'invite', guest['id'])
    assert guest['id'] not in game.sects
    shown = engine._public_race_system(game)['races']
    assert guest['id'] in {f['id'] for f in shown['human']['supported_factions']}
    assert guest['id'] not in {f['id'] for f in shown['woodborn']['supported_factions']}
    for war in (True, False):
        g = GameState.from_dict(game.to_dict())
        rng = random.Random(44)
        if war:
            for _ in range(6):
                obj = materialize(bind(engine), g, 'spirit', 'human', rng)
                if obj.id == guest['id']:
                    break
        else:
            original_choice = rng.choice
            def choice(rows):
                if rows == ['sect', 'family']:
                    return 'sect'
                return 'woodborn' if 'woodborn' in rows else original_choice(rows)
            with patch.object(rng, 'random', return_value=0), patch.object(rng, 'choice', side_effect=choice):
                engine._maybe_npc_found_power(g, rng, [])
            obj = g.sects[guest['id']]
            assert next(n for n in obj.npcs if n.id == obj.founder_npc_id).race == 'woodborn'
        assert obj.id == guest['id'] and obj.name == guest['name'] and obj.allegiance_race == 'human'
        assert obj.id not in g.strategic_war_state['directory_support']['spirit']
        identities = [(n.id, n.race) for n in obj.npcs]
        meeting(g, 'seafolk', 'invite', obj.id)
        assert obj.allegiance_race == 'seafolk' and identities == [(n.id, n.race) for n in obj.npcs]


def test_extra_recruitment_requires_actual_funding_and_consumes_once(setup):
    engine, original = setup
    game = copy.deepcopy(original)
    org = game.sects['taixuan']
    game.player.age += (2 - game.player.age) % 5
    meeting(game, org.allegiance_race, 'sponsor', org.id)
    book = council.minutes(game, org.world, org.allegiance_race)
    purse = game.intrigue_state['factions']['sect:' + org.id]
    purse['resources'] = 0
    engine._annual_sect_update(game, random.Random(5), personal=False)
    assert book['places'][org.id] == 3
    purse['resources'] = 10**12
    engine._annual_sect_update(game, random.Random(5), personal=False)
    assert book['places'][org.id] == 2
    engine._annual_sect_update(game, random.Random(5), personal=False)
    assert book['places'][org.id] == 2
    game.player.age += 1
    engine._annual_sect_update(game, random.Random(5), personal=False)
    assert book['places'][org.id] == 1
    game.player.age += 1
    engine._annual_sect_update(game, random.Random(5), personal=False)
    assert book['places'][org.id] == 0
    assert any(h.event_id == 'SYS_COUNCIL_RECRUIT' for h in game.history)


def test_protected_sect_and_unauthorized_commands_do_not_take_effect(setup):
    engine, original = setup
    game = copy.deepcopy(original)
    game.player.faction_id = 'taixuan'
    before = copy.deepcopy(game.strategic_war_state)
    with pytest.raises(ValueError):
        meeting(game, 'seafolk', 'invite', 'taixuan')
    assert game.strategic_war_state == before
    game.player.realm_index = 1
    engine.store.save(game)
    saved = engine.get_game(game.id)
    payload = dict(action='local_council', world='spirit', race='human', motion='rotate',
                   expected_revision=saved['updated_at'], command_seq=1, command_id='test')
    with pytest.raises(ValueError):
        engine.strategic_war_action(game.id, payload)
    assert engine.store.load(game.id).strategic_war_state == before


def test_background_council_operates_on_current_world_and_spends_no_local_assets(setup):
    engine, original = setup
    game = copy.deepcopy(original)
    game.diplomacy_unit = 5
    before = set(game.sects), copy.deepcopy(game.economy_v2)
    rng = random.Random(10)
    with patch.object(rng, 'random', return_value=.55):
        news = engine._advance_diplomacy_unit(game, rng)
    world, = game.strategic_war_state['local_councils']
    assert world == 'spirit'
    book, = game.strategic_war_state['local_councils'][world].values()
    assert book['recent'][0]['summary'] in news and book['recent'][0]['ballots']
    assert (set(game.sects), game.economy_v2) == before


def test_local_grant_requotes_and_requires_donors_signature(setup):
    _, original = setup
    game = copy.deepcopy(original)
    donor, recipient = [s for s in game.sects.values() if s.world == 'spirit' and s.kind == 'sect'][:2]
    for org, cash in ((donor, 5000), (recipient, 50)):
        org.allegiance_race = 'human'
        org.location_id = game.player.location_id
        register(game, 'sect', org.id, 'spirit')['expected_upkeep'] = 100
        game.intrigue_state['factions']['sect:' + org.id]['resources'] = cash
    game.player.faction_id = donor.id
    quote = next(q for q in council.aid_offers(game, 'spirit', 'human') if q['donor'] == donor.id and q['id'] == recipient.id)
    assert quote['amount'] == 250
    balances = lambda: [balance(game, 'organization:sect:' + s.id) for s in (donor, recipient)]
    rng = random.Random(8)
    with patch.object(rng, 'random', return_value=0):
        with pytest.raises(ValueError):
            council.convene(game, 'spirit', 'human', 'aid', recipient.id, rng, player_ballot=True, offer=[donor.id, 249])
        council.convene(game, 'spirit', 'human', 'aid', recipient.id, rng, player_ballot=False, offer=[donor.id, 250])
        assert balances() == [5000, 50]
        game.player.age += 10
        council.convene(game, 'spirit', 'human', 'aid', recipient.id, rng, player_ballot=True, offer=[donor.id, 250])
        assert balances() == [4750, 300]
        assert not any(q['id'] == recipient.id for q in council.aid_offers(game, 'spirit', 'human'))
