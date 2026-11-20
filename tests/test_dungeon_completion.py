"""Completion audit: real saved command submissions, not just private solvers."""
import copy
import json
import pytest
from test_seeded_dungeons import local,discover,act
from cultivation_life.models import Item
from cultivation_life.rules import add_item,max_hp,max_mp,combat_power,passive_inventory
from cultivation_life.dungeon_schema import decode
from cultivation_life.system.dungeons.people import materialize


def loaded(engine,game):
    saved=engine.store.load(game.id)
    return saved,next(iter(saved.dungeon_state['instances'].values()))


def test_real_survey_detour_preserves_skipped_rewards_and_read_only_history(local):
    engine,game=local;discover(engine,game);act(engine,game,'enter')
    saved,site=loaded(engine,game);route=site['expedition']['routes'][site['nodes'][0]['id']]
    with pytest.raises(ValueError,match='侧路'):act(engine,game,'choose',choice='detour')
    act(engine,game,'choose',choice='survey')
    shown=engine.get_game(game.id)['dungeons']['session']
    assert any(c['id']=='detour' for c in shown['choices'])
    act(engine,game,'choose',choice='detour')
    saved,site=loaded(engine,game)
    assert site['step']==route['destination'] and not site['claims']
    if site['pending']:act(engine,game,'choose',choice='decline')
    act(engine,game,'exit')
    snapshot=engine.store.load(game.id).dungeon_state
    for _ in range(2):
        view=engine.get_game(game.id)['dungeons']
        assert view['archives'] and any('绕过' in r['text'] for r in view['archives'][0]['logs'])
    assert engine.store.load(game.id).dungeon_state==snapshot


def test_trade_consumes_real_item_once_and_never_reveals_private_goal(local):
    engine,game=local;discover(engine,game)
    saved,site=loaded(engine,game);role=next(iter(site['roles'].values()))
    role.update(state='invited',known=True,purpose='heal');engine.store.save(saved)
    act(engine,game,'enter');act(engine,game,'choose',choice='accept')
    actor=role['id'];act(engine,game,'bargain',actor_id=actor,choice='promise')
    before=engine.store.load(game.id).to_dict()
    with pytest.raises(ValueError,match='恢复药物'):act(engine,game,'bargain',actor_id=actor,choice='deliver')
    assert engine.store.load(game.id).to_dict()==before
    saved,site=loaded(engine,game)
    # Test fixture supplies a real bag item; production supplies these through frozen loot.
    add_item(saved.player,Item(id='TEST_RECOVERY',name='验收恢复药',tags=['dungeon_restorative']))
    engine.store.save(saved)
    result=act(engine,game,'bargain',actor_id=actor,choice='deliver')
    saved,site=loaded(engine,game)
    assert not any(i.id=='TEST_RECOVERY' for i in saved.player.inventory)
    assert site['expedition']['contracts'][actor]['state']=='fulfilled'
    assert not any(n.id==actor and getattr(n,'inventory',None) for n in saved.world_npcs.values())
    for forbidden in ('"purpose"','"goals"','"seen_power"','"desires"'):
        assert forbidden not in json.dumps(result['dungeons'])
    with pytest.raises(ValueError,match='没有待交付'):act(engine,game,'bargain',actor_id=actor,choice='deliver')


def test_weaker_side_bonus_does_not_take_next_node_or_auto_join(local):
    engine,game=local;discover(engine,game);act(engine,game,'enter')
    saved,site=loaded(engine,game);a,b=list(site['roles'].values())[:2]
    for role,rank in ((a,1),(b,2)):
        role.update(realm=rank,true_realm=rank,layer=1,known=True,state='contact',purpose='seek',preparation=0,trust=100,caution=100)
        role['ledger']['supporters']=[]
    site['pending']=dict(kind='conflict',actor=a['id'],other=b['id'])
    next_reward=site['nodes'][1]['reward']['id'];engine.store.save(saved)
    shown=act(engine,game,'choose',choice='support_actor')
    saved,site=loaded(engine,game)
    assert saved.last_combat_report
    assert site['pending']['kind']=='settlement'
    assert a['id'] not in site['party']
    assert len(site['expedition']['bonus_claims'])==1
    assert next_reward not in site['claims']
    assert {'part','ask_join'}=={c['id'] for c in shown['dungeons']['session']['choices']}
    act(engine,game,'choose',choice='part')
    saved,site=loaded(engine,game)
    assert a['id'] in site['expedition']['settlements'] and a['id'] not in site['party']


def test_faction_reinforcements_are_lazy_until_actual_battle(local):
    engine,game=local;discover(engine,game);act(engine,game,'enter')
    saved,site=loaded(engine,game);a,b=list(site['roles'].values())[:2]
    for role in (a,b):role.update(realm=1,true_realm=1,layer=1,purpose='seek',state='unseen')
    site['space']['positions'].update({r['id']:site['step'] for r in (a,b)})
    a['ledger']['supporters']=[b['id']];a.update(known=True,state='hostile')
    site['pending']=dict(kind='guardian',actor=a['id']);engine.store.save(saved)
    assert not a['materialized'] and not b['materialized']
    act(engine,game,'choose',choice='fight')
    saved,site=loaded(engine,game)
    assert saved.last_combat_report
    assert all(site['roles'][r['id']]['materialized'] for r in (a,b))
    assert all(r['id'] in saved.world_npcs for r in (a,b))


