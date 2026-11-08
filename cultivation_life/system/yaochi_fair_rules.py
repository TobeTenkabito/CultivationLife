"""Local fair contracts, original people and a fixed celestial calendar."""
from ..npc_custody import is_free
from ..relationship_records import find_person
from ..spatial_people import instance_of
from ..person_assignments import research_assignment
from .faction_geography import person_site
from .westward_rules import record
from .yaochi_rules import config

NAMES={'duel':'同境论法','guard':'护阵演武','supply':'资材会办'}

def state(game):return record(game).get('fair',{})
def entries(game):return state(game).get('entries',[])
def active(game):return next((r for r in entries(game) if r['status']=='active'),None)
def cycle(game):return game.player.age//500

def reason(game,recovery=False):
    from .yaochi_westward import reason as local_reason
    from .earth_temple_rules import pending
    blocked=local_reason(game,cancelling=recovery)
    if blocked:return blocked
    if not recovery and (record(game).get('project') or pending(game) or game.yaochi_state.get('job')):
        return '请先结清专修、庙务或瑶池委托，再参会'
    return ''

def person_reason(game,npc,entry=None):
    if not npc or not is_free(npc) or npc.world!='celestial' or instance_of(game,npc.id):return '原参会人已失效或不在仙界普通地点'
    if person_site(game,npc)!=config()['location_id']:return '须与原参会人在瑶池当面办理'
    if npc.id in game.intrigue_state.get('npc_prisons',{}):return '原人物受机构拘管'
    if npc.id in game.heavenly_court.get('wanted_ids',[]):return '通缉人物不能报名仙会'
    if any((r.get('npc_id') or r.get('id'))==npc.id for r in game.player.party):return '须先解除同行'
    held=research_assignment(game,npc.id)
    if held and (not entry or held['id']!=entry['id']):return '原人物已有其他事务'
    return ''

def people(game):
    ids=set(game.world_npcs)|set(game.notable_npcs)|set(game.heavenly_court.get('officials',{}))
    return [n for key in sorted(ids) if (n:=find_person(game,key)) and not person_reason(game,n)]

def work_reason(game):
    if blocked:=reason(game):return blocked
    row=active(game)
    if not row:return '没有已报名的在办赛事'
    if game.player.age>row['deadline'] or cycle(game)!=row['cycle']:return '本项会期已截止，请办理退赛'
    if game.player.realm_index!=row['realm']:return '境界分组已变化，请退赛；本届不重新报名'
    if row.get('opponent'):
        npc=find_person(game,row['opponent'])
        if blocked:=person_reason(game,npc,row):return blocked
        if npc.realm_index!=row['realm']:return '对手境界已变化，不能沿旧分组交战'
    return ''
