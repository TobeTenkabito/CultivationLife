"""Per-save authored books; commands use the original inventory and learning ports."""
import copy
import math
import uuid

from .. import content_registry as registry
from ..authored_technique_schema import PREFIX, SLOTS, STATS, EFFECTS, integer, validate_buffs, buff_text, validate_library
from ..models import Technique
from ..rules import acquire_technique, add_technique_copy, technique_manual_item_id, can_player_practice_technique

OWNER = 'official.authored-techniques'


def enabled():
    return any(r.get('id') == OWNER and r.get('status') == 'loaded' for r in registry.EXTENSION_REPORT)


def definitions(game, group=None):
    state = getattr(game, 'authored_techniques', {})
    return state.get(group, {}) if group else {**state.get('inherited', {}), **state.get('own', {})}


def template(game, identity):
    row = definitions(game).get(identity)
    return Technique(**copy.deepcopy(row['technique'])) if row else None


def insight_projection(player):
    claimed = dict(player.creation_insights.get('claimed', {}))
    for t in player.known_techniques:
        if not t.id.startswith(PREFIX):
            claimed[t.id] = max(claimed.get(t.id, 0), 10 * max(1, t.grade)**2 * t.level**2)
    earned = sum(claimed.values())
    spent = player.creation_insights.get('spent', 0)
    return dict(claimed=claimed, earned=earned, spent=spent, available=max(0, earned-spent))


def spend(player, cost):
    facts = insight_projection(player)
    if cost > facts['available']:
        raise ValueError(f"创法点不足：需要{cost}点，现有{facts['available']}点")
    player.creation_insights = dict(claimed=facts['claimed'], spent=facts['spent']+cost)


