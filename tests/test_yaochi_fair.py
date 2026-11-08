"""Original estate, paid years, independent people and competition settlement."""
import copy
from unittest.mock import patch
import pytest
from test_immortal_cultivation import prepared
from test_yaochi_westward import pool
from cultivation_life.models import SectNpc
from cultivation_life.rules import add_item
from cultivation_life.system import yaochi_fair as fair,yaochi_garden as garden
from cultivation_life.system.yaochi_fair_rules import active
from cultivation_life.system.economy.ledger import balance,transfer_value
from cultivation_life.system.westward_finance import YAOCHI
from cultivation_life.person_assignments import research_assignment

def cmd(e,gid,action,value='',amount=1):
    key='garden' if action.startswith('garden_') else 'fair'
    shown=e.get_game(gid)['yaochi'][key]
    return e.yaochi_action(gid,action,shown['token']+'|'+value,amount)

def work(e,gid,kind='fair'):
    with patch('cultivation_life.engine.orchestration.advancement._finish_action_events',return_value=None):
        return cmd(e,gid,kind+'_work')

def opponent(e,gid):
    g=e._load(gid);n=SectNpc('fair-witness','赴会同道','散修',9,1,30,100000,world='celestial',location_id=g.player.location_id)
    g.world_npcs[n.id]=n;e.store.save(g);return n.id

def array(e,gid):
    from cultivation_life.system.formation_system import formation_material_definitions,make_formation_material_instance
    g=e._load(gid);definitions=formation_material_definitions()
    choices=[d for d in definitions.values() if d.get('world')=='celestial'][:3]
    materials=[make_formation_material_instance(d,source='验收原阵材',origin_world='celestial') for d in choices]
    g.player.formation_materials.extend(materials);e.store.save(g)
    e.save_formation(gid,dict(name='仙会护阵',slots=[m['id'] for m in materials]+[None]*(9-len(materials)),activate=True))

def damage(e,gid,identity):
    e.building_action(gid,'manage',building_id=identity)
    from test_building_system import choose
    choose(e,gid,'destroy')
    choice=next(c['id'] for c in e.get_game(gid)['pending_event']['choices'] if c['id'].startswith('destroy:'))
    choose(e,gid,choice);choose(e,gid,'leave')

def leased(e,gid):
    cmd(e,gid,'garden_lease');cmd(e,gid,'garden_fund',amount=1000000)
    row=e.get_game(gid)['yaochi']['garden']['recipes'][0]
    cmd(e,gid,'garden_configure',row['id'],2)
    return row

def test_views_do_not_create_deeds_or_draw_people(pool):
    e,gid=pool;g=e._load(gid);before=copy.deepcopy(g.to_dict())
    fair.public(g);garden.public(g)
    assert g.to_dict()==before

def test_lease_original_production_and_delivery(pool):
    e,gid=pool;recipe=leased(e,gid);g=e._load(gid);row=garden.estate(g)
    assert row['owner_kind']=='yaochi' and row['id']==garden.identity()
    cmd(e,gid,'garden_order');cmd(e,gid,'garden_start');g=e._load(gid)
    assert garden.estate(g)['job']['quantity']==8
    work(e,gid,'garden');g=e._load(gid);row=garden.estate(g)
    assert row['produced']>=8 and not row['job']
    cash=balance(g,row['operating_lease']['wallet']);total=row['operating_lease']['order']['total']
    cmd(e,gid,'garden_deliver');g=e._load(gid)
    assert balance(g,garden.lease(g)['wallet'])==cash+total and not garden.estate(g)['stock']
    cmd(e,gid,'garden_close');g=e._load(gid)
    assert not garden.lease(g) and garden.estate(g)['owner_kind']=='yaochi'
    assert g.yaochi_state['merit']==100000

def test_expiry_no_new_production_but_original_batch_can_finish(pool):
    e,gid=pool;leased(e,gid);cmd(e,gid,'garden_start');g=e._load(gid)
    garden.lease(g)['until']=g.player.age+1;e.store.save(g)
    work(e,gid,'garden');g=e._load(gid)
    assert garden.estate(g)['stock'] and not garden.estate(g)['enabled']
    with pytest.raises(ValueError,match='期已满'):cmd(e,gid,'garden_start')
    item,n=next(iter(garden.estate(g)['stock'].items()));cmd(e,gid,'garden_withdraw',item,n);cmd(e,gid,'garden_close')

