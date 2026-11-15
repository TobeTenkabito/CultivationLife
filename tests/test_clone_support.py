"""Clone assets reuse owned training and paid resumable trial combat."""
import copy
import json
import random
from types import SimpleNamespace

import pytest

from test_npc_development import game
from test_technique_secrets import base
from cultivation_life.content_registry import TECHNIQUE_CATALOG, WORLD_SYSTEMS
from cultivation_life.rules import add_item,combat_power
from cultivation_life.system import clone_support
from cultivation_life.system.npc_development import service,presentation
from cultivation_life.system.combat.trials import load_battle,dump_battle,run_batch
from cultivation_life.engine import engine_combat_runtime


def clone(rank=2,power=500):
    return dict(id='clone_test',name='分身验收',type='clone',path='dao',race='human',gender='female',age=30,
                spirit_root='supreme_metal',realm_index=rank,layer=1,combat_power=power,
                body_training=10,divine_sense_rank=17,alive=True,durability=80.,operating_energy=100.,
                energy_source_id='npc_training_puppet_energy_3' if rank==9 else f'npc_training_puppet_energy_rank_{rank}',
                main_technique_id=None,breakthrough_bonus=0.)


@pytest.mark.parametrize('axis',['cultivation','body','sense'])
def test_training_writes_same_clone_and_never_refills_energy_or_duplicates_npc(game,axis):
    asset=clone();game.player.puppets=[asset]
    material=f'npc_training_puppet_{axis}_1';add_item(game.player,material,10)
    before=copy.deepcopy(game.to_dict());q=service.quote(game,'puppet',asset['id'],axis,'material',1)
    assert q['can_train'] and game.to_dict()==before
    service.apply(game,'puppet',asset['id'],axis,'material',1)
    assert game.player.puppets[0] is asset
    assert asset['combat_power']>500 and asset['durability']==80 and asset['operating_energy']==100
    assert set(game.world_npcs)=={'student'} and not game.player.party
    assert sum(i.quantity for i in game.player.inventory if i.id==material)==10-q['material_count']
    assert game.rng_state==before['rng_state'] and game.player.age==before['player']['age']
    view=next(r for r in presentation.public(game)['targets'] if r['id']==asset['id'])
    assert '分身' in view['relations']
    assert view['portrait']['visual_variant']=='clone' and not view['portrait'].get('restraint')


def test_teaching_reuses_paid_growth_and_does_not_change_other_categories(game):
    asset=clone();game.player.puppets=[asset]
    book=copy.deepcopy(TECHNIQUE_CATALOG['TECH_BASIC_QI']);game.player.known_techniques=[book]
    service.teach(game,'puppet',asset['id'],book.id,slot='main')
    assert asset['main_technique_id']==book.id
    power=asset['combat_power']
    with pytest.raises(ValueError):service.teach(game,'puppet',asset['id'],book.id,slot='main')
    assert asset['combat_power']==power
    asset['type']='mechanical';asset['main_technique_id']=None
    with pytest.raises(ValueError):service.teach(game,'puppet',asset['id'],book.id,slot='main')


def test_normal_roster_adds_clone_without_using_or_replacing_party(game):
    game.player.puppets=[clone()];before=copy.deepcopy(game.player.party)
    deps=SimpleNamespace(_npc_power=lambda npc:100,_public_party=lambda g:[dict(id='friend',name='同行者',combat_power=100,realm_index=2,path='dao')])
    roster=engine_combat_runtime._player_combat_units(deps,game)
    assert {'player','clone_test','friend'} <= {u.id for u in roster}
    assert game.player.party==before
    assert [u.id for u in engine_combat_runtime._player_combat_units(deps,game,{'single_combat':True})]==['player']


