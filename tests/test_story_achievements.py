"""Original identities, real action evidence and precise achievement boundaries."""
import copy
import random
from pathlib import Path

import pytest

from cultivation_life.achievement_facts import (
    descendants_lead_sects, family_kin_all_fallen, leader_sect_before_capture,
    record_corpse_campaign,
)
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState, Player, SectNpc, SectState
from cultivation_life.runtime import encode_rng
from cultivation_life.rules import add_item


ROOT = Path(__file__).resolve().parents[1]


def person(identity, *, kin=True, alive=True, reason=None, **kwargs):
    return SectNpc(identity, '沈' + identity, '族人', 1, 1, 30, 200,
                   family_traits={'kin': kin}, alive=alive, death_reason=reason, **kwargs)


def state():
    return GameState('achievement-test', 1, Player('沈砚', 'supreme_fire'), '', '')


def lead(game, identity, sect_id):
    npc = person(identity, faction_id=sect_id)
    sect = SectState(sect_id, sect_id, npcs=[npc])
    game.sects[sect_id] = sect
    game.intrigue_state.setdefault('factions', {})[f'sect:{sect_id}'] = {
        'positions': {'leader': identity}, 'controller_id': 'someone-else',
    }
    return npc, sect


def test_godfather_counts_distinct_real_sect_offices_without_mutation():
    g = state()
    lead(g, 'son', 'first')
    lead(g, 'daughter', 'second')
    g.player.offspring = [{'id': 'son'}, {'id': 'daughter'}]
    before = copy.deepcopy(g.to_dict())
    assert descendants_lead_sects(g, 2)
    assert g.to_dict() == before
    assert not descendants_lead_sects(g, 3)


@pytest.mark.parametrize('invalid', ['dead', 'held', 'imprisoned', 'guest', 'away', 'extinct',
                                     'controller_only', 'family', 'missing', 'not_member', 'unrelated'])
def test_godfather_rejects_invalid_second_office(invalid):
    g = state()
    lead(g, 'son', 'first')
    npc, sect = lead(g, 'daughter', 'second')
    g.player.offspring = [{'id': 'son'}, {'id': 'daughter'}]
    record = g.intrigue_state['factions']['sect:second']
    if invalid == 'dead': npc.alive = False
    elif invalid == 'held': npc.roster_state = 'held'
    elif invalid == 'imprisoned': g.intrigue_state['npc_prisons'] = {npc.id: {}}
    elif invalid == 'guest': record['positions']['guest_elder'] = npc.id
    elif invalid == 'away': npc.world = 'spirit'
    elif invalid == 'extinct': sect.extinct = True
    elif invalid == 'controller_only': record.update(positions={'leader': None}, controller_id=npc.id)
    elif invalid == 'family': sect.kind = 'family'
    elif invalid == 'missing': sect.npcs.clear()
    elif invalid == 'not_member':
        sect.npcs.clear(); npc.faction_id = 'elsewhere'; g.notable_npcs[npc.id] = npc
    elif invalid == 'unrelated': g.player.offspring.pop()
    assert not descendants_lead_sects(g, 2)


def test_godfather_uses_parent_ids_and_family_dual_membership():
    g = state()
    son, _ = lead(g, 'son', 'first')
    grandson, second = lead(g, 'grandson', 'second')
    grandson.family_traits['parents'] = [son.id]
    g.player.offspring = [{'id': son.id}]
    second.npcs.clear()
    g.family = SectState('clan', '沈氏', npcs=[grandson], kind='family')
    assert descendants_lead_sects(g, 2)


def test_godfather_does_not_count_one_identity_twice():
    g = state()
    npc, _ = lead(g, 'son', 'first')
    g.player.offspring = [{'id': npc.id}]
    g.sects['second'] = SectState('second', '第二宗', npcs=[npc])
    g.intrigue_state['factions']['sect:second'] = {'positions': {'leader': npc.id}}
    assert not descendants_lead_sects(g, 2)


@pytest.mark.parametrize('reason', ['势力征伐中阵亡', '势力大战中陨落', '仙域斗法中陨落',
                                    '与敌修斗法时陨落', '遭敌修截杀', '被敌修击杀夺宝'])
def test_martyrs_ignore_outsiders_and_count_only_actual_kin_deaths(reason):
    g = state()
    g.family = SectState('clan', '沈氏', kind='family', npcs=[
        person('heir', alive=False, reason=reason), person('outsider', kin=False),
    ])
    before = copy.deepcopy(g.to_dict())
    assert family_kin_all_fallen(g)
    assert g.to_dict() == before


