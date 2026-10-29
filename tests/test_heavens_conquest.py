"""Actual frontier war, unchanged headquarters, original soldiers and treaties."""
import copy
import pytest
from test_heavens_development import established, branch, local, tick
from test_heavens_outposts import act
from cultivation_life.system.heavens import outpost_conquest as conquest, outpost_development as development
from cultivation_life.system.heavens import outpost_runtime as base
from cultivation_life.system.heavens.outpost_schema import validate_references
from cultivation_life.system.economy.ledger import balance, transfer_value
from cultivation_life.system.economy import organizations
from cultivation_life.system.territory import state as territory
from cultivation_life.system.war import requirements
from cultivation_life.world_state import race_pair


def prepare(bundle):
    # A real original enemy headquarters is adjacent to the original built
    # frontier. No NPC, faction, inventory or treasury is copied.
    game,row=local(bundle)
    enemy=next(s for s in game.sects.values() if s.world=='demon' and s.kind=='sect' and s.npcs)
    site=next(loc for loc,_ in bundle[0].maps._graphs['demon']['red_marrow_city'] if not bundle[0].maps.location('demon',loc).get('min_realm_index',0))
    enemy.location_id=site
    for npc in enemy.npcs:
        npc.location_id='red_marrow_city';npc.realm_index=1;npc.layer=1
    enemy.npcs[0].location_id=site
    organizations.register(game,'sect',enemy.id,'demon')
    game.intrigue_state['factions']['sect:'+enemy.id]['resources']=100000
    bundle[0].store.save(game)
    act(bundle,'outpost_return')
    act(bundle,'outpost_military_authorize')
    act(bundle,'outpost_depart')
    act(bundle,'outpost_develop')
    act(bundle,'outpost_invest')
    act(bundle,'outpost_invest')
    game,row=local(bundle)
    worker=development.workers(bundle[2],game,row)[0]['id']
    return worker,enemy.id,site


def start(bundle):
    worker,enemy,site=prepare(bundle)
    act(bundle,'outpost_war_start',dict(person_id=worker,rival_id=enemy))
    return worker,enemy,site


def end(bundle,years=180):
    return tick(bundle,lambda g,r: conquest.current(g,r) is None,years)


def test_actual_campaign_marches_fights_and_vassalizes_without_moving_headquarters(branch):
    worker,enemy,site=start(branch)
    game,row=local(branch);war=conquest.current(game,row)
    assert game.world_npcs[worker].location_id=='red_marrow_city'
    assert requirements.deployed_people(game,war,'attacker',arrived_only=True)==[]
    assert game.sects['tianjian'].world=='human'
    original_rng=game.rng_state
    with pytest.raises(ValueError,match='真实胜利'):act(branch,'outpost_war_vassal')
    game,row=tick(branch,lambda g,r: (w:=conquest.current(g,r))['status']=='peace_ready' and w['frontier']['occupation_awarded'],160)
    war=conquest.current(game,row)
    assert game.rng_state==original_rng  # The regional/individual stream is not overwritten.
    assert war['winner']=='attacker' and war['battles']>0 and war['war_score']>=55
    assert game.world_npcs[worker].location_id==site and game.player.location_id=='red_marrow_city'
    act(branch,'outpost_war_vassal')
    game,row=local(branch)
    relation=game.sect_relations[race_pair('tianjian',enemy)]
    assert (relation['status'],relation['overlord'],relation['subject'])==('vassal','tianjian',enemy)
    assert game.sects[enemy].world=='demon' and not game.sects[enemy].extinct
    assert game.world_npcs[worker].location_id==site
    game,row=end(branch)
    assert conquest.wars(game,row)[-1]['campaign_phase']=='home'
    assert game.world_npcs[worker].location_id=='red_marrow_city'
    assert game.world_npcs[row['governor_id']].location_id=='red_marrow_city'
    assert game.sects['tianjian'].location_id=='wudi_plain'
    validate_references(game)
    war=conquest.wars(game,row)[-1]
    from cultivation_life.system.war.logistics import wallet
    assert war['logistics']['refunded']
    assert not balance(game,wallet(war,'attacker'))


def test_early_white_peace_returns_from_actual_departure_and_never_refunds_twice(branch):
    worker,_,_=start(branch)
    game,row=local(branch);war=conquest.current(game,row)
    primary=next(u for u in row['units'] if u['person_id']==worker)
    before=balance(game,base.wallet(row));road=balance(game,primary['wallet'])
    act(branch,'outpost_war_stop')
    assert balance(local(branch)[0],base.wallet(row))==before
    game,row=end(branch,2)
    assert balance(game,base.wallet(row))>=before+30000-200
    returned=balance(game,primary['wallet']); assert returned<road
    frozen=balance(game,base.wallet(row))
    tick(branch,years=1)
    assert balance(local(branch)[0],base.wallet(row))==frozen-100


