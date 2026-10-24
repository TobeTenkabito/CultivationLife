"""Disposable visual fixtures, never writes real player saves."""
import random

def path_character_cases():
    return [dict(path=p,gender=g,static=f'actor.path.{p}-hero-{g}',combat=f'{p}-hero-{g}',npc=f'{p}-npc-{g}')
            for p in ['ghost','confucian','buddhist'] for g in ['female','male']]

def prepare_path_character(engine,identity,case,core_hero=False):
    from cultivation_life.models import SectNpc
    game=engine.store.load(identity);p=game.player
    p.path='dao' if core_hero else case['path'];p.gender=case['gender'];p.race='human';p.lineage_race='human'
    p.ghost_host_body=None;p.ghost_attachment=None
    game.pending_event=None;game.settings.update(silent_events=True,combat_popup=True)
    npc=SectNpc(id='path-art-person',name='三道同道',title='同道',realm_index=3,layer=1,age=80,lifespan=500,
                path=case['path'],gender=case['gender'],race='human',world=p.world,affinity=20)
    game.notable_npcs[npc.id]=npc
    engine._combat(game,dict(target_name='道途演武',path=case['path'],gender=case['gender'],race='human',combat_type='cultivator',
        target_realm_index=p.realm_index,target_power=engine._player_battle_power(game)*.5),False,random.Random(510))
    assert game.last_combat_report['visual']['enemy']==case['npc']
    if not core_hero:assert game.last_combat_report['visual']['hero']==case['combat']
    engine.store.save(game)