def test_stale_quote_and_title_transfer_refused_atomically(pool):
    e,gid=pool;shown=e.get_game(gid)['yaochi']['garden'];cmd(e,gid,'garden_lease')
    before=e.store._path(gid).read_bytes()
    with pytest.raises(ValueError,match='变化'):e.yaochi_action(gid,'garden_lease',shown['token']+'|')
    assert e.store._path(gid).read_bytes()==before
    from cultivation_life.system.economy.enterprise_actions import command
    g=e._load(gid);row=garden.estate(g)
    with pytest.raises(ValueError,match='产权'):command(g,e.maps,dict(action='estate_release',estate_id=row['id'],revision=row['revision']))

def test_cooperator_real_occupancy_and_release(pool):
    e,gid=pool;leased(e,gid);n=opponent(e,gid);cmd(e,gid,'garden_steward',n)
    assert research_assignment(e._load(gid),n)
    with pytest.raises(ValueError,match='参会人'):cmd(e,gid,'fair_join','duel~'+n)
    cmd(e,gid,'garden_release');assert not research_assignment(e._load(gid),n)

def test_supply_actual_years_original_goods_and_one_award(pool):
    e,gid=pool;cmd(e,gid,'fair_join','supply');g=e._load(gid);r=active(g);age=g.player.age
    with pytest.raises(ValueError,match='五年'):cmd(e,gid,'fair_deliver')
    for k,n in r['materials'].items():add_item(g.player,k,n)
    e.store.save(g);work(e,gid);g=e._load(gid)
    assert g.player.age==age+5 and active(g)['progress']==5
    cash=balance(g,'player');reward=active(g)['prize']+active(g)['goods_value']
    cmd(e,gid,'fair_deliver');g=e._load(gid)
    assert balance(g,'player')==cash+reward and not active(g) and fair.entries(g)[-1]['delivered']
    with pytest.raises(ValueError,match='一次'):cmd(e,gid,'fair_join','supply')
    cmd(e,gid,'garden_lease');assert garden.lease(e._load(gid))['deposit']==100

def test_duel_uses_actual_actor_and_combat_not_repeated(pool):
    e,gid=pool;n=opponent(e,gid);cmd(e,gid,'fair_join','duel~'+n);work(e,gid)
    cmd(e,gid,'fair_fight');g=e._load(gid)
    assert g.last_combat_report and g.world_npcs[n].alive and not research_assignment(g,n)
    assert len(g.last_combat_report['player_roster'])==1 and fair.entries(g)[-1]['battle']['rounds']>0
    with pytest.raises(ValueError,match='没有'):cmd(e,gid,'fair_fight')

def test_guard_needs_original_array_and_cancel_does_not_reset(pool):
    e,gid=pool;n=opponent(e,gid);cmd(e,gid,'fair_join','guard~'+n);work(e,gid)
    with pytest.raises(ValueError,match='阵法'):cmd(e,gid,'fair_fight','hold')
    cmd(e,gid,'fair_cancel')
    with pytest.raises(ValueError,match='一次'):cmd(e,gid,'fair_join','guard~'+n)

@pytest.mark.parametrize('plan',['hold','break'])
def test_guard_real_combat_report_and_array_threshold(pool,plan):
    e,gid=pool;n=opponent(e,gid);array(e,gid);cmd(e,gid,'fair_join','guard~'+n);work(e,gid)
    cmd(e,gid,'fair_fight',plan);g=e._load(gid);r=fair.entries(g)[-1];battle=g.last_combat_report
    assert r['battle']['integrity']==battle['formation_integrity_end'] and battle['formation_profile']['name']=='仙会护阵'
    expected=r['battle']['outcome']=='victory' or plan=='hold' and battle['outcome']=='stalemate' and len(battle['rounds'])>=4 and battle['rounds'][-1]['player_hp_ratio']>.3
    assert (r['status']=='won')==bool(expected and r['battle']['integrity']>=(.5 if plan=='hold' else .7))
    assert r['battle']['plan']==plan and not active(g) and g.world_npcs[n].alive

def test_fair_interrupted_years_and_disabled_recovery(pool):
    from cultivation_life.content_registry import WORLD_SYSTEMS
    import random
    e,gid=pool;cmd(e,gid,'fair_join','supply');age=e._load(gid).player.age;annual=e._advance_world_year
    def interrupt(g,rng,news,**kw):
        result=annual(g,rng,news,**kw)
        if g.player.age==age+2:
            g.pending_event=e._instantiate_event(e.events_by_id['EVT_SECT_FIRST_WARNING_001'],g,random.Random(1));return False
        return result
    with patch.object(e,'_advance_world_year',side_effect=interrupt):work(e,gid)
    assert active(e._load(gid))['progress']==2
    g=e._load(gid);g.pending_event=None;e.store.save(g)
    with patch.dict(WORLD_SYSTEMS['yaochi_westward'],enabled=False):
        with pytest.raises(ValueError,match='启用'):cmd(e,gid,'fair_work')
        cmd(e,gid,'fair_cancel')
    assert not active(e._load(gid))

