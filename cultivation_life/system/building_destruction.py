"""Single destruction authority; original stocks, deposits and rewards never reset."""
import hashlib

from ..building_schema import address
from ..building_rules import config
from ..models import HistoryRecord
from ..rules import max_mp
from . import building_projects as projects
from .building_assets import rows_at


def destroy(game,row,*,source='player'):
    if row['type']=='scenery':raise ValueError('自然景观不可摧毁')
    if row['status']=='destroyed':raise ValueError('建筑已经被摧毁')
    if source=='player':
        if row['address']!=address(game):raise ValueError('必须亲赴建筑所在地')
        reason=projects.demolition_reason(game,row)
        if reason:raise ValueError(reason)
        if not projects.owns(game,row):game.player.mp-=max(1,round(max_mp(game.player)*.25))
    elif source!='war':raise ValueError('未知建筑损毁来源')
    if source=='war' and row['type']=='city':raise ValueError('战事不会自动摧毁城市')
    if row['type']=='industry':
        original=game.economy_v2['estates'][row['source_id']]
        from .economy.economy_trust import release
        release(original)
        original.update(building_status='destroyed',building_destroyed_age=game.player.age,
            enabled=False,entrusted=False,auto_buy=False,auto_sell=False,revision=original['revision']+1)
        from .economy.enterprise_state import log
        log(original,game.player.age,'设施毁坏，已付批次暂停；原仓库、储量、货运与账户保留，养护照常')
    elif row.get('subtype')=='temple':
        site=game.buddhist_state['worlds'][row['address']['world']]['sites'][row['address']['location_id']]
        site.update(temple_ruin_level=site['temple'],temple=0)
    else:
        projects.persist(game,row)['status']='destroyed'
    game.history.append(HistoryRecord('SYS_BUILDING_DESTRUCTION',1,game.player.age,'建筑毁坏',row['id'],source,
        f"{row['name']}已成遗址。没有返还资材或追加人物伤亡。",dict(building_id=row['id'],source=source),['building']))


def rebuild(game,row,temple_action):
    if row['address']!=address(game):raise ValueError('必须亲赴建筑所在地')
    bill=projects.quote(game,'rebuild',row)
    if bill['reason']:raise ValueError(bill['reason'])
    if row.get('subtype')=='temple':
        previous=game.pending_event;game.pending_event=None
        try:temple_action(game,'temple',{})
        finally:game.pending_event=previous
    else:
        projects.pay(game,bill,'原址重建'+row['name'])
        if row['type']=='industry':
            original=game.economy_v2['estates'][row['source_id']]
            if original['job']:
                original['job']['finish']+=max(0,game.player.age-original['building_destroyed_age'])
            original['building_status']='intact';original.pop('building_destroyed_age',None)
            original['revision']+=1
        else:
            original=projects.persist(game,row)
            original['status']='intact'
            if row['type']=='city':original.update(level=1,development=0,features=[],facilities=[])
    game.history.append(HistoryRecord('SYS_BUILDING_REBUILD',1,game.player.age,'原址重建',row['id'],'completed',
        f"{row['name']}在原地重建，旧活动次数与原权属保留。",dict(building_id=row['id'],cost=bill['coins']),['building']))


def war_damage(game,war):
    """One deterministic incident roll per real battle, independent of gameplay RNG."""
    number=int(war.get('battles',0))
    if number<=int(war.get('building_damage_round',0)) or not war.get('location_id'):
        return
    war['building_damage_round']=number
    place=dict(world=war['world'],instance_id=None,location_id=war['location_id'])
    for row in rows_at(game,place):
        if row['type'] in {'city','scenery'} or row['status']=='destroyed':continue
        seed=f"{game.seed}:{war['id']}:{number}:{row['id']}".encode()
        roll=int.from_bytes(hashlib.blake2s(seed,digest_size=8).digest(),'big')/2**64
        if roll<float(config()['war_destruction_chance']):destroy(game,row,source='war')
