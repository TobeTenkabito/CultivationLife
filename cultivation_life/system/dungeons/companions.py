"""Carry local, authoritative outside companions into the expedition roster."""
import copy
from ...relationship_records import find_person
from ...content_registry import FACTION_DEFINITIONS
from .people import available


def carry(game,site,log):
    for ref in game.player.party:
        identity=ref['id'];npc=find_person(game,identity)
        if not npc:continue
        if not available(game,site,{'npc_id':identity}):
            log(site,npc.name+'未在入口会合，此行留在队伍之外。');continue
        existing=next((r for r in site['roles'].values() if r['npc_id']==identity),None)
        role=existing or copy.deepcopy(next(iter(site['roles'].values())))
        role.update(id=existing['id'] if existing else identity,npc_id=identity,
            name=npc.name,sect_id=npc.faction_id,
            sect_name=game.sects[npc.faction_id].name if npc.faction_id in game.sects else FACTION_DEFINITIONS.get(npc.faction_id,{}).get('name','散修'),
            realm=npc.realm_index,layer=npc.layer,true_realm=npc.realm_index,path=npc.path,
            purpose='escort',desire=30,resolve=30,preparation=20,trust=max(0,min(100,npc.affinity or 0)),caution=60,
            existing=True,state='joined',known=True,clues=[],target='treasure',
            story='与你一同从外界入境',power_factor=npc.combat_factor,joined_step=site['step'],left_step=None,
            revealed=False,materialized=True,ledger={'outside_party':True},offer_step=len(site['nodes'])+1)
        if not existing and len(site['roles'])>=34:raise ValueError('此行名册已满')
        site['roles'][role['id']]=role
        if 'space' in site:site['space']['positions'][role['id']]=site['step']
        if role['id'] not in site['party']:site['party'].append(role['id'])
        log(site,npc.name+'随你一同进入副本。',actors=[role['id']])


def separate(game,role):
    if role['ledger'].get('outside_party'):
        game.player.party[:]=[r for r in game.player.party if r['id']!=role['npc_id']]