@pytest.mark.parametrize('other_support',[False,True])
def test_clone_growth_and_lifecycle_never_enter_intrinsic_or_party_power(base,other_support):
    engine,original=base;g=copy.deepcopy(original);p=g.player;g.pending_event=None
    p.realm_index=4;p.layer=8;p.opportunity=100000
    p.puppets=([dict(clone(),id=kind,type=kind,corpse_integrity=80,control=100)
                for kind in ('mechanical','corpse','living')] if other_support else [])
    def powers():
        view=engine.present(g)
        return (combat_power(p),engine._player_intrinsic_combat_power(p),engine._player_battle_power(g),
                view['player']['combat_power'],view['player']['battle_power'])
    baseline=powers();asset=clone(power=10**12);p.puppets.append(asset)
    def check():
        assert powers()==baseline
        row=next(r for r in engine._public_demonic_system(p,g)['puppets'] if r['id']==asset['id'])
        assert row['combat_power']==asset['combat_power']
        assert row['battle_contribution']==row['battle_contribution_ratio']==0
    check()
    add_item(p,'npc_training_puppet_body_1',10)
    service.apply(g,'puppet',asset['id'],'body','material',1)
    assert asset['combat_power']>10**12
    check()
    for change in (dict(operating_energy=0),dict(durability=0,alive=False)):
        asset.update(change);check()
    p.puppets.remove(asset)
    assert powers()==baseline


@pytest.mark.parametrize('change',[
    lambda g:g.player.puppets[0].update(alive=False),
    lambda g:g.player.puppets[0].update(durability=0),
    lambda g:g.player.puppets[0].update(realm_index=9),
    lambda g:setattr(g.player,'sealed_cultivation',{'active':True}),
    lambda g:setattr(g.player,'world','rift'),
    lambda g:g.player.puppets.append(copy.deepcopy(g.player.puppets[0])),
    lambda g:g.player.puppets[0].update(id='student'),
])
def test_unavailable_clone_or_colliding_identity_cannot_enter(game,change):
    game.player.puppets=[clone()];change(game)
    assert not clone_support.units(game)


def prepared_trial(family,realm,monkeypatch,*,enabled=True,charge=100,supply=False):
    from scripts import calibrate_upper_breakthroughs as c
    configure=c.configure_field;captured={}
    def setup(game,*args):
        value=configure(game,*args);p=game.player
        asset=clone(realm,combat_power(p)*.45);asset['path']=p.path
        asset.update(layer=p.layer,body_training=100,immortal_body_level=20,
                     operating_energy=charge,energy_source_id=f'puppet_{p.world}_{realm}_energy_crystal')
        p.combat_plan.update(puppet_supply=supply)
        if enabled:p.puppets=[asset,dict(asset,id='ordinary_puppet',type='mechanical')]
        captured['game']=game
        return value
    with monkeypatch.context() as patch:
        patch.setattr(c,'configure_field',setup)
        trial,_=c.prepare(family,realm,'ready',c.variants(family)[0],15413)
    return captured['game'],trial


@pytest.mark.parametrize('family',['immortal','demonic','monster','ghost'])
@pytest.mark.parametrize('realm',[9,10,11])
def test_all_upper_trials_include_only_clones_and_do_not_strengthen_mirrors(family,realm,monkeypatch):
    _,plain=prepared_trial(family,realm,monkeypatch,enabled=False)
    game,trial=prepared_trial(family,realm,monkeypatch)
    base=load_battle(plain['snapshot']);battle=load_battle(trial['snapshot'])
    assert {k for k,s in battle.units.items() if s.unit.side=='player'}=={'player','clone_test'}
    assert trial['battle_state']['stats']['enemy']==plain['battle_state']['stats']['enemy']
    for key,s in base.units.items():
        if s.unit.side=='enemy':assert s.unit==battle.units[key].unit
    assert battle.units['clone_test'].unit.capabilities.capacity==0
    state=trial['battle_state'];rng=random.Random(18)
    run_batch(battle,state,rng,batch_size=1)
    clone_support.commit(game,battle,state)
    asset=game.player.puppets[0]
    assert asset['operating_energy']==(95 if 'clone_test' in battle._ordinary_attacks else 100)
    assert 0<=asset['durability']<=80
    saved=json.loads(json.dumps(dump_battle(battle)))
    restored=load_battle(saved);state2=copy.deepcopy(state);rng2=random.Random();rng2.setstate(rng.getstate())
    assert run_batch(battle,state,rng,batch_size=1)==run_batch(restored,state2,rng2,batch_size=1)
    assert json.loads(json.dumps(dump_battle(battle)))==json.loads(json.dumps(dump_battle(restored))) and state==state2
    clone_support.commit(game,battle,state);old=copy.deepcopy(asset)
    clone_support.commit(game,battle,state)
    assert asset==old


