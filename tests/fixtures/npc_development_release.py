"""Disposable real-load fixtures shared by EXE and signed native acceptance."""
def prepare_npc_development(engine,identity):
    import random,copy
    from cultivation_life.models import SectNpc
    from cultivation_life.content_registry import TECHNIQUE_CATALOG
    from cultivation_life.rules import add_item,max_hp,max_mp,combat_power
    from cultivation_life.puppet_content import FORMS
    from cultivation_life.system.npc_techniques import learn
    g=engine.store.load(identity);p=g.player;g.pending_event=None;g.active_trial=None
    p.next_tribulation_age=None;p.hp=max_hp(p);p.mp=max_mp(p);p.opportunity=10**12
    p.combat_plan={'manual':False,'puppet_supply':False}
    bird=dict(id='release-bird',name='云翼守卫',type='mechanical',form='bird',realm_index=9,layer=1,
        body_training=100,immortal_body_level=0,divine_sense_rank=101,combat_power=combat_power(p),
        durability=100,alive=True,operating_energy=5,energy_source_id='npc_training_puppet_energy_3')
    p.puppets=[bird]
    engine._combat(g,dict(target_name='供能演武',target_power=combat_power(p)*3,target_realm_index=9,
        target_layer=1,combat_type='cultivator',max_rounds=3),False,random.Random(18))
    p.hp=max_hp(p);p.mp=max_mp(p)
    n=SectNpc('release-student','育才弟子','弟子',9,1,300,None,world=p.world,location_id=p.location_id,
        path=p.path,gender='female',race='human',spirit_root='supreme_metal',body_training=100,
        immortal_body_level=10,divine_sense_rank=101,transcendence=dict(conversion=1,capacity=1000,current=17))
    g.world_npcs[n.id]=n;p.disciples=[g.link_relationship({'id':n.id})]
    book=copy.deepcopy(TECHNIQUE_CATALOG['TECH_BASIC_QI']);p.known_techniques.append(book);learn(n,book,slot='main')
    for axis in ('body_art','domain','technique'):add_item(p,f'npc_training_{p.path}_{axis}_3',20)
    add_item(p,'npc_training_puppet_energy_3',4)
    for form in FORMS:
        if form=='bird':continue
        p.puppets.append(dict(bird,id='release-'+form,name='机关'+form,form=form,operating_energy=0))
    for gender in ('male','female'):
        p.puppets.append(dict(bird,id='release-corpse-'+gender,name='炼尸'+gender,type='corpse',gender=gender,operating_energy=0))
    held=SectNpc('release-prisoner','受禁修士','修士',9,1,300,None,world=p.world,location_id=p.location_id,
        path=p.path,gender='male',race='human',spirit_root='supreme_metal',body_training=100,immortal_body_level=10)
    g.world_npcs[held.id]=held;p.prisoners.append(g.detain_person({'id':held.id,'combat_power':500}))
    g.settings.update(combat_popup=False,silent_events=True);engine.store.save(g)
    return g
