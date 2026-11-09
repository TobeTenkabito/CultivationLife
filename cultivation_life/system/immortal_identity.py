"""Three exclusive primary identities projected from original offices and temples."""
from ..models import HistoryRecord
from ..runtime import now_iso
from .court_bureau_rules import HOME,digest
from .earth_temple_rules import reason,ledgers,temple,pending
from .westward_rules import record,enabled

from .immortal_identity_rules import offices,official,primary,public_service,join_reason

def handover_reason(game):
    if any(key.startswith('temple:') and (r.get('job') or r.get('delegate')) for key,r in game.economy_v2.get('institution_agendas',{}).get('scopes',{}).items()):
        return '须先交接驻庙执事与原在办项目'
    b=game.heavenly_court.get('bureaus',{})
    if pending(game):return '须先逐庙完成或退出已承接的庙务、施工与争议'
    if any(j['status']=='active' for j in b.get('jobs',[])) or b.get('review') or any(c['status']=='active' for c in b.get('inquiries',[])):
        return '须先交接全部公务、公物、属员行程和监察案件'
    if game.heavenly_court.get('projects',{}).get('current'):return '须先完成或撤回当前七曜议案'
    if game.heavenly_court.get('open_election'):return '须先答复原七曜选举'
    return ''

def token(game):
    return digest([primary(game),game.player.age,game.player.world,game.player.location_id,
        record(game).get('earth'),game.heavenly_court.get('bureaus'),offices(game),handover_reason(game)])

def command(deps,game,action,target,amount):
    if type(amount) is not int or amount!=1 or target!=token(game):raise ValueError('三途职责已变化，请刷新后办理')
    if blocked:=reason(game,recovery=action=='identity_retire'):raise ValueError(blocked)
    earth=record(game).get('earth',{});main=temple(game,earth.get('temple_id'))
    if action=='identity_register':
        if game.player.location_id!=HOME:raise ValueError('须亲赴玉京登记原主庙')
        if not main or main['owner']!=dict(kind='player',id=game.id):raise ValueError('须已有本人原主庙')
        if earth.get('registration'):raise ValueError('原神位已经登记，不重复登记或刷新香火')
        earth['registration']=dict(temple_id=main['id'],age=game.player.age)
        summary='原主庙神位已登记；不入编、不收香火税、不刷新额度或期限。'
    elif action=='identity_retire':
        if blocked:=handover_reason(game):raise ValueError(blocked)
        mode=primary(game)
        if mode=='free':raise ValueError('当前已为散仙，无须重复交接')
        if mode=='xuan':
            if game.player.location_id!=HOME:raise ValueError('须回玉京交还职司及七曜席位')
            b=game.heavenly_court.get('bureaus',{});old=b.get('office')
            b.update(office=None,staff={},leave=False)
            if old:b.setdefault('heads',{}).pop(old,None)
            for key in offices(game):game.heavenly_court['offices'][key]=None
            game.heavenly_court['pledges']=[r for r in game.heavenly_court.get('pledges',[]) if (game.heavenly_court['offices'].get(r.get('office_id')) or {}).get('holder_id')=='player']
        elif not main or game.player.location_id!=main['address']['location_id']:
            raise ValueError('须亲临原主庙交接主持')
        for s in ledgers(game):s['active']=False
        deps._sync_player_court_identity(game)
        summary='已交接退隐为散仙；原资产、个人成长、功德功勋及期限保留。复任仍须原资格，香火不追发。'
    else:raise ValueError('未知三途事务')
    game.history.append(HistoryRecord('SYS_IMMORTAL_IDENTITY',1,game.player.age,'仙家三途',action,'completed',summary,{},['yaochi','identity']))
    game.updated_at=now_iso();deps.store.save(game);return deps.present(game)

def public(game):
    if game.player.world!='celestial' or game.guixu_state.get('player_session') or not (enabled() or record(game).get('earth') or game.heavenly_court.get('bureaus')):return None
    mode=primary(game);earth=record(game).get('earth',{});main=temple(game,earth.get('temple_id'))
    place=HOME if mode=='xuan' else main['address']['location_id'] if main else None
    return dict(primary=mode,name={'free':'散仙','earth':'地仙','xuan':'玄仙'}[mode],token=token(game),
        office=game.heavenly_court.get('bureaus',{}).get('office'),stars=offices(game),
        registration=earth.get('registration'),
        retire_reason=reason(game,recovery=True) or handover_reason(game) or ('当前已为散仙' if mode=='free' else '须回玉京或原主庙办理交接' if game.player.location_id!=place else ''),
        register_reason=reason(game) or ('须在玉京持本人原主庙登记' if game.player.location_id!=HOME or not main else '已登记原神位' if earth.get('registration') else ''),
        join_reason=join_reason(game))
