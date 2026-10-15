"""Real commands for fixed guard sites and imprisoned members' economic roles."""
import copy
import random

import pytest

from test_other_systems_audit_fixes import api, snapshot
from test_ownership_prison_fixes import organization_game
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.system.formation_system import formation_material_definitions, make_formation_material_instance
from cultivation_life.system.economy import organizations
from cultivation_life.system.economy.ledger import transfer_value
from cultivation_life.system.war import requirements, logistics


def ready_org(engine, kind='sect'):
    game, identity = organization_game(engine, kind)
    entity = game.sects['audit_org'] if kind=='sect' else game.family
    entity.location_id = game.player.location_id
    entity.npcs[0].location_id = entity.location_id
    entity.npcs[0].realm_index = 3
    entity.npcs[0].lifespan = 100000
    game.player.next_tribulation_age = None
    organizations.register(game, kind, entity.id, entity.world)
    transfer_value(game, 'background:human', organizations.key(kind, entity.id), 1000000, '隔离验收预算')
    engine.store.save(game)
    return engine._load(game.id), identity


def deploy_guard(engine, act, game):
    definitions = formation_material_definitions()
    rows = [make_formation_material_instance(definitions[k], source='隔离验收', origin_world='human')
            for k in ('human_greenwood_stake', 'human_red_sun_sand', 'human_xuanyin_stone')]
    game.player.formation_materials.extend(rows)
    engine.store.save(game)
    act(game.id, 'formation-save', name='驻地守阵验收', slots=[r['id'] for r in rows]+[None]*6, activate=True)
    act(game.id, 'formation-ground-deploy', owner_kind='sect')
    return engine._load(game.id)


def relocate_guard(engine, act):
    game, _ = ready_org(engine)
    game = deploy_guard(engine, act, game)
    old = game.sects['audit_org'].location_id
    plan = next(r for r in engine.get_game(game.id)['map']['organization_relocation'] if r['kind']=='sect')
    destination = plan['destinations'][0]['id']
    act(game.id, 'organization-action', kind='sect', owner_id='audit_org', action='relocate', location_id=destination)
    act(game.id, 'map-travel', destination=destination)
    return engine._load(game.id), old, destination


def defense_event(engine, game, *, followup=False):
    event = engine._instantiate_event(engine.events_by_id['EVT_PLAYER_SECT_DEFENSE_001'], game, random.Random(1))
    event['runtime'] = dict(sect_id='audit_org', required_power=1, stage=1)
    if followup:
        event['_followup_event'] = copy.deepcopy(engine._prepare_treasure_reward_event(game, random.Random(7)))
    game.pending_event = event
    engine.store.save(game)
    return event


def test_relocation_keeps_original_materials_but_never_defends_new_hq_until_rebuilt(api):
    engine, act = api
    game, old, destination = relocate_guard(engine, act)
    original = copy.deepcopy(game.player.formation_ground_arrays[0])
    assert original['location_id']==old!=destination
    assert engine._sect_guard_array(game, 'audit_org') is None
    assert engine._sect_guard_power(game, 'audit_org')==0
    event = defense_event(engine, game, followup=True)
    reward = copy.deepcopy(event['_followup_event'])
    shown = engine.get_game(game.id)
    assert next(c for c in shown['pending_event']['choices'] if c['id']=='formation')['enabled']
    act(game.id, 'choice', event_id=event['id'], choice_id='formation')
    saved = engine._load(game.id)
    assert saved.sects['audit_org'].pressure==1
    assert saved.player.formation_ground_arrays==[original]
    assert saved.pending_event['runtime']==reward['runtime']
    act(game.id, 'choice', event_id=reward['id'], choice_id='pill')
    frozen = snapshot(engine, game.id)
    act(game.id, 'formation-ground-withdraw', status=400, ground_formation_id=original['id'])
    assert engine.store._path(game.id).read_bytes()==frozen
    # New real materials deployed at the new HQ restore legal defense.
    saved = deploy_guard(engine, act, engine._load(game.id))
    current = saved.player.formation_ground_arrays[-1]
    assert engine._sect_guard_array(saved, 'audit_org')['id']==current['id']
    event = defense_event(engine, saved)
    act(game.id, 'choice', event_id=event['id'], choice_id='formation')
    saved = engine._load(game.id)
    assert saved.sects['audit_org'].pressure==1
    assert saved.player.formation_ground_arrays[0]==original
    assert saved.player.formation_ground_arrays[-1]['battles']==1


