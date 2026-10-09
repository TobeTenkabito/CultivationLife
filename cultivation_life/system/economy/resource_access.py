"""Fixed-site geological/ecological rights; no mirror resource inventories."""
import hashlib
from ...content_registry import WORLD_SYSTEMS
from ...economy_content import specification, ROLES, material_id


def site_profile(world, location, kind):
    cap={1:5,2:8,3:12}[WORLD_SYSTEMS['world_profiles'][world]['tier']]
    seed=int.from_bytes(hashlib.blake2s(f'{world}:{location}:{kind}'.encode(),digest_size=4).digest(),'big')
    grade=1+seed%cap
    family=dict(mine='ore',farm='herb',hunt='core').get(kind)
    if not family:return ()
    roles=tuple(r for r in ROLES if r.startswith(family+'_'))
    start=(seed//cap)%3
    return tuple(material_id(world,grade,roles[(start+i)%3]) for i in range(2))


def permits(row, recipe):
    spec=specification(recipe['output'])
    if not spec or not spec['raw']:return True
    return recipe['output'] in site_profile(row['world'],row['location'],row['kind'])


def public_allowance(game,market,item):
    """Unowned regional capacity only; counters count completed extraction."""
    spec=specification(item)
    if not spec or not spec['raw']:return None
    kind=dict(ore='mine',herb='farm',core='hunt')[spec['role'].split('_')[0]]
    title=game.economy_v2.get('estates',{}).get(f'{market["id"]}:{kind}')
    private=bool(title and title['owner_kind']!='background' and item in site_profile(market['world'],market['location'],kind))
    record=market.get('resource_use')
    if not record or record['year']!=game.player.age:
        record=dict(year=game.player.age,years=max(1,game.player.age-market['last_year']),items={})
    ceiling=market['commodities'][item]['initial_target']*.10*record['years']*(.65 if private else 1.)
    return max(0,int(ceiling)-record['items'].get(item,0))


def record_extraction(game,market,item,quantity):
    spec=specification(item)
    if spec and spec['raw']:
        record=market.get('resource_use')
        if not record or record['year']!=game.player.age:
            market['resource_use']=dict(year=game.player.age,years=max(1,game.player.age-market['last_year']),items={})
        rows=market['resource_use']['items']
        rows[item]=rows.get(item,0)+quantity
