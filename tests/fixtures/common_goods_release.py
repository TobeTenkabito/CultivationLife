"""Disposable copies only; ordinary commands perform all tested mutations."""
import random
from cultivation_life.rules import add_item, max_hp, max_mp, combat_power


def prepare_common_goods(engine, identity):
    game = engine._load(identity)
    p = game.player
    assert combat_power(p) >= 43690
    assert all(t.level == 8 for t in p.combat_techniques)
    game.pending_event = game.active_trial = None
    game.settings.update(silent_events=True,guixu_event_popup=False)
    p.realm_index, p.layer = 4, 1
    p.lifespan = max(p.age+1000,p.lifespan or 0)
    p.hp, p.mp = max_hp(p)/2, max_mp(p)/2
    p.inventory = []
    for item, quantity in [('spirit_stone',100000),('econ_human_4_core_blood',1),
                          ('econ_human_4_talisman_protection',1),('econ_human_4_ore_structure',1),
                          ('econ_human_4_ore_conduct',2),('econ_human_4_ore_store',1)]:
        add_item(p,item,quantity)
    engine._schedule_auction(game,random.Random(2151))
    game.auction_state.update(auction_class=3,class_name='高级',rank_band=[5],entry_fee=500,
        location_id=p.location_id,location_name=engine.maps.location(p.world,p.location_id)['name'])
    engine._open_auction(game,random.Random(2151))
    engine.store.save(game)


def common_goods_wallet(engine, identity, amount):
    game = engine._load(identity)
    next(i for i in game.player.inventory if i.id == 'spirit_stone').quantity = amount
    engine.store.save(game)


def common_goods_black_market(engine, identity):
    game = engine._load(identity)
    engine._finish_auction(game,random.Random(2151))
    engine.store.save(game)


def inspect_common_goods(engine, identity):
    game = engine._load(identity)
    p = game.player
    assert next(h for h in game.history if h.event_id == 'SYS_ECONOMIC_MEDICINE').state_diff['gain'] == 400
    assert game.auction_state['entry_paid']
    assert len([h for h in game.history if h.event_id == 'SYS_AUCTION_ENTRY']) == 1
    row = next(r for r in p.talismans if r['method_id'] == 'econ_human_4_talisman_protection')
    assert row['enabled'] and row['uses'] == 3 and row['protection'] == 16
    assert not any(i.id == 'econ_human_4_talisman_protection' for i in p.inventory)
    assert not any('ore_' in i.id for i in p.inventory)
    artifact = next(a for a in p.crafted_artifacts if a['name'] == '通用矿材验收')
    assert artifact['scaling_realm_index'] == 4


def common_goods_recipe():
    return dict(mold_id='sword',primary_id='common:econ_human_4_ore_structure:0',
        secondary_a_id='common:econ_human_4_ore_conduct:0',secondary_b_id='common:econ_human_4_ore_conduct:1',
        quench_id='common:econ_human_4_ore_store:0',allocations={'combat_power':10},name='通用矿材验收')