def test_fair_occupation_and_real_crossworld_freeze(pool):
    e,gid=pool;cmd(e,gid,'fair_join','supply')
    before=copy.deepcopy(active(e._load(gid)))
    with pytest.raises(ValueError,match='当前事务'):e.yaochi_action(gid,'accept','gather_herbs')
    g=e._load(gid);assert active(g)==before
    plan=e._plan_world_transition(g,'spirit','sealed_descent',reason='仙会原案归属验收');e._apply_world_transition(g,plan)
    assert active(g)==before and fair.public(g) is None and garden.public(g) is None

def test_cancelled_order_real_penalty_and_no_earned_merit(pool):
    e,gid=pool;leased(e,gid);cmd(e,gid,'garden_order');g=e._load(gid);wallet=garden.lease(g)['order']['wallet']
    cmd(e,gid,'garden_cancel_order');cmd(e,gid,'garden_close');g=e._load(gid)
    assert balance(g,wallet)==0 and g.yaochi_state['merit']==99960 and g.yaochi_state['earned']==100000

def test_no_new_battle_cannot_reuse_previous_report(pool):
    e,gid=pool;n=opponent(e,gid);cmd(e,gid,'fair_join','duel~'+n);work(e,gid);cmd(e,gid,'fair_fight')
    array(e,gid);cmd(e,gid,'fair_join','guard~'+n);work(e,gid)
    assert e._load(gid).last_combat_report
    with patch.object(e,'_combat',return_value=('technique_blocked','原功法资格未满足')):cmd(e,gid,'fair_fight','hold')
    row=fair.entries(e._load(gid))[-1]
    assert row['status']=='closed' and row['battle']['rounds']==0 and row['battle']['integrity'] is None

def test_market_mode_and_dead_cooperator_do_not_create_wages(pool):
    from cultivation_life.npc_custody import kill_person
    e,gid=pool;leased(e,gid);cmd(e,gid,'garden_mode','market');assert garden.estate(e._load(gid))['auto_sell']
    cmd(e,gid,'garden_mode','retain');cmd(e,gid,'garden_start');n=opponent(e,gid);cmd(e,gid,'garden_steward',n)
    g=e._load(gid);kill_person(g,n,'协作者失效验收');e.store.save(g);work(e,gid,'garden');g=e._load(gid)
    assert garden.lease(g)['wages']==0 and not garden.estate(g)['enabled'] and garden.estate(g)['stock']
    cmd(e,gid,'garden_release');assert not research_assignment(e._load(gid),n)

def test_garden_freezes_with_original_region_and_keeps_single_deed(pool):
    from cultivation_life.engine.world import regions
    e,gid=pool;leased(e,gid);cmd(e,gid,'garden_start');g=e._load(gid)
    plan=e._plan_world_transition(g,'spirit','sealed_descent',reason='仙圃原地区冻结验收');e._apply_world_transition(g,plan)
    original=copy.deepcopy(garden.estate(g));g.player.age+=1
    regions.synchronize(e._dependencies.regions,g,{'spirit'},end=g.player.age)
    assert garden.estate(g)==original and garden.public(g) is None
    plan=e._plan_world_transition(g,'celestial','sealed_return',reason='原仙圃返界验收');e._apply_world_transition(g,plan)
    assert garden.estate(g)['id']==original['id'] and garden.estate(g)['operating_lease']==original['operating_lease']

def test_insufficient_fair_budget_is_atomic(pool):
    e,gid=pool;g=e._load(gid);transfer_value(g,YAOCHI,'background:celestial',balance(g,YAOCHI),'验收原采购池不足');e.store.save(g)
    before=e.store._path(gid).read_bytes()
    with pytest.raises(ValueError,match='府库不足'):cmd(e,gid,'fair_join','supply')
    assert e.store._path(gid).read_bytes()==before

def test_damaged_leased_farm_original_repair_restores_paid_batch(pool):
    from cultivation_life.system.building_assets import local_rows
    e,gid=pool;leased(e,gid);cmd(e,gid,'garden_start');g=e._load(gid)
    building=next(r for r in local_rows(g) if r.get('source_id')==garden.identity())
    before=copy.deepcopy(garden.estate(g)['job'])
    damage(e,gid,building['id'])
    with pytest.raises(ValueError,match='修复'):cmd(e,gid,'garden_work')
    cmd(e,gid,'garden_rebuild');g=e._load(gid)
    assert garden.estate(g)['building_status']=='intact' and garden.estate(g)['job']==before
    assert garden.estate(g)['owner_kind']=='yaochi'
    work(e,gid,'garden');assert garden.estate(e._load(gid))['stock']
