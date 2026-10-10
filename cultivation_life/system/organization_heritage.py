"""Local libraries, paid copies and bounded study using prepaid member allowances."""
import copy
import hashlib
from functools import lru_cache

from ..content_registry import TECHNIQUE_CATALOG, MARKET_GOODS, WORLD_SYSTEMS, REALMS, restricted_acquisition
from ..rules import learn_technique, add_technique_copy, technique_scale, can_practice_technique
from ..npc_custody import is_free
from .economy import depot
from .economy import organization_accounts as organizations
from .economy.ledger import account, balance, transfer_value
from .faction_geography import faction_site


def ceiling(world):
    return {1:4, 2:7, 3:11}.get(WORLD_SYSTEMS['world_profiles'].get(world, {}).get('tier'), 0)


@lru_cache(maxsize=64)
def offers(world, path):
    rows = {}
    for good in MARKET_GOODS:
        identity = good['content_id']
        t = TECHNIQUE_CATALOG.get(identity) if good['kind'] == 'technique' else None
        if (t and good.get('world', 'human') == world and t.path == path
                and not restricted_acquisition('technique', identity) and t.active_in(world)
                and max(t.grade, good['tier']) <= ceiling(world)):
            rows[identity] = dict(id=identity, grade=max(t.grade, good['tier']), price=good['price'])
    return rows


def eligible(entity, identity):
    return identity in offers(entity.world, TECHNIQUE_CATALOG[identity].path) if identity in TECHNIQUE_CATALOG else False


def snapshot(entity):
    """Deterministic defaults, including before adoption; projection never writes."""
    if entity.heritage:
        return entity.heritage
    pool = sorted(offers(entity.world, entity.path).values(), key=lambda r:(r['grade'],r['id']))
    if not pool:
        pool=sorted({r['id']:r for path in ('dao','demonic','ghost','monster','buddhist','confucian')
                     for r in offers(entity.world,path).values()}.values(),key=lambda r:(r['grade'],r['id']))
    if not pool:
        return dict(books=[], revision=0, history=[])
    seed = int.from_bytes(hashlib.sha256(entity.id.encode()).digest()[:4], 'big')
    count = min(len(pool), 1 + seed % 3)
    # Include a basic inheritance, then select different ranks deterministically.
    chosen = [pool[0]['id']]
    for offset in range(count-1):
        target = pool[1+(seed+offset) % max(1,len(pool)-1)]['id'] if len(pool)>1 else pool[0]['id']
        if target not in chosen: chosen.append(target)
    return dict(books=chosen, revision=0, history=[])


def ensure(entity):
    if not entity.heritage:
        entity.heritage = copy.deepcopy(snapshot(entity))
    return entity.heritage


def note(game, entity, message):
    state=ensure(entity)
    state['revision'] += 1
    state['history']=(state.get('history',[])+[dict(year=game.player.age,text=message)])[-16:]


def member(game, entity):
    return entity is game.family or game.player.faction_id == entity.id


def controls(game,entity):
    if not member(game,entity) or entity.world!=game.player.world or entity.extinct: return False
    from .organization_authority import player_controls
    return player_controls(game,entity,entity.npcs,member=True)


def decision(game, entity):
    if not member(game, entity) or entity.world != game.player.world: return False
    row=game.intrigue_state.get('factions',{}).get(f'{depot.owner_kind(game,entity)}:{entity.id}',{})
    if row.get('controller_id') == 'player': return True
    kind=depot.owner_kind(game,entity)
    thresholds=WORLD_SYSTEMS['player_faction']['governance_threshold']
    fallback=2+WORLD_SYSTEMS['world_profiles'][entity.world]['tier'] if entity.kind=='family' else thresholds.get(entity.world,thresholds['human' if entity.world=='human' else 'spirit'])
    intrigue=WORLD_SYSTEMS.get('intrigue_dlc',{})
    threshold=intrigue.get('decision_thresholds',{}).get(kind,fallback) if intrigue.get('enabled') else fallback
    rank=(game.player.cultivation_suppression or game.player.sealed_cultivation or {}).get('realm_index',game.player.realm_index)
    return bool(controls(game,entity) or rank>=threshold)


def command(game, maps, payload):
    identity=payload.get('owner_id')
    entity=game.family if game.family and game.family.id==identity else game.sects.get(identity)
    p=game.player
    if (not entity or entity.extinct or entity.kind=='institution' or entity.world!=p.world
            or not member(game,entity) or faction_site(entity)['id']!=p.location_id):
        raise ValueError('请以本门成员身份亲赴驻地办理绝学事务')
    state=ensure(entity)
    if type(payload.get('revision')) is not int or payload['revision']!=state['revision']:
        raise ValueError('传承书目已变化，请刷新后重试')
    identity=payload.get('technique_id')
    if not eligible(entity,identity): raise ValueError('此功法不属本界普通传承，或超过本界绝学品阶上限')
    t=TECHNIQUE_CATALOG[identity]
    action=payload['action']
    known=next((k for k in p.known_techniques if k.id==identity),None)
    if action=='heritage_add':
        if not decision(game,entity): raise ValueError('收录绝学需要本组织决策权')
        if not known: raise ValueError('只能收录自己已经领悟的功法')
        if identity in state['books']: raise ValueError('本门已收录此功法')
        state['books'].append(identity)
        note(game,entity,f'{p.name}收录《{t.name}》作为本门绝学。')
    elif action=='heritage_learn':
        if identity not in state['books']: raise ValueError('本门没有收录此功法')
        if known: raise ValueError('已经领悟；再次领取玉简需要缴纳灵石')
        learn_technique(p,t)
        note(game,entity,f'{p.name}免费参悟《{t.name}》。')
    elif action=='heritage_copy':
        if identity not in state['books'] or not known: raise ValueError('请先免费参悟本门绝学')
        price=offers(entity.world,t.path)[identity]['price']
        fiscal=organizations.register(game,depot.owner_kind(game,entity),entity.id,entity.world)
        transfer_value(game,'player',depot.treasury(game,entity),price,'本门绝学玉简抄录费')
        fiscal['income']+=price
        add_technique_copy(p,t)
        note(game,entity,f'{p.name}缴纳{price}灵石，领取《{t.name}》Lv.1玉简。')
    else: raise ValueError('未知绝学操作')


