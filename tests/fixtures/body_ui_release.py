"""Disposable release-only preparation; never used by normal game loading."""
PRESETS={'dao':'true_immortal','demonic':'asura_upper','monster':'nether_upper','ghost':'reincarnation_upper'}
PANELS={'dao':'golden-light','demonic':'asura-body','monster':'monster-body','ghost':'ghost-body'}
BUTTONS={'dao':'[data-divine-light-train=kun]','demonic':'[data-aggregate=se]',
         'monster':'[data-monster-change=xuanfu]','ghost':'[data-ghost-refine=wuxiang]'}
LEVELS={'dao':'game.golden_light.lights[0].level','demonic':'game.asura.aggregates[0].level',
        'monster':'game.upper_voisinages.monster_body.rows[0].level','ghost':'game.upper_voisinages.ghost_body.rows[0].level'}

def prepare_body_ui(engine,identity):
    import random
    from cultivation_life.rules import add_item,max_hp,max_mp
    from cultivation_life.system.divine_lights import definitions
    from cultivation_life.system.wuyun import definitions as aggregates
    from cultivation_life.system.monster_body import config
    from cultivation_life.ghost_body_content import MATERIAL_IDS,IDS
    g=engine._load(identity);p=g.player;g.pending_event=None;g.active_trial=None
    p.next_tribulation_age=None;p.body_training=100;p.opportunity=10**12;p.immortal_traces=10**6
    p.immortal_body.update(level=50,divine_lights={r['id']:1 for r in definitions()},
        ghost_training={key:1 for key in IDS},monster=dict(level=50,training={r['id']:1 for r in config().get('mechanisms',[])}))
    p.asura_cultivation.update(conversion=5,body_level=50,souls=100000,route='asura',level=9,
        domain_rank=8,domain_power=10,domain_name='发行演武域',discipline_plan={'mode':'blood'},
        aggregates={r['id']:1 for r in aggregates()})
    for row in [*definitions(),*aggregates(),*config().get('mechanisms',[])]:
        for key in row['recipe']:add_item(p,key,10000)
    for key in MATERIAL_IDS:add_item(p,key,10000)
    p.immortal_aperture.update(capacity=6000,current=6000)
    p.hp=max_hp(p);p.mp=max_mp(p);g.settings.update(combat_popup=False,silent_events=True)
    engine._combat(g,dict(target_name='发行演武',target_power=engine._player_battle_power(g),
        target_realm_index=9,target_layer=1,kind='environment',combat_type='cultivator',max_rounds=2),False,random.Random(350))
    # Each assertion case starts healthy, with a genuine frozen battle report.
    p.hp=max_hp(p);p.mp=max_mp(p);p.immortal_aperture['current']=6000
    engine.store.save(g)
    return g


def prepare_npc_roster(engine,identity):
    """New arrivals in an existing local sect, in disposable acceptance saves only."""
    import random
    g=engine.store.load(identity)
    sect=next(s for s in g.sects.values() if s.world==g.player.world and s.kind=='sect' and not s.extinct)
    g.player.faction_id=sect.id;g.pending_event=None
    # Exercise the production recruitment constructor, then bound the visual fixture's age.
    for gender in ('male','female'):
        npc=None
        for seed in range(30):
            npc=engine._recruit_sect_npc(sect,g.player.age,random.Random(351+seed))
            if npc:break
        assert npc is not None
        npc.name='新入门'+('少年' if gender=='male' else '少女')
        npc.gender=gender;npc.race='human';npc.path='dao';npc.age=16
    engine.store.save(g)
    return g
