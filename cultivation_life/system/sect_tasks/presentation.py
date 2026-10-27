"""Read-only board and public NPC contributions, no finance adoption on GET."""
import copy
from math import ceil
from . import state as s, tasks
from ...content_registry import REALMS, CONTENT_DOCUMENTS
from ...rules import has_item
from ..economy import depot
from ..intrigue.leadership import candidates


def public(game):
    sect=game.sects.get(game.player.faction_id or '')
    if not s.active(game,sect):return None
    board=s.snapshot(game,sect);row=s.record(game,sect);q=s.quota(game,sect)
    stock=depot.find(game,sect)
    goods=s.ordinary(sect.world)
    local=game.player.location_id==s.faction_site(sect,persist=False)['id']
    task_rows=[]
    for task in board['tasks']:
        r=copy.deepcopy(task)
        r['available']=tasks.valid(game,sect,task) and task['issuer']!='player' and q['completions']<1
        if r['available']:
            r['available']=bool(tasks.at_front(game,sect,task) and tasks.opponents(game,sect,task['war_id'])) if r['kind']=='mobilize' else local
            if r['available'] and r['kind']=='material':
                good=goods.get(r['item'])
                r['available']=bool(good and has_item(game.player,good['id'],r['quantity'])
                    and (not stock or depot.occupied(stock)+r['quantity']<=10000))
        if r['kind']=='mobilize':
            r['battle_location']=next((w.get('location_id') for w,_ in tasks.wars(game,sect) if w['id']==r['war_id']),None)
            r['battle_location_name']=next((p['name'] for p in CONTENT_DOCUMENTS['maps.json']['worlds'][sect.world]['locations'] if p['id']==r['battle_location']),'战役已结束')
        task_rows.append(r)
    rights=s.permissions(game,sect)
    return dict(owner_id=sect.id,revision=board['revision'],blocked=s.blocked(game,sect,at_site=False),local=local,
        contribution=game.player.faction_contribution,influence=s.influence(game,sect,'player'),
        can_publish=game.player.realm_index>=board['minimum_realm'] and q['posts']<3,
        minimum_realm=board['minimum_realm'],realms=[dict(id=i,name=r.name) for i,r in enumerate(REALMS)],
        recruitment_open=board['recruitment_open'],permissions=rights,leader=s.leader(game,sect),
        successors=[dict(id=k,name=v) for k,v in candidates(game,dict(kind='sect',id=sect.id,**{k:row[k] for k in ('positions','guests') if k in row}),sect.npcs).items() if k!=s.leader(game,sect)],
        can_dismiss=rights['dismiss'] and bool(board['arrears']) and row.get('unrest',0)>=20 and board.get('dismissed_crisis_year')!=board['salary_year'],
        treasury=row.get('resources',0),unrest=row.get('unrest',0),arrears=board['arrears'],
        salary_year=board['salary_year'],salaries=copy.deepcopy(board['salaries']),dismissals=board['dismissals'],
        minimum_salary=s.minimum(game.player.realm_index,sect.world),limit=s.limit(game),used=q['value'],
        tasks=task_rows,history=copy.deepcopy(board['history']),
        wars=[dict(id=w['id'],name=f'{w.get("attacker_id")} 对 {w.get("defender_id")}') for w,_ in tasks.wars(game,sect)],
        materials=[dict(key=k,**v) for k,v in goods.items() if v['tier']<=game.player.realm_index+1],
        stock=[dict(key=k,name=goods[k]['name'],quantity=n,value=depot.unit_value(game,stock,k),cost=ceil(depot.unit_value(game,stock,k)/10))
               for k,n in (stock or {}).get('stock',{}).items() if n>0 and k in goods and goods[k]['tier']<=game.player.realm_index+1],
        members=[dict(id=k,name=n.name,contribution=s.contribution(game,sect,k),influence=s.influence(game,sect,k)) for k,n in s.members(game,sect).items()])