def test_evidence_chain_updates_without_instantiating_remote_people(local):
    engine,game=local;discover(engine,game);act(engine,game,'enter')
    saved,site=loaded(engine,game)
    # Frozen V2 reports exist only in epic/legend; install one controlled audit fact.
    site['quality']='epic';ids=list(site['roles'])
    site['space']['positions'].update({key:3 for key in ids[:2]})
    site['expedition']['facts']=[dict(id='audit-news',actors=ids[:2],direction='东',occurred=1,reported=2,verified=4,result='伤亡后撤',mistaken=True)]
    for role in site['roles'].values():role['offer_step']=99
    engine.store.save(saved)
    for _ in range((len(site['nodes'])+1)//2):act(engine,game,'choose',choice='bypass')
    saved,site=loaded(engine,game)
    chain=[r for r in site['logs'] if r.get('fact_id')=='audit-news']
    assert [r['kind'] for r in chain]==['听说','据说','实证','据说']
    assert chain[-1]['supersedes']==chain[-2]['id']
    assert '已撤回' in chain[-1]['text']
    assert all(not r['materialized'] for r in site['roles'].values())


def test_relic_resonance_bounds_across_maps_and_quantities(local):
    _,game=local;p=game.player
    first=Item(id='one',name='甲',combat_bonus=200,hp_bonus=30,mp_bonus=10,tags=['equipment','dungeon_relic'])
    second=Item(id='two',name='乙',combat_bonus=100,hp_bonus=1000,mp_bonus=1000,tags=['equipment','dungeon_relic'])
    add_item(p,first);baseline=(combat_power(p),max_hp(p),max_mp(p))
    add_item(p,first,100);add_item(p,second,100)
    assert (combat_power(p),max_hp(p),max_mp(p))==baseline
    assert [i.id for i in passive_inventory(p) if 'dungeon_relic' in i.tags]==['one']


def test_extension_rejects_reward_and_route_forgery_without_touching_original(local):
    engine,game=local;discover(engine,game);saved,site=loaded(engine,game)
    bad=copy.deepcopy(saved.dungeon_state);row=bad['instances'][site['id']]
    route=next(iter(row['expedition']['routes'].values()));route['destination']=999
    with pytest.raises(ValueError):decode(bad)
    assert decode(saved.dungeon_state)==saved.dungeon_state


def test_public_invitation_reputation_does_not_read_private_cultivation(local):
    from cultivation_life.reputation import assess,record
    _,game=local;p=game.player
    visible=assess(p,visible=True)['value']
    p.divine_sense_rank+=80
    record(p,'secret-core',45,'探境所得')
    assert assess(p,visible=True)['value']==visible
    assert assess(p)['value']>visible
    record(p,'public-help',5,'争夺中援助同道')
    assert assess(p,visible=True)['value']==visible+5


def test_surviving_ally_can_turn_hostile_at_settlement_without_early_disclosure(local):
    engine,game=local;discover(engine,game);act(engine,game,'enter')
    saved,site=loaded(engine,game);role=next(iter(site['roles'].values()))
    role.update(realm=saved.player.realm_index,true_realm=saved.player.realm_index,layer=saved.player.layer,
        state='joined',known=True,purpose='assassinate',resolve=95,preparation=100,trust=100,caution=0)
    materialize(saved,site,role);site['party']=[role['id']]
    site['pending']=dict(kind='settlement',actor=role['id']);engine.store.save(saved)
    shown=engine.get_game(game.id)['dungeons']['session']
    assert not shown['people'][0]['exposed']
    shown=act(engine,game,'choose',choice='part')['dungeons']['session']
    saved,site=loaded(engine,game)
    assert site['pending']['kind']=='ambush'
    assert role['id'] not in site['party']
    assert shown['people'][0]['exposed'] and not shown['can_exit']
    with pytest.raises(ValueError,match='争斗'):act(engine,game,'exit')


def test_claimed_restorative_uses_original_item_command_without_permanent_growth(local):
    engine,game=local;discover(engine,game);act(engine,game,'enter')
    saved,site=loaded(engine,game)
    index=next(i for i,n in enumerate(site['nodes']) if n['reward']['kind']=='pill')
    node=site['nodes'][index];node['kind']='cache';site['step']=index;site['pending']=None
    for role in site['roles'].values():role.update(state='left',offer_step=0)
    saved.player.hp=max_hp(saved.player)/2;saved.player.mp=max_mp(saved.player)/2
    engine.store.save(saved);act(engine,game,'choose',choice='seize')
    before=engine.store.load(game.id)
    engine.use_item(game.id,node['reward']['id'])
    after=engine.store.load(game.id)
    assert after.player.hp>before.player.hp and after.player.mp>before.player.mp
    assert after.player.permanent_intrinsic_hp_bonus==before.player.permanent_intrinsic_hp_bonus
    assert after.player.opportunity>before.player.opportunity
    assert not any(i.id==node['reward']['id'] for i in after.player.inventory)
    with pytest.raises(ValueError,match='物品不存在'):engine.use_item(game.id,node['reward']['id'])
