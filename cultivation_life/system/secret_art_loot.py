"""One probabilistic material from a real kill's actual innate root."""
from ..content_registry import ContentRegistry, ROOT_DEFINITIONS, ITEM_CATALOG
from ..rules import root_elements, add_item
from ..secret_art_content import AFFINITIES, core_id, soul_id
from ..relationship_records import find_person


def grant(game, source, rng, kind):
    if kind not in {'core', 'soul'}:
        raise ValueError('未知秘术材料种类')
    person = find_person(game, str(source.get('npc_id') or ''), include_inactive=True)
    root = person.spirit_root if person else source.get('spirit_root')
    rank = int(person.realm_index if person else source.get('realm_index', source.get('target_realm_index', 0)))
    if root not in ROOT_DEFINITIONS or not 1 <= rank <= 12:
        return ''
    attributes = [a for a in root_elements(root) if a in AFFINITIES]
    if not attributes or rng.random() >= ContentRegistry.loaded_documents['secret_arts.json'][kind + '_drop_chance']:
        return ''
    affinity = rng.choice(attributes)
    identity = (core_id if kind == 'core' else soul_id)(affinity, rank)
    add_item(game.player, identity)
    return f" 取得{ITEM_CATALOG[identity].name}一份。"
