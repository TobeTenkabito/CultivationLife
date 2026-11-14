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
