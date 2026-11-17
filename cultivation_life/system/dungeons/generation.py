"""Independent immutable seed streams and finite map slots; no world simulation."""
import hashlib
import random
from ...dungeon_schema import QUALITIES, PURPOSES
from ...cultivation_coordinates import rank_for
from ...reputation import true_rank
from ...content_registry import WORLD_SYSTEMS, FACTION_DEFINITIONS
from .rewards import recipe
from . import prose, scenes

NAMES = ('沈砚','洛凝','陆衍','顾长庚','宋微澜','钟离朔','叶闻秋','秦照','温玄','韩晚舟','裴渊','萧弦','许承风','苏问尘','关苍','陈雪岑')
NAMES += tuple(prose.extra.PERSON_NAMES)
THEMES = {'water':('沉水','水府','潮眼','积水石阶'),'mountain':('镇岳','洞府','地脉','断裂岩桥'),
    'fire':('离火','炉宫','火眼','熔岩裂谷'),'frost':('凝霜','冰宫','冰髓','覆霜长廊'),
    'fort':('古塞','遗堡','阵枢','残破门楼'),'shadow':('照夜','冥宫','魂灯','阴风侧殿'),
    'grove':('青木','药圃','灵根','荒草石径'),'ruins':('归藏','古府','灵纹','倾塌石廊')}


def stream(seed, *parts):
    return random.Random(int.from_bytes(hashlib.sha256((':'.join(map(str,(seed,*parts)))).encode()).digest(),'big'))


def config():return WORLD_SYSTEMS['seeded_dungeons']


def generate(game, location, slot, legends):
    p=game.player;world=p.world;profile=config()['profiles'][world+':'+location['id']]
    identity=f'dungeon:{world}:{location["id"]}:{slot}'
    rng=stream(game.seed,identity,'v1');ceiling=config()['ceilings'][world]
    weights=profile['weights'][:]
    if legends>=config()['legendary_limit'][world]:weights[-1]=0
    quality=rng.choices(QUALITIES,weights=weights)[0]
    index=QUALITIES.index(quality)
    realm=ceiling if quality=='legendary' else min(profile['cap'],profile['realm']+(index//2))
    reference=true_rank(p)
    tier=WORLD_SYSTEMS['world_profiles'][world]['tier']
    theme=profile['theme'];words=THEMES[theme]
    name=words[0]+rng.choice(('太微','九曜','承露','含章','流霞','问玄','长离','栖真','照夜','归藏','怀璧','通幽','观澜','悬星','鸣玉','玄都','少清','停云','步虚','洞明')+tuple(prose.extra.NAMES))+words[1]
    factions=[(sect.id,sect.name) for sect in game.sects.values() if sect.world==world and not sect.extinct]
    if not factions:factions=[(None,'散修')]
    roles={}
    count=(2,4,10,16)[index]
    for number in range(count):
        rr=stream(game.seed,identity,'role',number);key=identity+':person:'+str(number)
        sect_id,sect_name=rr.choice(factions)
        purpose=rr.choices(PURPOSES,weights=[35,15,15,10,10,15])[0]
        role_realm=min(ceiling,max(1,realm+rr.choice((-1,0,0,1))))
        layer=rr.randint(3,9)
        if purpose=='assassinate' and rank_for(role_realm,layer)<rank_for(*reference):
            if reference[0]>ceiling or reference[0]>max(realm,profile['cap']) and quality not in {'epic','legendary'}:
                purpose='observe'
            else:role_realm,layer=reference
        true_realm=role_realm
        if quality=='legendary' and number==count-1:
            true_realm={1:6,2:9,3:12}[tier];role_realm=min(ceiling,true_realm);layer=9
        domain_rank=0
        if true_realm>9:domain_rank=rr.randint(1,9)
        elif true_realm==9 and layer>=7 and (rr.random()<.12 or quality=='legendary' and number==count-1):domain_rank=1
        if true_realm==12 and layer>=7 and rr.random() < (.65 if quality=='legendary' and number==count-1 else .05):domain_rank=13
        # Claimed purpose is not a code for the private purpose, even across runs.
        story=rr.choice(prose.STORIES)
        roles[key]=dict(id=key,name=NAMES[(rr.randrange(len(NAMES))+number)%len(NAMES)],sect_id=sect_id,
            sect_name=sect_name,realm=role_realm,layer=layer,true_realm=true_realm,
            path=game.sects[sect_id].path if sect_id in game.sects else {'demon':'demonic','true_demon':'demonic','asura':'demonic','nether':'monster','reincarnation':'ghost','hell':'ghost','phantom_underworld':'monster','monster_realm':'monster'}.get(world,'dao'),
            purpose=purpose,desire=rr.randint(45,100),resolve=95 if purpose=='assassinate' else rr.randint(30,75),
            preparation=rr.randint(15,45),trust=rr.randint(15,50),caution=rr.randint(30,80),
            npc_id=None,existing=False,state='unseen',known=False,clues=[],target='player' if purpose=='assassinate' else 'treasure',
            story=story,power_factor=round(rr.uniform(.9,1.3),3),joined_step=None,left_step=None,
            revealed=False,materialized=False,ledger={'domain_rank':domain_rank},offer_step=rr.randint(1,4))
    nodes=[];structures=scenes.history(game);texts=set(game.dungeon_state.get('text_fingerprints',[]))
    for number in range(profile['nodes']):
        nr=stream(game.seed,identity,'node',number)
        kind,mechanism,variant,actor=scenes.structure(nr,roles,structures,core=number==profile['nodes']-1)
        direction=nr.choice(('东','西','南','北','东北','西北'))
        text=scenes.compose(nr,location['name'],theme,kind,direction,mechanism,texts)
        nodes.append(dict(id=identity+':node:'+str(number),kind=kind,mechanism=mechanism,variant=variant,text=text,
            risk=round(nr.uniform(.04,.12)*(1+index*.2),3),
            reward=recipe(stream(game.seed,identity,'reward',number),identity+':reward:'+str(number),realm,p.path,theme,quality,core=kind=='core',world=world),
            actor=actor,direction=direction))
    if quality=='legendary':nodes[-1]['actor']=next(reversed(roles))
    site=dict(id=identity,world=world,location_id=location['id'],name=name,quality=quality,realm=realm,
        layer=9 if quality=='legendary' else 5,ceiling=ceiling,theme=theme,terrain=profile['terrain'],
        conditions=profile['conditions'][:],slot=slot,seed=rng.randrange(2**32),reference=list(reference),
        roles=roles,nodes=nodes,status='open',revision=0,step=0,depth=0,logs=[],party=[],claims=[],pending=None,
        entered=False,unit=0,preparations=0,agreements={},revealed=False,last_result='',node_history=[],branches=[],initiator=None)
    from .expedition import blueprint
    from .rewards import bounded_recipe, resource_recipe, bound_growth_budget
    for number,node in enumerate(nodes):
        bounded_recipe(node['reward'],quality,world)
        if number==len(nodes)//2:
            resource=resource_recipe(stream(game.seed,identity,'resource',number),node['reward']['id'],realm,world,p.path,quality)
            if resource:node['reward']=resource
    def bonus(number):
        reward=recipe(stream(game.seed,identity,'gratitude',number),identity+':bonus:'+str(number),realm,p.path,theme,quality,world=world)
        bounded_recipe(reward,quality,world)
        return reward
    site['expedition']=blueprint(site,stream(game.seed,identity,'expedition-v2'),bonus)
    bound_growth_budget(site)
    return site
