"""World-local voisinage definitions and combat projection, without UI or government actions."""
from ..content_registry import WORLD_SYSTEMS
from .combat.contracts import CapabilitySource


def config():
    return WORLD_SYSTEMS.get('upper_voisinages', {})


def world_config(player):
    return config().get('worlds', {}).get(player.world)


def available(player):
    return bool(world_config(player)) and player.realm_index >= 9


def record(player):
    return player.world_voisinages.get(player.world, {})


def level(player, key):
    return max(0, min(13, int(record(player).get('levels', {}).get(key, 0))))


def definitions(player):
    from .monster_true_form import definition
    from .ghost_soul_form import definition as soul_definition
    rows = [dict(row) for row in (world_config(player) or {}).get('fields', [])]
    dynamic = definition(player)
    if dynamic:
        rows.append(dynamic)
    soul = soul_definition(player)
    if soul:
        rows.append(soul)
    from .spirit_inheritance_rules import definitions as inherited_definitions
    rows.extend(inherited_definitions(player))
    from .spirit_inheritance_rules import valid
    for row in rows:
        data = record(player).get('spirit_bindings', {}).get(row['id'])
        if data and valid(data, player.world):
            row.update(inheritance_template=data['template'], name=row['name'] + '·' + data['source_name'])
    return rows


def project(definition, rank, cap=None):
    from .world_voisinage_projection import project as project_field
    return project_field(definition, rank, cap)


def player_source(player, cap=None):
    from .asura import active as asura_active, source as asura_source
    if asura_active(player):
        return asura_source(player, cap=cap)
    if not available(player):
        return CapabilitySource()
    key = record(player).get('active')
    definition = next((d for d in definitions(player) if d['id'] == key), None)
    rank = level(player, key)
    if not definition or not rank:
        return CapabilitySource()
    return CapabilitySource((project(definition, rank, cap),), {key: rank})