def test_mandate_required_and_failed_start_preserves_entire_save(branch):
    worker,enemy,site=prepare(branch)
    game,row=local(branch);row.pop('military');branch[0].store.save(game)
    path=branch[0].store._path(branch[1]);before=path.read_bytes()
    with pytest.raises(ValueError,match='总部另行批准'):act(branch,'outpost_war_start',dict(person_id=worker,rival_id=enemy))
    assert path.read_bytes()==before
    with pytest.raises(ValueError,match='原总部'):act(branch,'outpost_military_authorize')
    assert path.read_bytes()==before


def test_real_frontier_and_treasury_required_no_governor_or_duplicate_war(branch):
    worker,enemy,_=prepare(branch)
    game,row=local(branch)
    with pytest.raises(ValueError,match='负责人须留守'):act(branch,'outpost_war_start',dict(person_id=row['governor_id'],rival_id=enemy))
    territory.state(game)['holdings']['demon']['red_marrow_city']['tianjian']['outpost']=False
    branch[0].store.save(game)
    with pytest.raises(ValueError,match='实际驻点'):act(branch,'outpost_war_start',dict(person_id=worker,rival_id=enemy))


def test_actual_world_freezes_war_and_custody_stops_travel_without_charges(branch):
    from cultivation_life.regional_context import CalendarGame
    from cultivation_life.engine.world.regions import ensure
    worker,_,_=start(branch)
    game,row=local(branch);ensure(branch[0]._dependencies.regions,game)
    before=copy.deepcopy(game.to_dict())
    base.year_step(branch[2],CalendarGame(game,'human',game.player.age+1))
    assert game.to_dict()==before
    game.intrigue_state.setdefault('npc_prisons',{})[worker]={'test':True}
    war=conquest.current(game,row);progress=copy.deepcopy(war['journeys']['attacker'])
    base.year_step(branch[2],CalendarGame(game,'demon',game.player.age+1))
    assert war['journeys']['attacker']==progress


def test_preview_and_invalid_duplicate_old_actions_are_atomic(branch):
    from cultivation_life.system.heavens import outposts
    worker,enemy,_=start(branch)
    game,row=local(branch);before=copy.deepcopy(game.to_dict())
    outposts.project(branch[2],game)
    assert game.to_dict()==before
    path=branch[0].store._path(branch[1]);stored=path.read_bytes()
    with pytest.raises(ValueError):act(branch,'outpost_war_start',dict(person_id=worker,rival_id=enemy))
    with pytest.raises(ValueError,match='原军令入口'):branch[0].war_action(branch[1],conquest.current(game,row)['id'],'battle')
    with pytest.raises(ValueError,match='原军令入口'):branch[0].war_peace(branch[1],conquest.current(game,row)['id'],'vassal')
    assert path.read_bytes()==stored


def test_physical_death_ends_original_deployment_and_loses_original_cash(branch):
    worker,_,_=start(branch)
    game,row=local(branch);game.world_npcs[worker].alive=False
    people=set(game.world_npcs);branch[0].store.save(game)
    game,row=end(branch,5)
    primary=next(u for u in row['units'] if u['person_id']==worker)
    assert primary['phase']=='lost' and not balance(game,primary['wallet'])
    assert set(game.world_npcs)==people and not game.world_npcs[worker].alive
    assert not conquest.wars(game,row)[-1].get('winner')


def test_victory_must_be_real_and_holding_objective_is_once_only(branch):
    _,_,_=start(branch)
    game,row=tick(branch,lambda g,r: bool((w:=conquest.current(g,r)) and w['frontier']['occupation_awarded']),120)
    war=conquest.current(game,row);assert war and war['frontier']['occupation']==5
    score=war['war_score'];tick(branch,years=8)
    game,row=local(branch);assert conquest.current(game,row)['war_score']==score
    war=conquest.current(game,row);war['frontier']['victory_battles']=0
    branch[0].store.save(game)
    with pytest.raises(ValueError,match='真实胜利'):act(branch,'outpost_war_vassal')


def test_active_war_blocks_base_withdraw_and_original_hq_cannot_open_another_war(branch):
    worker,enemy,_=start(branch)
    with pytest.raises(ValueError,match='等待原军队'):act(branch,'outpost_withdraw')
    game,row=local(branch)
    from cultivation_life.system.war.occupancy import busy
    assert busy(game,game.sects['tianjian'],managed_only=True) and busy(game,game.sects[enemy],managed_only=True)
    with pytest.raises(ValueError):branch[0]._start_war(game,'sect','tianjian',enemy,initiated_by_player=True)


def test_no_money_or_treaty_bypasses(branch):
    worker,enemy,_=prepare(branch)
    game,row=local(branch)
    relation=game.sect_relations.setdefault(race_pair('tianjian',enemy),{})
    relation.update(status='truce',truce_until_age=game.player.age+100)
    branch[0].store.save(game)
    with pytest.raises(ValueError,match='停战期'):act(branch,'outpost_war_start',dict(person_id=worker,rival_id=enemy))
    relation.update(status='neutral',truce_until_age=0)
    transfer_value(game,base.wallet(row),'player',balance(game,base.wallet(row)),'test original cash withdrawal')
    branch[0].store.save(game)
    with pytest.raises(ValueError,match='当地须实有军费'):act(branch,'outpost_war_start',dict(person_id=worker,rival_id=enemy))


