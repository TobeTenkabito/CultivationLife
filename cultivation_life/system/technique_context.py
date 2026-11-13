"""Read-only original body and maintained form facts for combat manuals."""
from .combat.actor_state import read


def context(owner):
    from ..content_registry import TRANSFORMATION_CATALOG, TECHNIQUE_CATALOG
    from ..models import Technique
    from .transformation_system import transformation_technique_limits, compatible_active_forms
    equipped = read(owner, 'transformation_technique')
    identity = read(equipped, 'id') if equipped else (read(owner, 'technique_slots', {}) or {}).get('transformation')
    equipped=Technique(**equipped) if isinstance(equipped,dict) else equipped or TECHNIQUE_CATALOG.get(identity)
    capacity,space=transformation_technique_limits(equipped) if equipped else (0,0)
    loadout = (read(owner, 'transformation_loadouts', {}) or {}).get(identity, {})
    mastery = read(owner, 'transformation_mastery', {}) or {}
    stored=[k for k in loadout.get('stored',[]) if k in TRANSFORMATION_CATALOG and mastery.get(k,{}).get('purity',0)>0][:capacity]
    forms=compatible_active_forms([k for k in loadout.get('active',[]) if k in stored],space)
    return dict(form='|'.join(forms) if read(owner, 'path') != 'monster' else '',
                bodiless=(read(owner, 'spirit_state', {}) or {}).get('mode') == 'wandering',
                corpse=read(owner, 'kind') == 'corpse')
