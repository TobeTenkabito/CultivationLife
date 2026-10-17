"""Isolated release snapshots; real UI commands perform purchases and cultivation."""
import copy
import random

from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.rules import acquire_technique, add_item, add_technique_copy


def prepare_common_techniques(engine, identity):
    game=engine._load(identity);p=game.player
    game.pending_event=game.active_trial=None
    p.realm_index,p.layer=4,1
    p.spirit_root='supreme_metal';p.additional_roots=[]
    p.technique=p.support_technique=p.body_technique=p.divine_sense_technique=p.transformation_technique=None
    p.combat_techniques=[];p.known_techniques=[]
    art=copy.deepcopy(TECHNIQUE_CATALOG['TECH_OPEN_SONGCHUANG_METAL_WATER_MAIN'])
    acquire_technique(p,art);add_technique_copy(p,art)
    add_item(p,'jinque_water');add_item(p,'spirit_stone',10000)
    engine._ensure_market(game,random.Random(7))
    for offer_id,book_id in [('old-rare-art','TECH_OPEN_SONGCHUANG_WIND_YIN_YANG_MAIN'),
                             ('ordinary-art','TECH_OPEN_SONGCHUANG_METAL_COMBAT')]:
        t=TECHNIQUE_CATALOG[book_id]
        game.market_offers.append(dict(id=offer_id,kind='technique',content_id=t.id,name=t.name,
            description='坊市传承玉简',element=t.element,price=100,tier=1,tier_name='练气',
            market_name='书坊',world=p.world,location_id=p.location_id,sold=False,locked=False))
    engine.store.save(game)


def lose_common_technique_root(engine, identity):
    game=engine._load(identity)
    assert game.player.technique.id=='TECH_OPEN_SONGCHUANG_METAL_WATER_MAIN'
    assert game.player.technique.level==2
    assert game.player.technique.required_affinities==['metal','water']
    assert not any(item.technique_id==game.player.technique.id for item in game.player.inventory)
    game.player.additional_roots=[]
    engine.store.save(game)