def quote(player, payload):
    if not isinstance(payload, dict) or set(payload) - {'name', 'grade', 'category', 'element', 'allocations', 'buffs'}:
        raise ValueError('创法参数无效')
    name = payload.get('name', '').strip() if isinstance(payload.get('name'), str) else ''
    if not 2 <= len(name) <= 24 or any(ord(c) < 32 for c in name):
        raise ValueError('功法名须为2–24字')
    grade = integer(payload.get('grade'), 1, 12, '功法境界')
    maximum = max((t.grade for t in player.known_techniques if not t.id.startswith(PREFIX)), default=0)
    if grade > maximum:
        raise ValueError('须先学会相应境界的普通功法')
    category = payload.get('category')
    if category not in {'main', 'support', 'combat', 'body', 'divine_sense', 'transformation'}:
        raise ValueError('请选择功法类型')
    element = payload.get('element', 'neutral')
    if element not in {'neutral', 'metal', 'wood', 'water', 'fire', 'earth', 'wind', 'thunder', 'yin', 'yang'}:
        raise ValueError('功法属性无效')
    allocations = payload.get('allocations')
    if not isinstance(allocations, dict) or set(allocations) != set(STATS):
        raise ValueError('请分配机缘、气血、法力、战力四项点数')
    for value in allocations.values():
        integer(value, 1, 1000000, '属性点数')
    buffs = copy.deepcopy(validate_buffs(payload.get('buffs', [])))
    allowed = {'main', 'support', 'combat'} if category in {'main', 'support', 'combat'} else {{'body':'body','divine_sense':'sense','transformation':'transformation'}[category]}
    if any(b['slot'] not in allowed for b in buffs):
        raise ValueError('效果栏目必须与该类型功法的可装备栏目一致')
    # A transparent point price, not a hidden random roll. Delayed unlocks cost less.
    effects_cost = sum(math.ceil(b['value']*EFFECTS[b['effect']][4]*(10-b['level'])/9 *
                      (1 if b['condition']=='always' else .75 if b['condition']=='from_round' else .5)) for b in buffs)
    cost = sum(allocations.values()) + effects_cost * grade**2
    if cost > 10**9:
        raise ValueError('创法投入超过上限')
    baseline = next((t for t in registry.TECHNIQUE_CATALOG.values() if t.grade == grade and t.element == 'neutral'
                     and t.growth_preference == category and t.id.startswith('TECH_OPEN_')), None)
    if baseline is None:
        baseline = next(t for t in registry.TECHNIQUE_CATALOG.values() if t.grade == grade and t.id.startswith('TECH_OPEN_'))
    values = {key: round(max(.1, float(getattr(baseline, key))) * allocations[key] / (10*grade**2), 4) for key in STATS}
    book = Technique(id=PREFIX+'preview', name=name, path=player.path, element=element, grade=grade,
        category='spiritual' if category in {'main','support','combat'} else category,
        growth_preference=category, authored_buffs=buffs, **values)
    if category == 'body':
        book.body_breakthrough_bonus = min(.3, allocations['opportunity_bonus'] / (1000*grade**2))
        book.body_bonus_max_layer = min(100, grade*12)
    if category == 'divine_sense':
        book.divine_sense_bonus = values['mp_bonus'] / 10
    if category == 'transformation':
        book.transformation_capacity = min(9, max(1, allocations['mp_bonus']//(10*grade**2)))
        book.transformation_space = book.transformation_capacity
    from dataclasses import asdict
    return dict(technique=asdict(book), cost=cost, attribute_cost=sum(allocations.values()), buff_cost=effects_cost*grade**2,
                allocations=copy.deepcopy(allocations), buffs=[buff_text(b) for b in buffs])


def require(game):
    if not enabled():
        raise ValueError('请启用《著经立道》DLC')
    if not game.player.alive or game.pending_event or game.active_trial or game.player.imprisonment or game.player.ghost_captor:
        raise ValueError('请先结束当前事件、战斗或拘禁状态')


def create(game, payload, revision):
    require(game)
    if type(revision) is not int or revision != game.authored_techniques.get('revision', 0):
        raise ValueError('著经记录已更新，请刷新后重试')
    row = quote(game.player, payload)
    if len(definitions(game, 'own')) >= 24:
        raise ValueError('本世至多创作二十四部功法')
    if any(t.name == row['technique']['name'] for t in registry.TECHNIQUE_CATALOG.values()) or any(r['technique']['name']==row['technique']['name'] for r in definitions(game).values()):
        raise ValueError('该功法名已存在，请另拟书名')
    spend(game.player, row['cost'])
    identity = PREFIX+uuid.uuid4().hex
    row['technique']['id'] = identity
    row.update(author=game.player.name, origin=game.id)
    game.authored_techniques.setdefault('own', {})[identity] = row
    game.authored_techniques['revision'] = revision+1
    acquire_technique(game.player, Technique(**copy.deepcopy(row['technique'])))
    from ..models import HistoryRecord
    game.history.append(HistoryRecord('SYS_AUTHORED_CREATE',1,game.player.age,'著经立道',identity,'created',f"你以{row['cost']}创法点著成《{row['technique']['name']}》。",{'points':-row['cost']},['system','authored']))
    return identity


def manual_price(row, level):
    return max(1, math.ceil(row['cost']/2)) * 2**(level-1)


def buy_manual(game, identity, level, revision):
    require(game)
    if type(revision) is not int or revision != game.authored_techniques.get('revision', 0):
        raise ValueError('著经记录已更新，请刷新后重试')
    row = definitions(game, 'own').get(identity)
    if row is None:
        raise ValueError('这里只能刻录本世自创功法；前世传承请前往黑市或交易会')
    integer(level, 1, 8, '玉简等级')
    spend(game.player, manual_price(row, level))
    book = template(game, identity)
    add_technique_copy(game.player, book, level=level)
    game.authored_techniques['revision'] = revision+1


def inherit(source):
    if not enabled():
        raise ValueError('请启用《著经立道》DLC')
    own = copy.deepcopy(definitions(source, 'own'))
    if not own:
        raise ValueError('所选周目没有本世自创功法')
    # Deliberately copy only this source's authorship, never its inherited shelf.
    return validate_library(dict(inherited=own, source_id=source.id, source_name=source.player.name, revision=0))


def local_books(game):
    if not enabled():
        return {}
    tier = int(registry.WORLD_SYSTEMS['world_profiles'].get(game.player.world, {}).get('tier', 0))
    cap = {1:5,2:8,3:12}.get(tier, 0)
    return {k:r for k,r in definitions(game, 'inherited').items() if r['technique']['grade'] <= cap}


def grant_market(game, identity):
    if identity not in local_books(game):
        raise ValueError('该前世传承不属于当前世界流通范围')
    acquire_technique(game.player, template(game, identity))


def market_offers(game, prefix):
    result=[]
    for key,row in local_books(game).items():
        t=row['technique']; grade=t['grade']
        result.append(dict(id=prefix+key, kind='authored_technique', content_id=key, name=t['name'],
            description='前世传承 · '+ ' '.join(buff_text(b) for b in t['authored_buffs']), tier=grade,
            tier_name=registry.REALMS[grade].name, price=max(100, round(100*10**((grade-1)*.8)*(1+row['cost']/(100*grade**2)))),
            sold=False,bargained=False))
    return result


def public(game):
    facts=insight_projection(game.player)
    known={t.id:t.level for t in game.player.known_techniques}
    can_operate=bool(game.player.alive and not (game.pending_event or game.active_trial or game.player.imprisonment or game.player.ghost_captor))
    manuals={i.id:i.quantity for i in game.player.inventory if i.technique_id}
    return dict(available=enabled(), can_operate=can_operate, revision=game.authored_techniques.get('revision',0),
        points={k:v for k,v in facts.items() if k!='claimed'}, source_name=game.authored_techniques.get('source_name'),
        max_grade=max((t.grade for t in game.player.known_techniques if not t.id.startswith(PREFIX)), default=0),
        slots=SLOTS, stats=STATS, effects={k:dict(name=v[0], maximum=v[3]) for k,v in EFFECTS.items()},
        books=[dict(id=k,name=r['technique']['name'],grade=r['technique']['grade'],author=r.get('author',''),
                    own=k in definitions(game,'own'),level=known.get(k,0),cost=r['cost'],
                    manual_cost=manual_price(r,min(8,known.get(k,1) or 1)),
                    can_upgrade=can_operate and 0<known.get(k,0)<9 and manuals.get(technique_manual_item_id(k,known.get(k,1) or 1),0)>0,
                    buffs=[buff_text(b) for b in r['technique']['authored_buffs']]) for k,r in definitions(game).items()])


def combat_rules(game, owner, *, player=False):
    if not enabled():
        return ()
    from .npc_techniques import equipped
    if player:
        slots=[('main',owner.technique),('support',owner.support_technique),('body',owner.body_technique),
               ('sense',owner.divine_sense_technique),('transformation',owner.transformation_technique),
               *(('combat',t) for t in owner.combat_techniques)]
    else:
        slots=equipped(game,owner)
    rules=[]
    seen=set()
    for slot,t in slots:
        if not t or not t.active_in(owner.world if not isinstance(owner,dict) else owner.get('world','')):
            continue
        if player:
            from ..rules import combat_requirement_met, qi_levels
            if not can_player_practice_technique(owner,t) or (t.requires_immortal_power and not owner.immortal_power_converted) or owner.body_training<t.required_body_training:
                continue
            if slot=='combat' and not combat_requirement_met(t.combat_requirements,qi_levels(owner)):
                continue
        for i,b in enumerate(t.authored_buffs):
            if b['slot']!=slot or t.level<b['level'] or (t.id,i) in seen:
                continue
            seen.add((t.id,i))
            _,trigger,channel,_,_=EFFECTS[b['effect']]
            value=b['value']/100 * (-1 if b['effect']=='upkeep' else 1)
            action=dict(op='adjust',stat='state',value=value) if b['effect']=='restore' else dict(op='modify',channel=channel,value=value)
            guards=[dict(fact='self.restricted_technique',op='eq',value=False)]
            if slot=='support': guards.append(dict(fact='self.restricted_support',op='eq',value=False))
            rule=dict(schema_version=3,id=f'buff-{i}',source_id=t.id,name=buff_text(b),trigger=trigger,actions=[action],when={'all':guards})
            if b['condition']!='always':
                rule['schedule']=dict(start=b['round'])
                if b['condition']=='at_round': rule['schedule']['end']=b['round']
            rules.append(rule)
    return tuple(rules)