@pytest.mark.parametrize('site', ['local', 'remote', 'foreign_world'])
def test_war_guard_power_command_array_and_wear_share_battlefield_address(api, site):
    engine, act = api
    game, _ = ready_org(engine)
    game = deploy_guard(engine, act, game)
    array = game.player.formation_ground_arrays[0]
    game.player.faction_id = None  # Measure infrastructure without the player's personal combat power.
    world = 'spirit' if site=='foreign_world' else 'human'
    location = (next(r['id'] for r in engine.maps.worlds[world]['locations'] if not r.get('min_realm_index') and r['id']!=array['location_id'])
                if site!='local' else array['location_id'])
    war = dict(id='guard-site', kind='sect', world=world, location_id=location,
        attacker_id='tianjian', defender_id='audit_org', start_unit=0,
        coalitions={'attacker':[{'id':'tianjian'}], 'defender':[{'id':'audit_org'}]},
        roster={'attacker':[], 'defender':[]})
    before = copy.deepcopy(array)
    power = engine._war_total_power(game, war, 'defender', include_player=False)
    entity_power = engine._war_entity_power(game, war, 'defender', 'audit_org')
    command = engine._war_side_formation(game, war, 'defender')
    engine._wear_war_guard_arrays(game, war)
    if site=='local':
        assert power>0 and entity_power>0 and command['source_kind']=='sect_guard'
        assert array['durability']==before['durability']-2.5 and array['battles']==1
    else:
        assert power==0 and not command['active']
        assert entity_power==0
        assert array==before


@pytest.mark.parametrize('kind', ['sect', 'family'])
def test_imprisoned_only_member_has_care_but_no_labor_or_sales_and_release_recovers(api, monkeypatch, kind):
    engine, act = api
    game, identity = ready_org(engine, kind)
    act(game.id, 'intrigue-personnel', kind=kind, action='imprison', npc_id=identity, years=500)
    seen = []
    original = engine._advance_world_year
    def observe(actual, *args, **kwargs):
        result = original(actual, *args, **kwargs)
        entity = actual.sects['audit_org'] if kind=='sect' else actual.family
        if [n.id for n in entity.npcs]==[identity] and engine._intrigue_is_imprisoned(actual, identity):
            seen.append(copy.deepcopy(actual.economy_v2['organizations'][organizations.key(kind,entity.id)]))
        return result
    with monkeypatch.context() as patch:
        patch.setattr(engine, '_advance_world_year', observe)
        act(game.id, 'advance', action='rest', years=1)
    assert seen
    for row in seen:
        assert row['labor_capacity']==row['produced']==row['income']==row['turnover']==0
        assert row['workforce']=={'3':1} and row['expected_upkeep']>0
    act(game.id, 'intrigue-personnel', kind=kind, action='release', npc_id=identity)
    act(game.id, 'advance', action='rest', years=1)
    saved = engine._load(game.id)
    row = saved.economy_v2['organizations'][organizations.key(kind,'audit_org')]
    assert row['labor_capacity']>0 and row['produced']>0