def test_empty_clone_does_not_keep_free_stat_contribution(monkeypatch):
    from cultivation_life.system.combat.trial_clones import contribute
    game,trial=prepared_trial('demonic',9,monkeypatch,charge=5)
    battle=load_battle(trial['snapshot']);state=trial['battle_state'];rng=random.Random(28)
    run_batch(battle,state,rng,batch_size=1)
    assert battle.units['clone_test'].operating_energy==0
    battle.begin_round(2,player_condition=1,enemy_condition=1,player_mp=1,enemy_mp=1,rng=rng)
    before=copy.deepcopy(state['stats']);after=copy.deepcopy(before);contribute(battle,state,after)
    assert after==before
    clone_support.commit(game,battle,state)
    assert game.player.puppets[0]['operating_energy']==0


@pytest.mark.parametrize('kind',['voisinage_backlash','asura_fusion'])
def test_special_upper_trials_keep_clone_identity_and_original_mode(monkeypatch,kind):
    from cultivation_life.engine.progression import immortal_trials,asura_trials
    from scripts.calibrate_upper_breakthroughs import ADAPTER
    g,_=prepared_trial('immortal' if kind=='voisinage_backlash' else 'demonic',9,monkeypatch)
    if kind=='voisinage_backlash':
        immortal_trials.start(ADAPTER,g,kind);b=immortal_trials.initialize(g,g.active_trial)
        monkeypatch.setattr(b,'ordinary_damage',lambda *a,**kw:pytest.fail('backlash must remain field-only'))
    else:
        body=dict(id='body-one',name='待炼肉身',power=combat_power(g.player),immortal_body_level=0)
        asura_trials.start(ADAPTER,g,kind,bodies=[body],route='heaven')
        b=load_battle(g.active_trial['snapshot'])
    assert {key for key,s in b.units.items() if s.unit.side=='player'}=={'player','clone_test'}
    assert b.units['clone_test'].unit.capabilities.operating_energy==100
    run_batch(b,g.active_trial['battle_state'],random.Random(18),batch_size=1)
    assert g.active_trial['battle_state']['mode']==kind
    if kind=='voisinage_backlash':assert b.units['clone_test'].operating_energy==100


def test_real_ordinary_battle_commits_clone_cost_and_damage(base):
    from cultivation_life.rules import max_hp,max_mp
    engine,original=base;g=copy.deepcopy(original);g.pending_event=None;p=g.player
    p.realm_index=2;p.layer=1;p.hp=max_hp(p);p.mp=max_mp(p)
    p.combat_plan=dict(manual=False,puppet_supply=False)
    p.puppets=[clone(2,combat_power(p))]
    engine._combat(g,dict(target_name='验收对手',target_power=combat_power(p)*3,
        target_realm_index=2,target_layer=1,combat_type='cultivator',max_rounds=1,mp_loss_scale=0),False,random.Random(18))
    asset=p.puppets[0]
    assert asset['operating_energy']==95 and 0<asset['durability']<80
    assert any(r['id']=='clone_test' and r['kind_name']=='分身' for r in g.last_combat_report['player_roster'])
    team=g.last_combat_report['visual']['teams']['hero']
    assert next(r for r in team if r['id']=='clone_test')['visual_variant']=='clone'
    assert not next(r for r in team if r['id']=='player').get('visual_variant')
    assert not p.party
    engine.store.save(g)
    assert engine.store.load(g.id).player.puppets==p.puppets


