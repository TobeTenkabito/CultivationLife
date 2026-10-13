"""Pure projection of fixed transmission-array ownership."""
import hashlib
from ..content_registry import WORLD_SYSTEMS
from .territory.rules import enabled

def arrays(game,maps,world=None):
    world=world or game.player.world
    factions=sorted((s for s in game.sects.values() if s.world==world and not s.extinct and s.id not in {'heavenly_court','yaochi'}),key=lambda s:s.id)
    registered=game.economy_v2.get('organization_sites',{}).get('initial_arrays',{})
    adopted=any(key.startswith(world+':') for key in registered)
    result={}
    for location in maps.worlds[world]['locations']:
        original=registered.get(f'{world}:{location["id"]}')
        # Once adopted, these real facilities remain at their saved addresses.
        # A new-game content layout neither moves them nor gifts new sites.
        if not original and (adopted or not location.get('teleport_array')):continue
        seed=int.from_bytes(hashlib.blake2s((world+location['id']).encode(),digest_size=4).digest(),'big')
        owner=factions[seed%len(factions)] if factions else None
        if original and game.economy_v2.get('organization_sites',{}).get('retired_arrays',{}).get(f'{world}:{location["id"]}:{original}'):continue
        if original:
            owner=game.sects.get(original)
            if owner and (owner.extinct or owner.world!=world):owner=None
        institution={'jade_capital':'heavenly_court','expanse_celestial_8':'yaochi'}.get(location['id']) if world=='celestial' else None
        if institution in game.sects and not game.sects[institution].extinct:owner=game.sects[institution]
        if enabled() and owner and game.intrigue_state.get('territory',{}).get('suppressed_arrays',{}).get(f'{world}:{location["id"]}:{owner.id}'):continue
        result[location['id']]=dict(id=location['id'],name=location['name'],owner_id=owner.id if owner else world+':array-keepers',owner_name=owner.name if owner else WORLD_SYSTEMS['world_names'][world]+'守阵盟')
    for built in game.economy_v2.get('teleport_arrays',{}).values():
        if built['world']!=world:continue
        owner=game.family if game.family and game.family.id==built['owner_id'] else game.sects.get(built['owner_id'])
        if owner and not owner.extinct and owner.world==world and built['location'] not in result:
            site=maps.location(world,built['location'])
            if site:result[built['location']]=dict(id=built['location'],name=site['name'],owner_id=owner.id,owner_name=owner.name)
    return result