@pytest.mark.parametrize('mode', ['release','expiry','disabled'])
def test_prison_war_demand_rebuilds_on_custody_change_and_real_deployment(api, monkeypatch, mode):
    engine, act = api
    game, identity = ready_org(engine)
    act(game.id, 'intrigue-resolution', kind='sect', resolution_type='declare_war', target_id='tianjian')
    game = engine._load(game.id)
    war = next(w for w in game.wars if w['attacker_id']=='audit_org' and w['defender_id']=='tianjian')
    act(game.id, 'intrigue-personnel', kind='sect', action='imprison', npc_id=identity, years=1 if mode=='expiry' else 500)
    game = engine._load(game.id)
    war = next(w for w in game.wars if w['id']==war['id'])
    assert not engine._available_warriors(game, war, 'attacker')
    assert 3 not in requirements.groups(game, war, 'attacker')
    assert war['logistics']['sides']['attacker']['reference_need']==logistics.need(game,war,'attacker')
    rng = game.rng_state
    frozen = copy.deepcopy(game.to_dict())
    logistics.public(game, war, 'attacker')
    assert game.to_dict()==frozen and game.rng_state==rng
    act(game.id, 'war-action', war_id=war['id'], action='deploy_all')
    if mode=='release':
        act(game.id, 'intrigue-personnel', kind='sect', action='release', npc_id=identity)
    elif mode=='expiry':
        # Original yearly settlement, without advancing an entire war action unit.
        from cultivation_life.system.intrigue.custody import advance_prison_year
        game = engine._load(game.id)
        advance_prison_year(game)
        engine.store.save(game)
    else:
        monkeypatch.setitem(WORLD_SYSTEMS['intrigue_dlc'], 'enabled', False)
    game = engine._load(game.id)
    war = next(w for w in game.wars if w['id']==war['id'])
    if mode!='disabled':
        assert requirements.groups(game,war,'attacker')[3]==1
        assert war['logistics']['sides']['attacker']['reference_need']==logistics.need(game,war,'attacker')
    act(game.id, 'war-action', war_id=war['id'], action='deploy_all')
    saved = engine._load(game.id)
    w = next(w for w in saved.wars if w['id']==war['id'])
    assert requirements.groups(saved,w,'attacker')[3]==1
    assert any(n.id==identity for n in engine._available_warriors(saved,w,'attacker'))


def test_prisoner_never_bills_or_consumes_grade_three_battle_supplies(api):
    engine, act = api
    game, identity = ready_org(engine)
    act(game.id, 'intrigue-resolution', kind='sect', resolution_type='declare_war', target_id='tianjian')
    game = engine._load(game.id)
    war = next(w for w in game.wars if w['attacker_id']=='audit_org' and w['defender_id']=='tianjian')
    act(game.id, 'intrigue-personnel', kind='sect', action='imprison', npc_id=identity, years=500)
    act(game.id, 'war-action', war_id=war['id'], action='deploy_all')
    saved = engine._load(game.id)
    war = next(w for w in saved.wars if w['id']==war['id'])
    control = copy.deepcopy(saved)
    control.sects['audit_org'].npcs.clear()
    cw = next(w for w in control.wars if w['id']==war['id'])
    requirements.refresh(control, cw, 'attacker')
    assert logistics.need(saved, war, 'attacker')==logistics.need(control,cw,'attacker')
    act(game.id, 'war-action', war_id=war['id'], action='round')
    saved = engine._load(game.id)
    war = next(w for w in saved.wars if w['id']==war['id'])
    assert 3 not in requirements.groups(saved,war,'attacker')
    consumed = war['logistics']['sides']['attacker']['consumed_items']
    market = saved.economy_v2['markets']['human:'+war['logistics']['sides']['attacker']['location']]
    assert not any(n and market['commodities'][k]['tier']==3 for k,n in consumed.items())


def test_imprisoned_elder_has_no_labor_bonus_and_disabled_dlc_keeps_original_semantics(api, monkeypatch):
    engine, act = api
    game, identity = ready_org(engine)
    act(game.id,'intrigue-personnel',kind='sect',action='imprison',npc_id=identity,years=500)
    game = engine._load(game.id)
    entity = game.sects['audit_org']
    game.intrigue_state['factions']['sect:audit_org']['positions']['war_elder']=identity
    row = game.economy_v2['organizations'][organizations.key('sect',entity.id)]
    credit = row['production_credit'] = 10000
    assert organizations.produce(game,engine.maps,entity,row)==0
    assert row['production_credit']==credit and row['territory_elder_factor']==1
    assert row['expected_upkeep']>0
    monkeypatch.setitem(WORLD_SYSTEMS['intrigue_dlc'],'enabled',False)
    assert organizations.produce(game,engine.maps,entity,row)>0
    assert row['labor_capacity']>0 and row['territory_elder_factor']==.7
    assert identity in game.intrigue_state['npc_prisons']