def test_destroyed_clone_stays_destroyed_and_blocks_training(game):
    from cultivation_life.system.combat_adapter import bind_capabilities
    game.player.puppets=[clone()]
    from cultivation_life.system.combat_system import BattleUnit
    units=[BattleUnit('player','本体','player',100,4,'dao'),*clone_support.units(game)]
    target=dict(target_name='敌人',target_power=100,target_realm_index=4,members=[dict(name='敌人',power=100,realm_index=4)])
    battle=bind_capabilities(game,units,target,WORLD_SYSTEMS['transcendent_combat']).battle
    state={};clone_support.freeze_stats(state,units[1:]);battle.units['clone_test'].body=0
    clone_support.commit(game,battle,state)
    assert not game.player.puppets[0]['alive'] and not clone_support.units(game)
    before=copy.deepcopy(game.to_dict())
    with pytest.raises(ValueError):service.apply(game,'puppet','clone_test','body')
    assert game.to_dict()==before


@pytest.mark.parametrize('family',['immortal','demonic','monster','ghost'])
def test_real_event_load_submit_resume_and_blocked_asset_mutations(base,monkeypatch,family):
    from cultivation_life.engine.progression import immortal_trials,asura_trials,upper_trials
    engine,original=base
    g,trial=prepared_trial(family,9,monkeypatch)
    g.id=original.id;g.player.location_id=engine.maps.normalize_location(g.player.world,None)
    g.player.opportunity=10**12
    g.pending_event=engine._instantiate_event(engine.events_by_id[g.pending_event['id']],g,random.Random(1))
    engine.store.save(g)
    module={'immortal':immortal_trials,'demonic':asura_trials,'monster':upper_trials,'ghost':upper_trials}[family]
    monkeypatch.setattr(module,'run_batch',lambda b,s,r:run_batch(b,s,r,batch_size=1))
    assert engine.get_game(g.id)['pending_event']
    # The lightweight calibration fixture omits world population. Adopt it via
    # the real loader once before checking rejected commands for side effects.
    engine.store.save(engine._load(g.id))
    for round_number in (1,2):
        before=engine.store.load(g.id)
        with pytest.raises(ValueError):engine.puppet_action(g.id,'clone_test','dismiss')
        with pytest.raises(ValueError):service.charge(before,'puppet','clone_test')
        stored=engine.store.load(g.id).to_dict();expected=before.to_dict()
        # The existing loader recalculates breakthrough reminder flags. The
        # rejected asset operation must leave every owned resource and trial intact.
        for key in ('puppets','mp','hp','opportunity','inventory','age','party','immortal_aperture'):
            assert stored['player'][key]==expected['player'][key]
        for key in ('rng_state','active_trial','pending_event'):
            assert stored[key]==expected[key]
        shown=engine.choose(g.id,'fight',event_id=before.pending_event['id'])
        saved=engine.store.load(g.id);asset=saved.player.puppets[0]
        assert shown['pending_event'] and saved.active_trial['battle_state']['round']==round_number
        assert asset['operating_energy']<=before.player.puppets[0]['operating_energy']
        assert asset['durability']<=before.player.puppets[0]['durability']
        frozen=load_battle(saved.active_trial['snapshot']).units['clone_test']
        assert asset['operating_energy']==frozen.operating_energy
        assert any(row['id']=='clone_test' and row['kind']=='clone' for row in saved.last_combat_report['player_roster'])
        assert any(row['id']=='clone_test' and row.get('visual_variant')=='clone' for row in saved.last_combat_report['visual']['teams']['hero'])
        assert not saved.player.party
