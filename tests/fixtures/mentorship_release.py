"""Disposable original actors for final EXE and signed Android acceptance."""
def prepare_mentorship(engine, identity):
    from cultivation_life.models import SectNpc
    from cultivation_life.content_registry import ITEM_CATALOG, TECHNIQUE_CATALOG
    from cultivation_life.rules import can_player_practice_technique
    from cultivation_life.system import mentorship as m
    from cultivation_life.system.npc_techniques import learn
    game=engine.store.load(identity);p=game.player;game.pending_event=None
    teacher=SectNpc('release-mentor','松风真人','授业师父',4,7,100,1000,
                    world=p.world,location_id=p.location_id,spirit_root=p.spirit_root,gender='male')
    game.world_npcs[teacher.id]=teacher;p.master=game.link_relationship({'id':teacher.id})
    m.admit(game,teacher.id,'player')
    peer=m.person(game,'school:release-mentor:0');peer.name='云岫';peer.affinity=60
    peer.treasure_item_id=next(iter(ITEM_CATALOG));peer.treasure_looted=False
    known={t.id for t in p.known_techniques}
    art=next(t for t in TECHNIQUE_CATALOG.values() if t.id not in known and can_player_practice_technique(p,t))
    learn(peer,art);p.opportunity=0;game.settings['combat_popup']=False
    engine.store.save(game)

