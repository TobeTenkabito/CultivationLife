"""Actual local engagements and guarded crown transfer for the Asura charter."""
from . import rules
from .. import institution_garrisons as troops, royal_seats
from ..institution_ai.rules import person_reason
from ..asura_court_finance import people
from ..npc_strength import power
from ..combat.npc_battle import resolve_local_engagement
from ...content_registry import WORLD_SYSTEMS
from ...relationship_records import find_person
from ...runtime import decode_rng,encode_rng


def defenders(game,row,location,m):
    ids=[]
    for other in rules.offices(game):
        if other['id']==row['id']:continue
        ids.extend(u['person_id'] for u in troops.stationed(game,other,location))
    if location==m.CAPITAL:
        ids.extend(n.id for n in people(game).values() if n.id!=m.king_id(game)
                   and not person_reason(game,n.id,'asura',location))
    attackers={u['person_id'] for u in troops.active(row)}
    # A single provincial roster is limited to six, not the combined defence.
    # Omitting the seventh person could silently remove the strongest cultivator.
    return [n for i in dict.fromkeys(ids) if i not in attackers
            if (n:=find_person(game,i)) is not None]


def enthrone(game,maps,row,*,m):
    war=m.conflict(row)
    if not m.fighting(row) or not troops.stationed(game,row,m.CAPITAL):raise ValueError('须有未结争位案及实际在场部众')
    claimant=war['claimant']
    if claimant=='player':
        if game.player.location_id!=m.CAPITAL or game.player.world!='asura':raise ValueError('须本人实际抵达王庭')
    elif person_reason(game,claimant,'asura',m.CAPITAL,assignment='garrison:'+row['id']):raise ValueError('举兵者本人尚未抵达王庭')
    royal_seats.transfer(rules.court(game),claimant,war['king'])
    m.close(game,maps,row,'won','王权依原抵抗结果完成唯一交接；地方不自动归顺，债务、公产及人物关系保留。')
    return war['result']


def cooldown(game,row,m):
    previous=m.state(row).get('last_battle',-1)
    if previous>=0 and game.player.age-previous<m.config()['battle_years']:
        raise ValueError('上一轮交战尚需整备，须经过十个实际年')


def skirmish(game,maps,row,location,m):
    units=troops.stationed(game,row,location)
    if not units:raise ValueError('原部众尚未实际抵达，不能以远方兵力攻占')
    if troops.state(row).get('shortfall'):raise ValueError('当前营务欠付，须先整备或撤回')
    enemies=defenders(game,row,location,m)
    engaged={n.id for n in enemies}
    war=m.conflict(row)
    if location in war['controlled']:raise ValueError('此处战果已登记，不能重复刷取')
    result='victory'
    if enemies:
        cooldown(game,row,m)
        rng=decode_rng(game.seed,game.rng_state)
        engagement=resolve_local_engagement([(find_person(game,u['person_id']),power(find_person(game,u['person_id']))) for u in units],
            [(n,power(n)) for n in enemies],WORLD_SYSTEMS['transcendent_combat'],rng,now=game.player.age,
            attacker_objective='repel',defender_objective='repel')
        game.rng_state=encode_rng(rng);result=engagement.outcome
        m.ensure(row)['last_battle']=game.player.age
    if result=='victory':
        for other in rules.offices(game):
            defeated=[u['person_id'] for u in troops.active(other) if u['person_id'] in engaged]
            if other['id']!=row['id'] and defeated:
                troops.recall(game,maps,other,defeated)
                m.authority.log(game,other,'原驻军在实际据点战失利，循原道路撤回，不抹除军饷和人物伤势。')
        war['controlled'].append(location);war['status']='capital' if location==m.CAPITAL else 'contested'
        text='原驻军取得本处守备战果；只在实际驻守时形成控制，不改变建筑产权或自动登位。'
    else:text='原交战未能突破抵抗。伤势、元力消耗保留；可整备、求援或撤军。'
    m.authority.log(game,row,text)
    return text