def public(game, entity):
    if not entity or entity.extinct or entity.world!=game.player.world or entity.kind=='institution': return None
    state=snapshot(entity)
    known={t.id for t in game.player.known_techniques}
    books=[]
    for identity in state['books']:
        if not eligible(entity,identity): continue
        t=TECHNIQUE_CATALOG[identity]; offer=offers(entity.world,t.path)[identity]
        books.append(dict(id=identity,name=t.name,grade=REALMS[offer['grade']].name,price=offer['price'],learned=identity in known))
    return dict(owner_id=entity.id,revision=state['revision'],ceiling=REALMS[ceiling(entity.world)].name,
        local=game.player.location_id==faction_site(entity)['id'],can_add=decision(game,entity),books=books,
        add_options=[dict(id=t.id,name=t.name) for t in game.player.known_techniques if eligible(entity,t.id) and t.id not in state['books']],
        history=list(state.get('history',[])))


def allowance_account(game,entity):
    return account(game,f'study:{depot.owner_kind(game,entity)}:{entity.id}')


@lru_cache(maxsize=256)
def research_pool(world,path,rank):
    return tuple(r['id'] for r in offers(world,path).values() if r['grade']<=rank)


def advance_member(game,entity,npc):
    """Called inside the existing NPC loop. One decision per ten actual years."""
    if entity.kind=='institution' or not is_free(npc) or npc.world!=entity.world: return
    state=ensure(entity); facts=npc.family_traits.setdefault('heritage_study',{})
    period=game.player.age//10
    marker=f'{entity.id}:{period}'
    if facts.get('at')==marker: return
    facts['at']=marker
    digest=hashlib.sha256(f'{game.seed}:{marker}:{npc.id}'.encode()).digest()
    levels=facts.setdefault('levels',{})
    actual=npc.main_technique_id
    if actual and actual not in levels: levels[actual]=npc.main_technique_level
    pool=research_pool(entity.world,npc.path,npc.realm_index)
    if pool and digest[2]<48 and state.get('research_year')!=period:
        identity=pool[digest[3]%len(pool)];price=offers(entity.world,npc.path)[identity]['price']
        source=f'study:{depot.owner_kind(game,entity)}:{entity.id}'
        if identity not in levels and source in game.economy_v2['accounts'] and balance(game,source)>=price:
            transfer_value(game,source,f'background:{entity.world}',price,'门人从当地书坊研习新功法')
            levels[identity]=1;state['research_year']=period
    if digest[0]<32:
        # Donate only an inheritance this real member already knows.
        for identity in levels:
            if identity not in state['books'] and eligible(entity,identity):
                state['books'].append(identity);note(game,entity,f'{npc.name}献录《{TECHNIQUE_CATALOG[identity].name}》。');break
    if digest[1]>=96: return
    # The persistent cursor visits one book, rather than sorting/scanning a catalog.
    if not state['books']: return
    cursor=facts.get('cursor',0)%len(state['books']);facts['cursor']=cursor+1
    identity=state['books'][cursor]
    if not eligible(entity,identity): return
    t=TECHNIQUE_CATALOG[identity]; offer=offers(entity.world,t.path)[identity]
    if t.path!=npc.path or offer['grade']>npc.realm_index or not can_practice_technique(npc.spirit_root,t.element): return
    level=levels.get(identity,0)
    if level>=9: return
    if level:
        # Member allowances are prepaid from actual upkeep, with one shared purse.
        source=f'study:{depot.owner_kind(game,entity)}:{entity.id}'
        if source not in game.economy_v2['accounts']: return
        price=offer['price']*2**(level-1)
        if balance(game,source)<price: return
        transfer_value(game,source,depot.treasury(game,entity),price,'门人研习绝学缴纳玉简费用')
        organizations.register(game,depot.owner_kind(game,entity),entity.id,entity.world)['income']+=price
    levels[identity]=level+1
    current=TECHNIQUE_CATALOG.get(npc.main_technique_id)
    body=npc.body_training or 0
    native_power=bool(npc.transcendence and npc.transcendence.get('conversion',0)>0)
    if t.category=='spiritual' and body>=t.required_body_training and (not t.requires_immortal_power or native_power) and (not current or t.combat_bonus>=current.combat_bonus):
        npc.main_technique_id=identity;npc.main_technique_level=level+1
    if body>=t.required_body_training and (not t.requires_immortal_power or native_power):
        learned=copy.copy(t);learned.level=level+1
        bonus=max(0.,learned.combat_bonus*technique_scale(learned))
        # One best contribution per category; replacing a book never stacks it.
        bonuses=facts.setdefault('combat_bonuses',{})
        previous=bonuses.get(t.category,0.)
        if bonus>previous:
            npc.family_combat_bonus+=bonus-previous;bonuses[t.category]=bonus
    note(game,entity,f'{npc.name}{"免费参悟" if not level else "付费精研"}《{t.name}》，达到Lv.{level+1}。')
