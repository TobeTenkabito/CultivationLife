"""Disposable monster art fixtures shared by browser, EXE and native acceptance."""
import random


def monster_visual_cases():
    from cultivation_life import content_registry as registry
    from cultivation_life.models import Player
    from cultivation_life.monster_visuals import monster_appearance
    found={}
    for node,n in registry.MONSTER_EVOLUTIONS.items():
        for gender in ['female','male']:
            p=Player(name='外观验收',spirit_root='heavenly',path='monster',gender=gender,
                     monster_species_id=n['species'],monster_evolution_id=node,monster_evolution_history=[node])
            appearance=monster_appearance(p)
            if appearance:
                found.setdefault(appearance['static'],dict(species=n['species'],node=node,gender=gender,
                                 realm=n['realm_index'],**appearance))
    return list(found.values())


def prepare_monster_visual(engine, identity, case):
    from cultivation_life.content_registry import MONSTER_EVOLUTIONS
    from cultivation_life.monster_visuals import monster_appearance
    game=engine.store.load(identity)
    p=game.player
    p.monster_species_id=case['species'];p.monster_evolution_id=case['node']
    p.monster_evolution_history=[case['node']]
    p.realm_index=MONSTER_EVOLUTIONS[case['node']]['realm_index'];p.layer=1;p.gender=case['gender']
    p.awaiting_major_breakthrough=False
    game.pending_event=None;game.settings.update(silent_events=True,combat_popup=True)
    expected=monster_appearance(p)
    assert expected and expected['static']==case['static']
    engine._combat(game,dict(target_name='演武对手',path='dao',gender='male',combat_type='cultivator',
                   target_realm_index=p.realm_index,target_power=engine._player_battle_power(game)*.5),False,random.Random(4190))
    assert game.last_combat_report['visual']['hero']==expected['combat']
    engine.store.save(game)


def prepare_monster_evolution(engine, identity):
    from cultivation_life.content_registry import REALMS
    from cultivation_life.rules import opportunity_required
    game=engine.store.load(identity)
    p=game.player;p.monster_species_id='flora';p.monster_evolution_id='FLORA_ANCIENT_TREE'
    p.monster_evolution_history=['FLORA_BASE','FLORA_SPIRIT','FLORA_ANCIENT_TREE']
    p.realm_index=2;p.layer=REALMS[2].layers;p.opportunity=opportunity_required(p)
    p.awaiting_major_breakthrough=True;game.pending_event=None
    game.settings['silent_events']=True
    engine.store.save(game)
