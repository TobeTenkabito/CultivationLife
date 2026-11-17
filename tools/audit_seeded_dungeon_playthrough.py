"""Paired, persisted playthroughs through public commands and original combat.

Fixtures are new custom lives in an isolated directory. Quality is stratified;
the sampling weights alone are forced, never victory, loot or actor decisions.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cultivation_life.engine import GameEngine
from cultivation_life.models import GameState
from cultivation_life.content_registry import ITEM_CATALOG, WORLD_SYSTEMS, MARKET_GOODS, TECHNIQUE_CATALOG
from cultivation_life.rules import combat_power, max_hp, max_mp, can_player_practice_technique
from cultivation_life.soul_rules import wandering
from cultivation_life.system.dungeons import generation
from scripts.release_evidence import inputs_digest

BUILDS=[('human',2,'dao','plain'),('human',4,'dao','equipped'),('human',5,'dao','equipped'),
        ('demon',5,'demonic','equipped'),('spirit',6,'dao','plain'),('spirit',8,'dao','domain'),
        ('monster_realm',8,'monster','domain'),('hell',8,'ghost','equipped'),
        ('celestial',9,'dao','domain'),('celestial',12,'dao','domain'),
        ('celestial',12,'buddhist','equipped'),('celestial',12,'confucian','equipped')]
POLICIES=('edge','deep','core','aid')


def snapshot(game):
    p=game.player
    return dict(alive=p.alive,wandering=wandering(p),captured=bool(p.imprisonment or p.ghost_captor),
        crisis=bool(p.nascent_state.get('crisis')),age=p.age,hp=p.hp,mp=p.mp,
        max_hp=max_hp(p),max_mp=max_mp(p),power=combat_power(p),opportunity=p.opportunity,
        traces=p.immortal_traces,infamy=p.infamy,
        inventory={i.id:i.quantity for i in p.inventory},energy=p.immortal_aperture.get('current',0))


def setup(engine,build,seed):
    world,rank,path,loadout=build
    mastered=loadout=='mastered'
    ids={r['content_id'] for r in MARKET_GOODS if r.get('kind')=='item' and r.get('tier')==rank and r.get('world')==world}
    equipment=sorted((i for i in ITEM_CATALOG.values() if i.id in ids and i.combat_bonus>0 and 'pill' not in i.tags),
                     key=lambda i:(i.combat_bonus,i.id),reverse=True)
    inventory=[dict(id=i.id,quantity=1) for i in equipment[:2]] if loadout!='plain' else []
    made=engine.create_game('副本实战验收','supreme_earth',path,seed,monster_species_id='fox' if path=='monster' else None,
        custom_start=dict(world=world,realm_index=rank,layer=9 if mastered else 7,inventory=inventory,
            body_training=100 if mastered else rank*3 if loadout!='plain' else 0,
            immortal_body_level=50 if mastered else 10 if rank>=9 else 0,
            domain_rank=(13 if rank==12 else 3) if loadout in {'domain','mastered'} else 0))
    game=engine.store.load(made['id'])
    # Initial fixture address only: choose a real local map near the build's rank.
    profiles=[(k,p) for k,p in generation.config()['profiles'].items() if k.startswith(world+':')]
    scope,_=min(profiles,key=lambda v:(abs(v[1]['realm']-rank),abs(v[1]['cap']-rank),v[0]))
    game.player.location_id=scope.split(':',1)[1]
    if mastered:
        # Explicit mature-build fixture, still bounded by authored grade and Lv9.
        # Combat outcomes, enemies and loot are never edited.
        from cultivation_life.rules import learn_technique,assign_technique
        books=sorted((t for t in TECHNIQUE_CATALOG.values() if t.grade==rank and t.path==path
            and t.category=='spiritual' and can_player_practice_technique(game.player,t)),
            key=lambda t:(t.combat_bonus,t.id),reverse=True)
        for slot,template in zip(('main','support'),books[:2]):
            book=copy.deepcopy(template);book.level=9
            learn_technique(game.player,book);assign_technique(game.player,book,slot)
    game.settings['silent_events']=True
    game.player.hp=max_hp(game.player);game.player.mp=max_mp(game.player)
    engine.store.save(game);engine.get_game(game.id)
    return engine.store.load(game.id).to_dict()


def submit(engine,gid,action,**payload):
    game=engine.store.load(gid);state=game.dungeon_state
    site=state['instances'][state['active']] if state.get('active') else list(state['instances'].values())[-1]
    return engine.dungeon_action(gid,action,dict(dungeon_id=site['id'],revision=site['revision'],**payload))


def choose(view,policy):
    session=view['dungeons']['session'];options={c['id'] for c in session['choices'] if c['enabled']}
    if 'accept' in options:return 'accept' if policy=='aid' else 'decline'
    if 'decline' in options:return 'decline'
    if 'part' in options:return 'part'
    if 'support_actor' in options:
        if policy!='aid':return 'flee'
        names=[c['label'].removeprefix('援助') for c in session['choices'][:2]]
        strengths=[next(p['comparison']['power'] for p in session['people'] if p['name']==name) for name in names]
        return ('support_actor','support_other')[int(strengths[1]<strengths[0])]
    if 'fight' in options:
        if policy=='edge':return 'flee'
        if policy=='core':return 'fight'
        hostile=[p for p in session['people'] if p['state']=='hostile']
        if any(p['comparison']['power']>session['player_comparison']['power']*1.5 for p in hostile):return 'flee'
        return 'fight'
    if 'survey' in options:return 'survey' if policy!='core' else 'bypass'
    for candidate in ('disarm','attune','seize','bypass'):
        if candidate in options:return candidate
    return None


def play(engine,document,quality,policy):
    game=GameState.from_dict(copy.deepcopy(document));gid=game.id;engine.store.save(game)
    before=snapshot(game);cfg=copy.deepcopy(generation.config())
    scope=game.player.world+':'+game.player.location_id
    cfg['profiles'][scope]['weights']=[int(q==quality) for q in generation.QUALITIES]
    with patch.object(generation,'config',lambda:cfg):
        view=engine.dungeon_action(gid,'discover',dict(world=game.player.world,location_id=game.player.location_id,slot=0))
    frozen=engine.store.load(gid).dungeon_state['instances'][view['dungeons']['sites'][0]['id']]
    view=submit(engine,gid,'enter');commands=[];reports=set()
    for _ in range(150):
        game=engine.store.load(gid);session=view['dungeons']['session']
        if not session:break
        site=game.dungeon_state['instances'][session['id']]
        options={c['id'] for c in session['choices'] if c['enabled']}
        medicine=next((i for i in game.player.inventory if 'dungeon_restorative' in i.tags and i.quantity>0),None)
        if medicine and not site['pending'] and (game.player.hp<max_hp(game.player)*.6 or game.player.mp<max_mp(game.player)*.3):
            view=engine.use_item(gid,medicine.id);commands.append('use_restorative');continue
        end=not session['choices']
        exhausted=game.player.hp<max_hp(game.player)*.45 or game.player.mp<max_mp(game.player)*.15
        if session['can_exit'] and (end or policy=='edge' and site['claims'] or policy in {'deep','aid'} and exhausted):
            view=submit(engine,gid,'exit');commands.append('exit');continue
        # Core-seeking uses only visible current scene/end information; it never
        # reads future actors, rewards, motives or hidden pressure scores.
        choice=choose(view,policy)
        if policy=='core' and not site['pending'] and session['place']=='核心':choice='seize'
        if choice is None:raise AssertionError('No legal choice before the exploration ended')
        view=submit(engine,gid,'choose',choice=choice);commands.append(choice)
        report=engine.store.load(gid).last_combat_report
        if report:reports.add(hashlib.sha256(json.dumps(report,sort_keys=True).encode()).hexdigest())
    else:raise AssertionError('Playthrough failed to terminate within the bounded action budget')
    game=engine.store.load(gid);site=game.dungeon_state['instances'][frozen['id']];after=snapshot(game)
    assert after['age']==before['age'] and not game.dungeon_state['active']
    returned=after['alive'] and not any(after[k] for k in ('wandering','captured','crisis'))
    # Measure actual playable adoption separately from ownership of an upper-rank book.
    learned=[]
    if returned:
        for item in list(game.player.inventory):
            if 'dungeon_restorative' in item.tags:
                for _ in range(item.quantity):engine.use_item(gid,item.id)
        for key,row in list(game.dungeon_state['manuals'].items()):
            if row['book']['grade']<=game.player.realm_index:
                from cultivation_life.models import Technique
                if can_player_practice_technique(game.player,Technique(**row['book'])):
                    engine.dungeon_action(gid,'learn',dict(manual_id=key));learned.append(key)
        game=engine.store.load(gid)
        candidates=[t for t in game.player.known_techniques if t.id in learned and t.category=='spiritual']
        if candidates:
            book=max(candidates,key=lambda t:t.combat_bonus)
            if not game.player.technique or book.combat_bonus>game.player.technique.combat_bonus:
                engine.equip_known_technique(gid,book.id,'main')
    game=engine.store.load(gid);adopted=snapshot(game)
    return dict(quality=quality,policy=policy,returned=returned,alive=after['alive'],wandering=after['wandering'],
        captured=after['captured'],crisis=after['crisis'],core=site['nodes'][-1]['reward']['id'] in site['claims'],
        fused_core=site['nodes'][-1]['reward']['fused'] and site['nodes'][-1]['reward']['id'] in site['claims'],
        claims=len(site['claims']),commands=commands,fights=len(reports),
        opportunity=adopted['opportunity']-before['opportunity'],traces=adopted['traces']-before['traces'],
        hp_spent=before['hp']-after['hp'],mp_spent=before['mp']-after['mp'],energy_spent=before['energy']-after['energy'],
        infamy=after['infamy']-before['infamy'],cooldown=game.dungeon_state['ready_age']-game.player.age,
        starting_power=before['power'],power_gain=adopted['power']-before['power'],learned=len(learned),
        retained={k:v-before['inventory'].get(k,0) for k,v in after['inventory'].items() if v>before['inventory'].get(k,0)},
        generated_people=sum(r['materialized'] for r in site['roles'].values()))


def baseline(engine,document):
    game=GameState.from_dict(copy.deepcopy(document));engine.store.save(game);before=snapshot(game)
    engine.advance(game.id,'cultivate',1)
    after=snapshot(engine.store.load(game.id))
    return dict(elapsed=after['age']-before['age'],opportunity=after['opportunity']-before['opportunity'],
        traces=after['traces']-before['traces'],power_gain=after['power']-before['power'],alive=after['alive'])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--seeds',type=int,default=4)
    parser.add_argument('--builds',type=int,default=len(BUILDS));parser.add_argument('--offset',type=int,default=0)
    parser.add_argument('--qualities',nargs='+',default=list(generation.QUALITIES));parser.add_argument('--policies',nargs='+',default=list(POLICIES))
    parser.add_argument('--expert',action='store_true')
    parser.add_argument('--output',default='build/reviews/seeded-dungeons/playthrough.json');args=parser.parse_args()
    source=inputs_digest(ROOT);start=time.monotonic();rows=[];baselines=[]
    output=ROOT/args.output;output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='dungeon-balance-') as folder:
        engine=GameEngine(ROOT,Path(folder)/'saves')
        # Only omit thawing unrelated read-only panels. Native prepare_response,
        # boundary settlement, transactions, file saves and combat still run.
        engine.project_game=lambda prepared:dict(id=prepared._payload['id'],dungeons=prepared._payload['dungeons'])
        builds=[('celestial',12,'dao','mastered')] if args.expert else BUILDS[args.offset:args.offset+args.builds]
        for build in builds:
            for seed in range(840,840+args.seeds):
                document=setup(engine,build,seed)
                normal=baseline(engine,document);normal.update(build=list(build),seed=seed);baselines.append(normal)
                for quality in args.qualities:
                    for policy in args.policies:
                        row=play(engine,document,quality,policy);row.update(build=list(build),seed=seed)
                        row['opportunity_action_units']=row['opportunity']/normal['opportunity'] if normal['opportunity']>0 else None
                        rows.append(row)
                        output.write_text(json.dumps(dict(source=source,complete=False,rows=rows,baselines=baselines),ensure_ascii=False,indent=2),encoding='utf-8')
                print(json.dumps(dict(build=build,seed=seed,runs=len(rows),seconds=round(time.monotonic()-start,1))),flush=True)
    result=dict(source=source,final_source=inputs_digest(ROOT),complete=True,seconds=round(time.monotonic()-start,1),
        protocol='Isolated custom starts; public command/save/combat; forced quality strata; paired seeds; no victory or reward mocking.',
        rows=rows,baselines=baselines)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(runs=len(rows),baselines=len(baselines),seconds=result['seconds'],output=str(output))),flush=True)


if __name__=='__main__':main()
