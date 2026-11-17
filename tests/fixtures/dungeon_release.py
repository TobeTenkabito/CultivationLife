"""Isolated acceptance fixtures; rewards are acquired through real page commands."""
import copy
import random
from cultivation_life.content_registry import ITEM_CATALOG, TECHNIQUE_CATALOG
from cultivation_life.rules import add_item,max_hp,max_mp
from cultivation_life.system.dungeons.rewards import recipe,bounded_recipe


def prepare_dungeon_player(engine,identity):
    game=engine.store.load(identity)
    game.pending_event=None
    game.player.realm_index=4;game.player.layer=9
    game.player.hp=max_hp(game.player);game.player.mp=max_mp(game.player)
    game.settings['combat_popup']=True
    for category in ('body','divine_sense','transformation'):
        book=min((t for t in TECHNIQUE_CATALOG.values() if t.category==category and t.element=='neutral'),key=lambda t:t.grade)
        if all(t.id!=book.id for t in game.player.known_techniques):game.player.known_techniques.append(copy.deepcopy(book))
    for item in [i for i in ITEM_CATALOG.values() if 'pill' in i.tags][:12]:add_item(game.player,item.id)
    engine.store.save(game)


def prepare_dungeon_loot(engine,identity):
    game=engine.store.load(identity);site=next(iter(game.dungeon_state['instances'].values()))
    rewards=[]
    for index,kind in enumerate(('pill','artifact','technique')):
        node=site['nodes'][index]
        for seed in range(100):
            reward=recipe(random.Random(seed),node['reward']['id'],site['realm'],'dao',site['theme'],site['quality'],world='human')
            if reward['kind']==kind:break
        else:raise AssertionError(kind)
        bounded_recipe(reward,site['quality'],'human')
        node.update(kind='cache',mechanism='cache',risk=0,reward=reward)
        rewards.append(reward)
    for role in site['roles'].values():role.update(state='declined',offer_step=99)
    engine.store.save(game)
    return dict(pill=rewards[0]['id'],relic=rewards[1]['id'],book=rewards[2]['book']['id'])


def prepare_dungeon_fight(engine,identity):
    game=engine.store.load(identity);site=game.dungeon_state['instances'][game.dungeon_state['active']]
    assert len(site['claims'])==3
    role=next(iter(site['roles'].values()))
    role.update(state='hostile',known=True,realm=1,true_realm=1,layer=1,power_factor=1.,purpose='seek')
    role['ledger']['domain_rank']=0
    site['pending']=dict(kind='guardian',actor=role['id'])
    engine.store.save(game)