def test_closed_road_refuses_dispatch_and_failed_commands_do_not_create_a_war(branch):
    from dataclasses import replace
    worker,enemy,_=prepare(branch)
    broken=branch[0],branch[1],replace(branch[2],outpost_road=lambda *args:None)
    path=branch[0].store._path(branch[1]);before=path.read_bytes()
    with pytest.raises(ValueError,match='合法往返道路'):act(broken,'outpost_war_start',dict(person_id=worker,rival_id=enemy))
    assert path.read_bytes()==before and not local(branch)[0].wars


def test_family_mandate_retains_original_family_and_uses_the_same_war_entry(branch):
    game,row=local(branch)
    family=game.sects.pop('tianjian');family.kind='family';game.family=family;row['owner_kind']='family'
    organizations.register(game,'family',family.id,'human')
    game.intrigue_state['factions']['family:tianjian']['controller_id']='player'
    branch[0].store.save(game)
    worker,enemy,_=prepare(branch)
    act(branch,'outpost_war_start',dict(person_id=worker,rival_id=enemy))
    game,row=local(branch);war=conquest.current(game,row)
    assert game.family.id==war['attacker_id']=='tianjian' and game.family.world=='human'
    assert 'tianjian' not in game.sects and war['world']=='demon'
    validate_references(game)


def test_surrender_revalidates_original_target_and_leaves_treaty_unsigned(branch):
    _,enemy,_=start(branch)
    game,row=tick(branch,lambda g,r: bool((w:=conquest.current(g,r)) and w['frontier']['occupation_awarded']),120)
    game.sects[enemy].location_id='red_marrow_city'
    branch[0].store.save(game)
    with pytest.raises(ValueError,match='目标驻地已变化'):act(branch,'outpost_war_vassal')
    assert local(branch)[0].sect_relations[race_pair('tianjian',enemy)]['status']=='war'


def test_military_reference_contract_rejects_duplicate_and_inconsistent_authority(branch):
    _,_,_=start(branch)
    game,row=local(branch);war=conquest.current(game,row)
    row['military']['source']='demon'
    from cultivation_life.system.heavens.outpost_schema import validate_outposts
    with pytest.raises(ValueError,match='军令不属于'):validate_outposts(game.heavens_state['runtime']['outposts'])
    row['military']['source']='human'
    war['journeys']['attacker'][0]['destination']='red_marrow_city'
    with pytest.raises(ValueError):validate_references(game)


def test_existing_defensive_guests_are_local_original_people_and_quote_is_read_only(branch,monkeypatch):
    from cultivation_life.content_registry import WORLD_SYSTEMS
    from cultivation_life.system.heavens import outposts
    worker,enemy,site=prepare(branch)
    monkeypatch.setitem(WORLD_SYSTEMS['intrigue_dlc'],'enabled',True)
    game,row=local(branch)
    host=game.sects[enemy]
    guest=next(n for e in game.sects.values() if e.id!=enemy and e.world=='demon' for n in e.npcs)
    guest.location_id=site
    game.intrigue_state['factions']['sect:'+enemy].setdefault('guests',[]).append(dict(npc_id=guest.id,defense_required=True))
    branch[0].store.save(game)
    before=copy.deepcopy(game.to_dict());outposts.project(branch[2],game)
    assert game.to_dict()==before
    game.wars.append(dict(status='active',roster={'attacker':[guest.id]}))
    assert guest.id not in {n.id for n in branch[2].outpost_defenders(game,row,site,enemy)['people']}
    game.wars.pop()
    act(branch,'outpost_war_start',dict(person_id=worker,rival_id=enemy))
    game,row=local(branch);war=conquest.current(game,row)
    assert guest.id in war['roster']['defender'] and guest.id in war['defensive_guests']
    assert game.sects[host.id].npcs[0].id in war['roster']['defender']


def test_original_native_recruits_with_implicit_hq_are_real_defenders(branch):
    worker,enemy,site=prepare(branch)
    game,row=local(branch);person=game.sects[enemy].npcs[1]
    person.location_id=None;branch[0].store.save(game)
    act(branch,'outpost_war_start',dict(person_id=worker,rival_id=enemy))
    game,row=local(branch);war=conquest.current(game,row)
    actual=next(n for n in game.sects[enemy].npcs if n.id==person.id)
    assert actual.location_id==site and person.id in war['roster']['defender']
    game,row=tick(branch,lambda g,r:conquest.current(g,r)['campaign_phase']=='engaged',50)
    assert person.id in {n.id for n in requirements.deployed_people(game,conquest.current(game,row),'defender',arrived_only=True)}


def test_returned_original_soldier_is_not_a_second_deployment_while_enemy_is_held(branch):
    worker,enemy,_=start(branch)
    game,row=local(branch);defender=conquest.current(game,row)['roster']['defender'][0]
    game.intrigue_state.setdefault('npc_prisons',{})[defender]={'test':True}
    branch[0].store.save(game)
    act(branch,'outpost_war_stop')
    game,row=tick(branch,years=1)
    assert conquest.current(game,row)['campaign_phase']=='returning'
    assert next(u for u in row['units'] if u['person_id']==worker)['phase']=='stationed'
    validate_references(game)


