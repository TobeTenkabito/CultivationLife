"""Read-only original identities and explicit nonliving asset appearances."""
from hashlib import sha256
from ..combat.actor_state import read

FIELDS=('id','name','race','gender','path','age','realm_index','host_body','possession',
        'transformed','spirit_state','ghost_host_body','ghost_attachment','lineage_race',
        'transformation_loadouts','transformation_technique')


def portrait(target,facts):
    if target.kind=='puppet' and facts.get('type') in ('mechanical','corpse'):
        kind=facts['type']
        from ...puppet_content import FORMS
        if kind=='mechanical' and facts.get('form','humanoid') not in FORMS:return None
        gender=read(target.person,'gender',facts.get('gender')) if target.person else facts.get('gender')
        gender=gender if gender in ('male','female') else ('male','female')[sha256(target.identity.encode()).digest()[0]%2]
        race=read(target.person,'race',facts.get('race')) if target.person else facts.get('race')
        if kind=='corpse' and race not in (None,'human'):return None
        return dict(id=target.identity,name=facts.get('name','傀儡'),asset_kind=kind,gender=gender,
            form=facts.get('form','humanoid'),realm_index=facts.get('realm_index'),realm_name=facts.get('realm_name'))
    original=target.person if target.kind in ('prisoner','puppet') and target.person else facts
    row={k:read(original,k) for k in FIELDS}
    if (row.get('spirit_state') or {}).get('mode')=='wandering':return None
    if target.kind in ('prisoner','puppet'):row['restraint']=True;row['status']='受禁控制中'
    return row
