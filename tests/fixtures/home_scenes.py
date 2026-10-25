"""Disposable save fixtures for source, compiled and native presentation checks."""
import random
from cultivation_life.rules import max_hp, max_mp


def thunder(engine, identity):
    game=engine.store.load(identity);p=game.player
    game.settings.update(silent_events=True,combat_popup=False)
    game.pending_event=None;p.path='dao';p.realm_index=4;p.layer=1;p.hp=max_hp(p);p.mp=max_mp(p)
    game.active_trial=dict(kind='periodic_thunder',step_index=0,
        event_ids=[f'EVT_PERIODIC_THUNDER_00{i}' for i in range(1,4)],lethal=True,power=1,
        base_power=1,old_label='化神',major=False)
    game.pending_event=engine._instantiate_event(engine.events_by_id[game.active_trial['event_ids'][0]],game,random.Random(6))
    engine.store.save(game)
    return game


def mirrors(engine,identity):
    game=engine.store.load(identity);p=game.player;game.pending_event=None;game.active_trial=None
    p.hp=max_hp(p);p.mp=max_mp(p);game.settings.update(silent_events=True,combat_popup=False)
    power=engine._player_battle_power(game)*.2
    target=dict(target_name='镜像验收',target_power=power*3,target_realm_index=p.realm_index,combat_type='trial',
        members=[dict(name=name,power=power,realm_index=p.realm_index,layer=p.layer,path=p.path,
            kind='environment',visual_variant=variant) for name,variant in [('自我尸','corpse_self'),('本我尸','corpse_primal'),('超我尸','corpse_superego')]])
    engine._combat(game,target,False,random.Random(606))
    engine.store.save(game)
    return game