@pytest.mark.parametrize('reason', [None, '寿元耗尽', '势力征伐中阵亡后复活', '战败和约指定处死',
                                    '被玩家炼为炼尸', '被玩家炼尸失败，形神俱灭', '冲关失败，道消身殒'])
def test_martyrs_reject_unknown_natural_execution_and_conversion_deaths(reason):
    g = state()
    g.family = SectState('clan', '沈氏', kind='family', npcs=[person('heir', alive=False, reason=reason)])
    assert not family_kin_all_fallen(g)


@pytest.mark.parametrize('survivor', ['local', 'away', 'prisoner', 'unregistered_child'])
def test_martyrs_living_kin_anywhere_block_unlock(survivor):
    g = state()
    g.family = SectState('clan', '沈氏', kind='family', npcs=[
        person('fallen', alive=False, reason='势力征伐中阵亡'),
    ])
    living = person('survivor')
    if survivor == 'unregistered_child':
        g.player.offspring = [{'id': living.id, 'alive': True, 'cultivation_started': False}]
    elif survivor == 'prisoner':
        living.roster_state = 'held'
        living.roster_origin = [{'container': 'family', 'id': 'clan'}]
        g.inactive_npcs[living.id] = living
    else:
        if survivor == 'away': living.world = 'spirit'
        g.family.npcs.append(living)
    assert not family_kin_all_fallen(g)


def test_martyrs_empty_clan_and_only_outsiders_do_not_unlock():
    g = state()
    assert not family_kin_all_fallen(g)
    g.family = SectState('clan', '沈氏', kind='family')
    assert not family_kin_all_fallen(g)
    g.family.npcs.append(person('same_surname_outsider', kin=False))
    assert not family_kin_all_fallen(g)


def test_martyrs_dead_save_does_not_award_surviving_family_achievement():
    g = state()
    g.family = SectState('clan', '沈氏', kind='family', npcs=[
        person('fallen', alive=False, reason='势力征伐中阵亡'),
    ])
    g.player.alive = False
    assert not family_kin_all_fallen(g)


@pytest.mark.parametrize('office', ['actual', 'legacy_title', 'stale_title', 'guest', 'prisoner', 'away'])
def test_capture_records_office_provenance_before_roster_removal(office):
    g = state()
    npc, sect = lead(g, 'leader', 'original')
    npc.title = '掌门'
    record = g.intrigue_state['factions']['sect:original']
    if office == 'legacy_title': record['positions'] = {}
    elif office == 'stale_title': record['positions']['leader'] = None
    elif office == 'guest': record['positions']['guest_elder'] = npc.id
    elif office == 'prisoner': g.intrigue_state['npc_prisons'] = {npc.id: {}}
    elif office == 'away': npc.world = 'spirit'
    g.player.prisoners.append(g.detain_person({'id': npc.id}))
    assert not sect.npcs
    assert (leader_sect_before_capture(g, npc.id) == sect.id) == (office in {'actual', 'legacy_title'})
    assert GameState.from_dict(g.to_dict()).inactive_npcs[npc.id].roster_origin == npc.roster_origin


def test_martyrs_authoritative_person_overrides_stale_genealogy():
    g = state()
    npc = person('heir', alive=False, reason='势力征伐中阵亡')
    g.family = SectState('clan', '沈氏', kind='family', npcs=[npc])
    g.player.offspring = [{'id': npc.id, 'alive': True}]
    assert family_kin_all_fallen(g)
    npc.alive = True
    g.player.offspring[0].update(alive=False, death_reason='势力征伐中阵亡')
    assert not family_kin_all_fallen(g)


def test_martyrs_uses_existing_family_registry_precedence():
    g = state()
    npc = person('heir', alive=True)
    g.family = SectState('clan', '沈氏', kind='family', npcs=[npc])
    g.relationship_npcs[npc.id] = person(npc.id, alive=False, reason='势力征伐中阵亡')
    assert not family_kin_all_fallen(g)


