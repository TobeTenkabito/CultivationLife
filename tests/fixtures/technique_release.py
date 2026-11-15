"""Disposable release scenarios; all rewards and combat use the real engine."""
import copy

from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.rules import learn_technique, assign_technique, max_hp, max_mp, QI_SOURCE_NAMES, add_item
from cultivation_life.system.duel_techniques import player_reason
from cultivation_life.system.formation_system import formation_material_definitions, make_formation_material_instance


def prepare_technique_release(engine, identity, mode='secret'):
    g=engine.store.load(identity);p=g.player
    g.pending_event=g.active_trial=None
    p.realm_index=4 if mode=='secret' else 5;p.layer=1;p.body_training=80
    p.additional_roots=['metal','wood','water','fire','earth','wind','thunder','yin','yang']
    p.qi_experience={k:1e12 for k in QI_SOURCE_NAMES}
    p.lifespan=p.age+10000;p.opportunity=100000;p.divine_sense_rank=40
    p.secret_art_state={};p.known_techniques=[];p.technique=p.support_technique=None
    p.combat_techniques=[];p.duel_technique_ids=[];p.formation_materials=[]
    if mode=='secret':
        for identity in ('TECH_HIGH_SKY_COLD_RAY','TECH_TIANYUAN_ART'):
            learn_technique(p,copy.deepcopy(TECHNIQUE_CATALOG[identity]))
        assign_technique(p,copy.deepcopy(TECHNIQUE_CATALOG['TECH_HIGH_SKY_COLD_RAY']),'support')
        for nature in ('metal','wood','water','fire','earth'):
            d=next(d for d in formation_material_definitions().values() if d['nature']==nature and d['tier']>=5)
            p.formation_materials.append(make_formation_material_instance(d,source='发行隔离场景',origin_world=d['world']))
        add_item(p,'spirit_stone',1000000)
    else:
        books=[copy.deepcopy(t) for t in TECHNIQUE_CATALOG.values()
            if t.combat_effect and t.combat_effect.get('version')==3
            and t.combat_effect['resource']=='mana' and not player_reason(p,t)
            and t.combat_effect['trigger']=='paid_preparation'][:7]
        assert len(books)==7
        for book in books:
            learn_technique(p,book);assign_technique(p,book,'combat')
        p.duel_technique_ids=[b.id for b in books[:6]]
    p.hp=max_hp(p);p.mp=max_mp(p);engine.store.save(g)
    return g


def prepare_expansion_release(engine, identity, mode):
    """Isolated new-release cases; real secret commands grant all rewards."""
    import random
    g=engine.store.load(identity);p=g.player;g.pending_event=g.active_trial=None
    if mode in ('wind','frost'):
        p.realm_index=4 if mode=='wind' else 8;p.layer=1;p.path='demonic' if mode=='wind' else 'dao'
        p.world='human' if mode=='wind' else 'spirit';p.location_id=engine.maps.normalize_location(p.world,None)
        p.additional_roots=['wind','water'];p.qi_experience={k:0. for k in QI_SOURCE_NAMES}
        p.qi_experience['demon' if mode=='wind' else 'spirit']=1e8
        p.opportunity=1e12;p.lifespan=p.age+10000;p.secret_art_state={}
        p.technique=p.support_technique=None;p.known_techniques=[];p.combat_techniques=[];p.duel_technique_ids=[];p.puppets=[];p.party=[]
        key='TECH_LINLAN_DEMON' if mode=='wind' else 'TECH_HUNDRED_THOUSAND_FROST'
        book=copy.deepcopy(TECHNIQUE_CATALOG[key]);learn_technique(p,book);assign_technique(p,book,'combat');p.duel_technique_ids=[key]
    else:
        power=engine._player_intrinsic_combat_power(p)
        p.puppets=[dict(id=f'crowd-clone-{i}',name=f'分身{i+1}',type='clone',realm_index=p.realm_index,layer=1,
            gender=p.gender,path=p.path,race='human',age=30,combat_power=power*.05,alive=True,durability=100.,
            operating_energy=100.,energy_source_id=f'npc_training_puppet_energy_rank_{p.realm_index}') for i in range(11)]
        foes=[dict(npc_id=f'crowd-foe-{i}',name=f'演武{i+1}',power=power*.13,realm_index=p.realm_index,
            gender='male' if i%2 else 'female',path='dao',kind='cultivator') for i in range(12)]
        from cultivation_life.system.clone_support import units
        assert len(units(g))==11, dict(world=p.world,realm=p.realm_index,alive=p.alive,
            sealed=p.sealed_cultivation,suppressed=p.cultivation_suppression,spirit=p.spirit_state)
        p.hp=max_hp(p);p.mp=max_mp(p)
        engine._combat(g,dict(target_name='多人演武',target_power=power*1.56,target_realm_index=p.realm_index,
            combat_type='cultivator',members=foes,max_rounds=3,natural_terrain='开阔'),False,random.Random(151))
    p.hp=max_hp(p);p.mp=max_mp(p);engine.store.save(g)
    return g
