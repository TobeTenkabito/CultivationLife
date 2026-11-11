"""Base appointment/funding separation, phased relief and fixed-site handover."""
from . import institution_authority as authority,institution_garrisons as troops
from .institution_deliberation import book,ensure
from .institution_ai.rules import record
from .economy.ledger import balance


def configure(scope,funding,appointments):
    if funding not in {'central','local'} or appointments not in {'central','local'}:raise ValueError('供养与任将权限无效')
    if book(scope)['rotation'] and book(scope)['rotation']['stage']=='awaiting':raise ValueError('须先完成本次轮调')
    ensure(scope)['mandate']=dict(funding=funding,appointments=appointments)


def relief(game,scope,outgoing,incoming,issuer,rate):
    prior=book(scope)['rotation']
    if prior and prior['stage']=='awaiting':raise ValueError('已有未完成轮调')
    if outgoing not in {u['person_id'] for u in troops.active(scope)}:raise ValueError('原部将不在驻军名册')
    if len(troops.active(scope))>=6:raise ValueError('须保留一个原驻军名额供接防，不能复制第七人')
    troops.enlist(game,scope,incoming,rate)
    ensure(scope)['rotation']=dict(outgoing=outgoing,incoming=incoming,stage='awaiting',ordered=game.player.age,issuer=issuer)


def finish_relief(game,maps,scope):
    r=book(scope)['rotation']
    if not r or r['stage']!='awaiting':raise ValueError('没有待验收轮调')
    units={u['person_id']:u for u in troops.active(scope)}
    old,new=units.get(r['outgoing']),units.get(r['incoming'])
    if not old or not new or old['phase']!='stationed' or new['phase']!='stationed' or old['destination']!=new['destination']:
        raise ValueError('新旧原部将须实际在同一驻地交接')
    if len(troops.stationed(game,scope,old['destination']))<2:raise ValueError('接防人已离场或失去资格')
    troops.recall(game,maps,scope,[r['outgoing']]);r['stage']='relieved'


def move_ready(game,scope):
    if troops.active(scope):raise ValueError('须先原路撤回驻军，再办理迁署')
    if record(game,scope['id']).get('job'):raise ValueError('须先交接原项目')
    c=scope.get('operations',{}).get('contract')
    if c and c['status']=='active':raise ValueError('须先交接原供货合同')
    if scope['people']:raise ValueError('须先解除原址属员职务；迁署不搬迁人物')
    if book(scope)['cases']:raise ValueError('须先结清议政、债务与盟约责任')
    if scope.get('petitions',{}).get('active'):raise ValueError('须先结清原址地方争议')
    if balance(game,scope['wallet']) or scope.get('garrison') and balance(game,scope['garrison']['wallet']):raise ValueError('须先上缴原公款并完成营务退款')


def relocate(game,scope,city,building_id):
    move_ready(game,scope)
    from ..building_schema import address
    if address(game)!=city['address']:raise ValueError('须本人沿原地图抵达批准的新址')
    if any(s is not scope and s['city_id']==city['id'] for s in authority.records(game).values()):raise ValueError('新址已有另一原机构')
    old=scope['building_id']
    scope.update(city_id=city['id'],location=city['address']['location_id'],building_id=building_id)
    if scope.get('garrison'):scope['garrison']['units']=[]
    ensure(scope)['guard']=None
    authority.log(game,scope,'原址移交完成；原建筑 '+old+' 留在原地，新府署须重新实付营造。')
