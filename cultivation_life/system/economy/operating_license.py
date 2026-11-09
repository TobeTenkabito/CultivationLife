"""A revocable operator reference; ownership, stock and batches stay on the estate."""
from ...content_registry import WORLD_SYSTEMS
from ...relationship_records import find_person
from ...npc_custody import is_free
from ...spatial_people import instance_of

def allowed(game,row):
    lease=row.get('operating_lease')
    return bool(lease and lease['operator']==game.id and row['owner_kind']=='yaochi' and row['owner_id']=='yaochi')

def production_reason(game,row):
    if not row.get('operating_lease'):return ''
    if not allowed(game,row) and not npc_allowed(game,row):return '原经营许可已失效'
    if row.get('building_status')=='destroyed':return '仙圃设施已损毁，须先自费原址修复'
    if not WORLD_SYSTEMS.get('yaochi_westward',{}).get('enabled'):return '仙圃扩展停用，停止新投产；已付批次保留'
    if game.player.age>=row['operating_lease']['until']:return '仙圃经营期已满，请结清在制、库存与欠费后交接'
    return ''

def steward_reason(game,row):
    lease=row.get('operating_lease',{});npc=find_person(game,lease.get('steward'))
    from ..faction_geography import person_site
    if not npc or not is_free(npc) or npc.world!=row['world'] or person_site(game,npc)!=row['location'] or instance_of(game,npc.id):return '原协作人物已失效或离场，合作经营暂停'
    if npc.id in game.intrigue_state.get('npc_prisons',{}):return '原协作人物受机构拘管'
    return ''

def annual(game,row,years):
    if not allowed(game,row) and row.get('operating_lease',{}).get('operator_kind')!='npc':return
    lease=row['operating_lease']
    if production_reason(game,row):row.update(enabled=False,auto_buy=False,auto_sell=False,entrusted=False)
    if lease.get('steward'):
        from .ledger import balance,transfer_value
        due=min(years,max(0,lease['until']-(game.player.age-years)))*100
        if steward_reason(game,row) or row.get('building_status')=='destroyed' or balance(game,lease['wallet'])<due:
            row.update(enabled=False,auto_buy=False,auto_sell=False,entrusted=False)
        elif due:
            transfer_value(game,lease['wallet'],f"background:{row['world']}",due,'仙圃原协作者实际维护工钱')
            row['expense']+=due;lease['wages']+=due

def npc_allowed(game,row):
    lease=row.get('operating_lease',{})
    if lease.get('operator_kind')!='npc' or row['owner_kind']!='yaochi':return False
    source=game.economy_v2.get('organizations',{}).get(lease.get('source'))
    if not source:return False
    entity=game.family if source['kind']=='family' else game.sects.get(source['identity'])
    if not entity or entity.extinct or not any(n.id==lease['operator'] for n in entity.npcs):return False
    from ..institution_ai.rules import person_reason
    return not person_reason(game,lease['operator'],row['world'],row['location'],assignment=row['id'])
