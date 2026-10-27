"""Isolated acceptance fixture; mutations only prepare a disposable test save."""
def prepare_soul(engine, game_id):
    from cultivation_life.models import SectNpc, Item
    from cultivation_life.rules import add_item
    game=engine._load(game_id);p=game.player
    game.pending_event=None;game.active_trial=None
    p.realm_index=4;p.layer=1;p.lifespan=10000;p.divine_sense_rank=20;p.soul_energy=600
    p.body_training=10;p.body_energy=300
    add_item(p,'spirit_stone',100000)
    add_item(p,Item('release-soul-sword','验收法剑',combat_bonus=500,tags=['artifact']))
    n=SectNpc('release-nascent','清澜','散修',4,1,30,10000,spirit_root='supreme_metal')
    game.world_npcs[n.id]=n
    p.prisoners.append(game.detain_person(n.to_dict()))
    engine.store.save(game)
