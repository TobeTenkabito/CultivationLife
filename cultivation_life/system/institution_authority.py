"""Base institutional appointments and public funds; no DLC-specific rules."""
from .economy.ledger import account, balance, transfer_value
from .institution_ai import rules, runtime


def records(game):
    return game.economy_v2.get('administrations', {})


def effective(game, row, person='player'):
    return (row.get('holder') == person and row.get('status') == 'active'
            and game.player.age < row['expires'] and not held(row,person))


def held(row,person):
    return any(c['subject']==person and c.get('facts',{}).get('suspends_authority')
               for c in row.get('protocols',{}).get('cases',[]))


def responsibilities(game, person):
    """Original roles only; holding an office does not teleport or freeze a person."""
    return [r for r in records(game).values()
            if person in (r['holder'], r['nominee'], r['controller']) or person in r['people']]


def log(game, row, text):
    row['revision'] += 1
    row['history'] = (row['history'] + [dict(year=game.player.age, text=text)])[-20:]


def create(game, *, identity, provider, name, world, location, owner, source, building_id, city_id):
    root = game.economy_v2.setdefault('administrations', {})
    if identity in root or len(root) >= 64:
        raise ValueError('原机构已登记或机构容量已满')
    wallet = 'administration:' + identity
    account(game, wallet)
    row = dict(id=identity, provider=provider, name=name, world=world, location=location,
        owner=dict(owner), source=source, wallet=wallet, building_id=building_id, city_id=city_id,
        holder=None, nominee=None, controller=None, status='vacant', expires=0,
        appointed=0, revision=0, people=[], history=[], funded=0, returned=0)
    root[identity] = row
    return row


def clear_delegation(game, row, *, operations=False):
    contract=row.get('operations',{}).get('contract')
    if operations and contract and contract['status']=='active':
        from .institution_ai.contracts import cancel
        cancel(game,contract)
    agenda = rules.record(game, row['id'])
    if agenda.get('job'):
        runtime.close(game, None, agenda, agenda['job'], 'cancelled', '任职授权交接，原项目余款退回机构。')
    if agenda:
        agenda.update(delegate=None, automatic=False)
        agenda['revision'] += 1


def nominate(game, row, person, term):
    if not isinstance(person, str) or not person or type(term) is not int or term <= 0:
        raise ValueError('任命人选或任期无效')
    if any(held(r,person) for r in records(game).values()):raise ValueError('原未清责任暂停任职授权，须先处理原案')
    if any(r['id'] != row['id'] or person in r['people'] for r in responsibilities(game, person)):
        raise ValueError('此人已有其他地方任职或待交接责任')
    if row['controller']:
        raise ValueError('须先完成前任交接，再办理继任')
    if row['nominee'] == person or effective(game, row, person):
        raise ValueError('已有同一任命，不得重复刷新任期')
    clear_delegation(game, row, operations=True)
    row.update(nominee=person, holder=None, status='appointed', appointed=game.player.age,
               expires=game.player.age + term)
    log(game, row, '任命已登记，须在原址验收接任；期限不因赴任延后。')


def assume(game, row, person, world, location):
    if (row['status'] != 'appointed' or row['nominee'] != person
            or game.player.age >= row['expires']):
        raise ValueError('任命已失效或并非受任人')
    if (world, location) != (row['world'], row['location']):
        raise ValueError('须亲赴原址办理交接')
    row.update(holder=person, controller=person, nominee=None, status='active')
    if 'operations' in row:
        operating=row['operations'];operating['term_baseline']=operating['settlements']+operating['deliveries']
    log(game, row, '原址接任完成；原公款、原设施及历史责任继续保留。')


def revoke(game, row):
    if row['status'] not in {'active', 'appointed'}:
        raise ValueError('没有可撤销的在任授权')
    clear_delegation(game, row, operations=True)
    row.update(holder=None, nominee=None, status='handover' if row['controller'] else 'vacant')
    log(game, row, '法定授权终止，原控制人须办理公款和设施交接。')


def relinquish(game, row, person):
    if row['controller'] != person and row['nominee'] != person:
        raise ValueError('并非原任或待赴任人')
    if any(u['phase'] not in {'home','lost'} for u in row.get('garrison',{}).get('units',[])):
        raise ValueError('原驻军尚未归返，不能提前解除交接责任')
    clear_delegation(game, row, operations=True)
    row.update(holder=None, nominee=None, controller=None, status='vacant', people=[])
    rotation=row.get('protocols',{}).get('rotation')
    if rotation and rotation['stage']=='awaiting':rotation['stage']='cancelled'
    log(game, row, '交回任职和原址控制，公款留在原机构，不转入个人行囊。')


def fund(game, row, source, amount):
    if type(amount) is not int or not 1 <= amount <= 10**15:
        raise ValueError('拨款须为有效的正整数')
    transfer_value(game, source, row['wallet'], amount, '原地方机构实款拨付')
    row['funded'] += amount
    log(game, row, f'原款拨入 {amount:,} 灵石；此款不构成私人产权。')


def return_funds(game, row):
    clear_delegation(game, row, operations=True)
    amount = balance(game, row['wallet'])
    transfer_value(game, row['wallet'], row['source'], amount, '地方机构未耗公款上缴原府库')
    row['returned'] += amount
    log(game, row, f'未耗公款 {amount:,} 灵石交回原上级府库。')
    return amount


def remit(game, row, amount):
    if type(amount) is not int or not 1<=amount<=balance(game,row['wallet']):
        raise ValueError('上缴必须在本府实有公款范围内')
    transfer_value(game,row['wallet'],row['source'],amount,'地方议定公款实缴原上级府库')
    row['returned']+=amount
    log(game,row,f'按原案实缴 {amount:,} 灵石；未动用项目托管及私人库存。')


def set_staff(game, row, person):
    if rules.record(game,row['id']).get('job'):
        raise ValueError('须先交接在办项目，再调整属员')
    if person:
        if any(r['id']!=row['id'] or person in (r['holder'],r['nominee'],r['controller'])
               for r in responsibilities(game,person)):
            raise ValueError('此人已有其他机构任职责任')
        if reason:=rules.person_reason(game,person,row['world'],row['location'],assignment='institution-delegate:'+row['id']):
            raise ValueError(reason)
    clear_delegation(game,row)
    row['people']=[person] if person else []
    log(game,row,'原址属员名册调整，项目实际执行时按预算支付劳务。')


def can_repair(game, building):
    return any(effective(game, r) and r['building_id'] == building['id']
               and r['owner'] == building['owner']
               and building['address']==dict(world=r['world'],location_id=r['location'],instance_id=None)
               for r in records(game).values())


def can_operate_city(game, row, city):
    """A registered local mandate grants management, never ownership."""
    from ..building_schema import address
    return (records(game).get(row.get('id')) is row and effective(game, row)
            and city['id'] == row['city_id'] and city['type'] == 'city'
            and city['owner'] in (row['owner'],dict(kind='background',id=city['id']))
            and city['address'] == address(game)
            and city['address'] == dict(world=row['world'], location_id=row['location'], instance_id=None))


def expire(game, row):
    if row['status'] in {'appointed', 'active'} and game.player.age >= row['expires']:
        revoke(game, row)