@pytest.mark.parametrize('participation', ['attacker', 'defender', 'attacker_ally', 'defender_ally', 'deployed_ally'])
def test_corpse_accepts_former_sect_on_either_side_or_alliance(participation):
    g = state()
    war = {'id': 'campaign', 'world': 'human', 'kind': 'sect', 'status': 'active',
           'attacker_id': 'first', 'defender_id': 'second', 'coalitions': {}, 'roster_owner': {}}
    if participation in {'attacker', 'defender'}: war[participation + '_id'] = 'former'
    elif participation == 'deployed_ally': war['roster_owner']['ally'] = 'former'
    else: war['coalitions'][participation.split('_')[0]] = [{'id': 'former'}]
    g.wars = [war]
    g.player.puppets = [{'id': 'corpse', 'type': 'corpse', 'former_leader_sect_id': 'former', 'alive': False}]
    # Even a corpse destroyed in this fight really participated.
    record_corpse_campaign(g, 'campaign', [{'id': 'corpse', 'kind': 'corpse', 'power': 1}], [{}])
    assert g.player.milestones['former_leader_corpse_campaign'] == 1


@pytest.mark.parametrize('invalid', ['no_fight', 'not_deployed', 'living', 'zero_power', 'unrelated_war',
                                    'other_world', 'ended', 'missing_origin', 'no_war'])
def test_corpse_no_credit_for_carrying_preview_or_unrelated_battle(invalid):
    g = state()
    g.wars = [{'id': 'campaign', 'world': 'human', 'kind': 'sect', 'status': 'active',
               'attacker_id': 'former', 'defender_id': 'enemy'}]
    puppet = {'id': 'corpse', 'type': 'corpse', 'former_leader_sect_id': 'former'}
    g.player.puppets = [puppet]
    roster, rounds = [{'id': 'corpse', 'kind': 'corpse', 'power': 1}], [{}]
    if invalid == 'no_fight': rounds = []
    elif invalid == 'not_deployed': roster = []
    elif invalid == 'living': puppet['type'] = roster[0]['kind'] = 'living'
    elif invalid == 'zero_power': roster[0]['power'] = 0
    elif invalid == 'unrelated_war': g.wars[0]['attacker_id'] = 'unrelated'
    elif invalid == 'other_world': g.wars[0]['world'] = 'spirit'
    elif invalid == 'ended': g.wars[0]['status'] = 'ended'
    elif invalid == 'missing_origin': puppet.pop('former_leader_sect_id')
    elif invalid == 'no_war': g.wars.clear()
    record_corpse_campaign(g, 'campaign', roster, rounds)
    assert not g.player.milestones


@pytest.fixture
def engine(tmp_path):
    return GameEngine(ROOT, tmp_path / 'saves')


def merchant_game(engine):
    g = engine._load(engine.create_game('本盟委托', 'supreme_fire', 'dao', 351, preset_id='core')['id'])
    alliance = g.merchant_state['worlds']['human'][0]
    g.player.location_id = alliance['hq']
    add_item(g.player, 'spirit_stone', 10**8)
    engine.store.save(g)
    engine.merchant_action(g.id, 'join', {'alliance_id': alliance['id']})
    return g.id, alliance


def test_merchant_real_submit_persists_unlock_and_never_repeats(engine):
    identity, alliance = merchant_game(engine)
    payload = {'alliance_id': alliance['id'], 'kind': 'weapon', 'material_tier': 1}
    engine.preview_merchant_commission(identity, payload)
    assert 'merchant_post_to_own_alliance' not in engine.achievements.metadata.read()['achievements']
    result = engine.merchant_action(identity, 'post', payload)
    assert '黑钱洗白' in {row['name'] for row in result['new_achievements']}
    loaded = engine.store.load(identity)
    assert loaded.player.milestones['posted_to_own_alliance'] == 1
    assert loaded.merchant_state['posted'][-1]['status'] == 'open'
    assert '黑钱洗白' not in {row['name'] for row in engine.get_game(identity)['new_achievements']}


def test_merchant_failed_submit_does_not_unlock_or_spend(engine):
    identity, alliance = merchant_game(engine)
    before = engine.store.load(identity).to_dict()
    with pytest.raises(ValueError):
        engine.merchant_action(identity, 'post', {'alliance_id': alliance['id'], 'kind': 'weapon', 'material_tier': 99})
    assert engine.store.load(identity).to_dict() == before
    assert 'merchant_post_to_own_alliance' not in engine.achievements.metadata.read()['achievements']