def npc_claim(game,maps,row,m):
    war=m.conflict(row)
    if war['king']=='player' or m.CAPITAL not in war['controlled']:return
    claimant=find_person(game,war['claimant']);king=find_person(game,war['king'])
    if (not claimant or not king or person_reason(game,claimant.id,'asura',m.CAPITAL,assignment='garrison:'+row['id'])
            or person_reason(game,king.id,'asura',m.CAPITAL)):return
    cooldown(game,row,m)
    rng=decode_rng(game.seed,game.rng_state)
    result=resolve_local_engagement([(claimant,power(claimant))],[(king,power(king))],
        WORLD_SYSTEMS['transcendent_combat'],rng,now=game.player.age,attacker_objective='repel',defender_objective='repel')
    game.rng_state=encode_rng(rng);m.ensure(row)['last_battle']=game.player.age
    if result.outcome=='victory':enthrone(game,maps,row,m=m)
    elif result.outcome=='defeat':m.close(game,maps,row,'defeated','举兵者不敌旧王实际抵抗，原案失败并归返。')


def battle(game,maps,row,operation,combat,*,m):
    war=m.conflict(row)
    if not m.fighting(row):raise ValueError('没有有效的起兵争位案')
    if not m.enabled():raise ValueError('修罗DLC停用，不能发起新交战')
    if war['king']!=m.king_id(game):raise ValueError('王位已变化，原案须收束')
    if operation=='assault':
        if war['claimant']!='player':raise ValueError('只有本方举兵者可以下令攻占')
        if game.player.location_id not in m.sites(game):raise ValueError('须到实际争夺地点指挥')
        return skirmish(game,maps,row,game.player.location_id,m)
    if operation=='claim':
        if war['claimant']!='player' or game.player.location_id!=m.CAPITAL:raise ValueError('须由举兵者亲临王庭争位')
        if m.CAPITAL not in war['controlled'] or not troops.stationed(game,row,m.CAPITAL):raise ValueError('须先解决王庭守备并保有实际驻军')
        target=find_person(game,war['king'])
        if target and target.alive:
            if person_reason(game,target.id,'asura',m.CAPITAL):raise ValueError('旧王尚在别处或无法合法交战，不能凭占城登位')
        else:
            # A vanished king is not an unreviewed automatic win; the original
            # crown must first reconcile its vacancy, invalidating this old case.
            raise ValueError('原王位主体已失效，须先核验新的王位状态')
    else:
        if not rules.king(game) or war['king']!='player':raise ValueError('只有原在位君主可以亲征平叛')
        target=find_person(game,war['claimant'])
        if not target or person_reason(game,target.id,'asura',game.player.location_id,assignment='garrison:'+row['id']):
            raise ValueError('须亲赴原举兵者实际所在地，不能远程讨伐')
        if target.id not in {u['person_id'] for u in troops.stationed(game,row,game.player.location_id)}:
            raise ValueError('原举兵者尚在行军或归返，不能用出发地址冒充实际战场')
    cooldown(game,row,m)
    if combat is None:raise ValueError('缺少原战斗结算服务')
    from ...rules import max_hp
    if game.player.hp<max_hp(game.player)*.25:raise ValueError('伤势过重，须先恢复气血')
    rng=decode_rng(game.seed,game.rng_state)
    result,text=combat(game,dict(npc_id=target.id,faction_id=target.faction_id,target_name=target.name,
        target_power=power(target),target_realm_index=target.realm_index,target_layer=target.layer,
        path=target.path,race=target.race,world=target.world,combat_type='cultivator',objective='repel',
        enemy_objective='repel',exclude_allied_ids=[target.id]),False,rng)
    game.rng_state=encode_rng(rng);m.ensure(row)['last_battle']=game.player.age
    result,text=royal_seats.duel_result(game.last_combat_report or {},result,text)
    if result=='victory':
        if operation=='claim':
            war['defeated']=True;return enthrone(game,maps,row,m=m)+' '+text
        m.close(game,maps,row,'defeated','君主亲征击退举兵者，撤销夺位案并保留原地方待交接责任。')
    elif result=='defeat':
        if operation=='claim':m.close(game,maps,row,'defeated','举兵者不敌旧王，争位失败，原军撤回且公职不恢复。')
        else:
            # Defeating a king away from his capital does not teleport the claimant.
            war['defeated']=True
            if game.player.location_id==m.CAPITAL and troops.stationed(game,row,m.CAPITAL):return enthrone(game,maps,row,m=m)+' '+text
    m.authority.log(game,row,'争位实际斗法：'+result+'；未决战果不转移王位。')
    return text
