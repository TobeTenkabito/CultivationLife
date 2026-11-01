"""Pure item/technique attack qualification, independent of equipment quality."""
from ..content_registry import ITEM_CATALOG


def force_tier(entry):
    if not entry:return 1
    def read(key,default=None):
        return entry.get(key,default) if isinstance(entry,dict) else getattr(entry,key,default)
    identity=read('id','')
    # Old economic bag snapshots must still use their canonical attack tier.
    if isinstance(identity,str) and identity.startswith('econ_'):
        definition=ITEM_CATALOG.get(identity)
        if definition and {'economic_raw','economic_product'} & set(definition.tags):
            entry=definition
    return max(int(read('force_tier',1)),2 if 'immortal_attack' in read('tags',()) or read('requires_immortal_power',False) else 1)