@pytest.mark.parametrize('battle_mode', ['carry_only', 'round', 'vanguard', 'former_attacker', 'attacker_ally', 'defender_ally'])
def test_capture_keeps_actual_office_through_reassignment_and_save(engine, battle_mode):
    g = engine._load(engine.create_game('先帝验收', 'supreme_fire', 'demonic', 352, preset_id='core')['id'])
    npc, sect = lead(g, 'former_leader', 'former_sect')
    assert leader_sect_before_capture(g, npc.id) == sect.id
    held = g.detain_person({'id': npc.id, 'combat_power': 1})
    g.player.prisoners.append(held)
    g.intrigue_state['factions'][f'sect:{sect.id}']['positions']['leader'] = None
    g.player.realm_index = 4
    g.player.path = 'demonic'
    g.player.divine_sense_rank = 4
    g.rng_state = encode_rng(random.Random(1))
    engine.store.save(g)
    shown = engine.captive_action(g.id, npc.id, 'corpse')
    loaded = engine.store.load(g.id)
    assert loaded.player.puppets[-1]['former_leader_sect_id'] == sect.id
    assert loaded.player.puppets[-1]['source_npc_id'] == npc.id
    assert '先帝还在创业' not in {row['name'] for row in shown['new_achievements']}
    if battle_mode == 'carry_only':
        return
    original = loaded.sects[sect.id]
    original.extinct = False
    original.npcs.append(person('successor', faction_id=sect.id))
    loaded.player.realm_index = 5
    loaded.player.lifespan = 10000
    loaded.player.faction_id = 'wanmo'
    if battle_mode.endswith('_ally'):
        war = engine._start_war(loaded, 'sect', 'wanmo', 'tianjian', initiated_by_player=True)
        side = battle_mode.split('_')[0]
        engine._add_war_participant(loaded, war, side, sect.id, war[side + '_id'])
    elif battle_mode == 'former_attacker':
        war = engine._start_war(loaded, 'sect', sect.id, 'wanmo', initiated_by_player=True)
    else:
        war = engine._start_war(loaded, 'sect', 'wanmo', sect.id, initiated_by_player=True)
    engine.store.save(loaded)
    if battle_mode != 'vanguard':
        fought = engine.war_action(g.id, war['id'], 'participate_round')
    else:
        offered = engine.war_action(g.id, war['id'], 'conquest')
        assert '先帝还在创业' not in {row['name'] for row in offered['new_achievements']}
        fought = engine.choose(g.id, 'fight')
    assert '先帝还在创业' in {row['name'] for row in fought['new_achievements']}
    assert engine.store.load(g.id).player.milestones['former_leader_corpse_campaign'] == 1
    assert '先帝还在创业' not in {row['name'] for row in engine.get_game(g.id)['new_achievements']}


def test_existing_kin_and_office_evidence_unlocks_after_reload(engine):
    g = engine._load(engine.create_game('家族功业', 'supreme_fire', 'dao', 353, preset_id='core')['id'])
    son, _ = lead(g, 'son', 'first')
    daughter, _ = lead(g, 'daughter', 'second')
    g.player.offspring = [son.to_dict(), daughter.to_dict()]
    engine.store.save(g)
    assert '教父' in {row['name'] for row in engine.get_game(g.id)['new_achievements']}
    g = engine.store.load(g.id)
    g.family = SectState('clan', '沈氏', kind='family', npcs=[
        person('fallen', alive=False, reason='势力征伐中阵亡'), person('outsider', kin=False),
    ])
    g.player.offspring = []
    engine.store.save(g)
    assert '满门忠烈' in {row['name'] for row in engine.get_game(g.id)['new_achievements']}


def test_last_kin_falls_in_actual_war_command_and_unlocks(engine):
    g = engine._load(engine.create_game('最后族人', 'supreme_fire', 'dao', 355, preset_id='core')['id'])
    g.player.realm_index = 5
    g.player.lifespan = 10000
    g.player.faction_id = None
    g.family = SectState('last_clan', '沈氏', kind='family', founded_by_player=True,
                         founder_player_id=g.id, npcs=[person('last_kin')])
    foe = person('enemy', faction_id='enemy_sect')
    foe.realm_index = 5
    foe.combat_factor = 10**8
    g.sects['enemy_sect'] = SectState('enemy_sect', '敌宗', npcs=[foe])
    g.rng_state = encode_rng(random.Random(1))
    war = engine._start_war(g, 'sect', 'enemy_sect', g.family.id, initiated_by_player=True)
    engine.store.save(g)
    result = engine.war_action(g.id, war['id'], 'round')
    saved = engine.store.load(g.id)
    assert not saved.family.npcs[0].alive
    assert saved.family.npcs[0].death_reason == '势力征伐中阵亡'
    assert saved.player.alive
    assert '满门忠烈' in {row['name'] for row in result['new_achievements']}
