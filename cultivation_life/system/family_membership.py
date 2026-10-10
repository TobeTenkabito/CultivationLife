"""Adopt the original clan, keep its finances and resolve true lineage extinction."""
import copy
from ..models import HistoryRecord
from ..content_registry import WORLD_SYSTEMS
from ..npc_custody import is_free
from .faction_geography import faction_site, require_faction_admission
from .economy import organization_accounts as finance
from .economy.ledger import balance


def player_kin(game, family):
    if family is not game.family: return False
    if family.founded_by_player and family.founder_player_id==game.id: return True
    membership=game.family_state.get('membership')
    return bool(membership.get('kin')) if membership else True


def initialize_line(family):
    if family.kind!='family': return
    from .organization_heritage import ensure
    ensure(family)
    for npc in family.npcs:
        if 'kin' not in npc.family_traits:
            npc.family_traits['kin']=bool(npc.id==family.founder_npc_id or npc.title in {'始祖','族长','族人','嫡系后人','族老'})


def wage(world,rank):
    return (20+max(1,rank)**2*4)*WORLD_SYSTEMS['world_profiles'][world]['tier']


def adopt(game,identity):
    if game.family and not game.family.extinct: raise ValueError('已有家族归属，不能重复加入')
    family=game.sects.get(identity)
    if not family or family.extinct or family.kind!='family' or family.world!=game.player.world:
        raise ValueError('请选择本界存续家族')
    require_faction_admission(family,game.player)
    if faction_site(family)['id']!=game.player.location_id: raise ValueError('请亲赴该家族驻地申请')
    if not any(is_free(n) and n.world==family.world for n in family.npcs): raise ValueError('家族暂无可受理申请的在世成员')
    if game.player.hostility.get(f'sect:{identity}',0)>=100: raise ValueError('该家族与你敌对，无法接纳申请')
    old=finance.register(game,'sect',identity,family.world)
    if balance(game,finance.key('sect',identity)) < wage(family.world,game.player.realm_index)*3:
        raise ValueError('家族府库不足以承担三年外姓供养，暂不接纳申请')
    initialize_line(family)
    factions=game.intrigue_state['factions']
    if f'family:{identity}' in factions or finance.key('family',identity) in game.economy_v2['organizations'] or f'study:family:{identity}' in game.economy_v2['accounts']:
        raise ValueError('家族财务归属冲突，请先核查原记录')
    # Relabel the same accounts and assets, never copy the treasury or inhabitants.
    record=factions.pop(f'sect:{identity}');record['kind']='family';factions[f'family:{identity}']=record
    record['positions']={};record['positions_initialized']=False
    game.economy_v2['organizations'].pop(finance.key('sect',identity))
    old['kind']='family';game.economy_v2['organizations'][finance.key('family',identity)]=old
    game.economy_v2.setdefault('organization_aliases',{})[finance.key('sect',identity)]=finance.key('family',identity)
    for row in game.economy_v2.get('depots',{}).values():
        if row['owner']==identity: row['kind']='family'
    for row in game.economy_v2.get('estates',{}).values():
        if row['owner_kind']=='sect' and row['owner_id']==identity: row['owner_kind']='family'
    for region in game.economy_v2.get('transport',{}).get('worlds',{}).values():
        for row in region['fleets'].values():
            if row.get('owner_kind')=='sect' and row.get('owner_id')==identity: row['owner_kind']='family'
    accounts=game.economy_v2['accounts']
    source=f'study:sect:{identity}'
    if source in accounts: accounts[f'study:family:{identity}']=accounts.pop(source)
    game.sects.pop(identity);game.family=family
    if game.player.faction_id==identity:
        game.player.faction_id=None;game.player.faction_join_age=None;game.player.faction_contribution=0
    game.family_state=dict(membership=dict(kin=False,joined_age=game.player.age),finance_year=game.player.age,
                           reproduction_enabled=False)
    return f'你作为外姓修士加入{family.name}，按实际年份领取府库支付的供养；尚未取得本家血缘身份。'


def resolve_line(game,family):
    if family.kind!='family' or family.extinct: return
    initialize_line(family)
    # Blood relatives remain relatives when traveling or captive; absence is not death.
    if family is game.family and player_kin(game,family) and game.player.alive: return
    if any(n.alive and n.family_traits.get('kin') for n in family.npcs): return
    if family is game.family and player_kin(game,family) and any(c.get('alive',True) and not c.get('family_traits',{}).get('expelled') for c in game.player.offspring): return
    candidates=[(n.realm_index,n.layer,n.id,n) for n in family.npcs if n.alive and not n.family_traits.get('expelled')]
    if family is game.family and game.player.alive:
        p=game.player; rank=(p.cultivation_suppression or p.sealed_cultivation or {})
        candidates.append((rank.get('realm_index',p.realm_index),rank.get('layer',p.layer),'player',None))
    if not candidates: return
    winner=max(candidates,key=lambda row:(row[0],row[1],row[2]))
    npc=winner[3]
    if npc:
        npc.family_traits['kin']=True;name=npc.name
    else:
        game.family_state.setdefault('membership',{})['kin']=True;name=game.player.name
    # Existing descendants of the successor become the new bloodline too.
    descendants={winner[2]}
    changed=True
    while changed:
        changed=False
        for row in family.npcs:
            if row.id not in descendants and descendants.intersection(row.family_traits.get('parents',())):
                descendants.add(row.id);row.family_traits['kin']=True;changed=True
    state=family.heritage
    state['line_successor']=winner[2]
    state['rename_available']=True
    kind='family' if family is game.family else 'sect'
    record=finance.faction_record(game,kind,family.id)
    record['controller_id']=winner[2]
    record.setdefault('positions',{})['family_head' if kind=='family' else 'leader']=winner[2]
    game.history.append(HistoryRecord('SYS_FAMILY_LINE_SUCCESSION',1,game.player.age,'外姓承宗',family.id,'succeeded',
        f'{family.name}原本家血缘已绝，由修为最强的外姓修士{name}承为本家，获得一次更名资格。',
        {'successor':winner[2]},['family','succession',f'world:{family.world}']))
    if npc:
        # NPC rulers exercise their one rename during the same authoritative transition.
        family.name=f'{npc.name[:1]}氏仙族';state['rename_available']=False


def rename(game,name):
    family=game.family
    if not family or family.extinct or family.world!=game.player.world: raise ValueError('须身在本族所在界面')
    if family.heritage.get('line_successor')!='player' or not family.heritage.get('rename_available'):
        raise ValueError('只有承宗成为本家的玩家拥有一次更名资格')
    clean=name.strip()
    if not clean or len(clean)>18: raise ValueError('家族名号须为1至18字')
    if any(s.id!=family.id and not s.extinct and s.name==clean for s in game.sects.values()): raise ValueError('该家族名号已被使用')
    old=family.name;family.name=clean;family.heritage['rename_available']=False
    return f'{old}更名为{clean}，族籍、府库、驻地与传承仍由原家族继承。'
