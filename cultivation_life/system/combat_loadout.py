"""Content-to-capability boundary. No item lookup inside combat rounds.

NPC treasure is deliberately never inspected here. Empty/unresolved slots do
not invent equipment, and a combat snapshot is not another ownership ledger.
"""
from dataclasses import replace

from ..content_registry import ITEM_CATALOG, TECHNIQUE_CATALOG
from .combat.contracts import CapabilitySource, Intervention
from .combat.npc_lifecycle import read
from .cultivation_ranks import npc_golden_light


def _tier(entry):
    if not entry:
        return 1
    # Existing economic bag copies can retain the pre-2.7.2 commercial grade
    # in force_tier. Resolve their qualification from the authoritative catalog
    # once at the battle boundary; never rewrite inventories or scan them yearly.
    identity = read(entry, 'id', '')
    if isinstance(identity, str) and identity.startswith('econ_'):
        definition = ITEM_CATALOG.get(identity)
        if definition and ('economic_raw' in definition.tags or 'economic_product' in definition.tags):
            entry = definition
    return max(int(read(entry, 'force_tier', 1)),
               2 if 'immortal_attack' in read(entry, 'tags', ()) or read(entry, 'requires_immortal_power', False) else 1)


def _responses(entry, source):
    return tuple(Intervention(**{**row, 'source': source}) for row in read(entry, 'combat_interventions', ())) if entry else ()


def public_loadout(game, npc):
    from .npc_techniques import public, resolve
    key = read(npc, 'main_technique_id')
    technique = resolve(game, key)
    if technique is None and key:
        definition = game.doctrine_state.get('definitions', {}).get(key.split(':manual:')[0], {})
        technique = next((t for t in definition.get('manuals', ()) if t['id'] == key), None)
    artifact = ITEM_CATALOG.get(read(npc, 'combat_artifact_id'))
    return dict(main_technique_name=read(technique, 'name') if technique else None,
                learned_techniques=public(game,npc),
                combat_artifact_name=artifact.name if artifact else None)


def project_loadout(game, owner, source=None, *, player=False, tianji_artifacts=()):
    source = source or CapabilitySource()
    if player:
        from .immortal_cultivation import golden_light, golden_light_resistance
        techniques = [t for t in [owner.technique, *owner.combat_techniques] if t and t.active_in(owner.world)]
        # Ordinary Item equipment is passive while held under the existing bag
        # model; crafted items must still occupy an equipped crafted slot.
        artifacts = [i for i in owner.inventory if i.quantity > 0 and set(i.tags) & {'artifact', 'equipment'}
                     and (not i.crafted_artifact_id or i.crafted_artifact_id in owner.equipped_crafted_artifact_ids)]
        ward = 2 if golden_light(owner) else 1
        resistance = golden_light_resistance(owner)
        from .crafting_system import active_crafted_artifacts
        artifacts.extend(active_crafted_artifacts(owner))
    else:
        key = read(owner, 'main_technique_id')
        from .npc_techniques import resolve
        technique = resolve(game,key)
        if technique is None and key:
            # Generated ids include the parent doctrine; direct lookup avoids
            # traversing the 25-doctrine catalog for every combatant.
            definition = game.doctrine_state.get('definitions', {}).get(key.split(':manual:')[0], {})
            technique = next((t for t in definition.get('manuals', ()) if t['id'] == key), None)
        worlds = read(technique, 'effective_worlds', ()) if technique else ()
        techniques = [technique] if technique and read(owner, 'main_technique_level', 0) >= 1 and (not worlds or read(owner, 'world') in worlds) else []
        artifact = ITEM_CATALOG.get(read(owner, 'combat_artifact_id'))
        artifacts = [artifact] if artifact else []
        ward = 2 if npc_golden_light(owner) else 1
        resistance = .01 if ward == 2 else 0.0
        artifacts.extend(tianji_artifacts)
        second = getattr(getattr(game, 'player', None), 'nascent_state', {}).get('second', {})
        if second and second.get('id') == read(owner, 'id'):
            from .npc_techniques import equipped
            techniques = [book for _, book in equipped(game, owner) if book.active_in(read(owner, 'world'))]
            artifacts = list(second['equipment'])
    if player:
        from .tianji_system import tianji_content_available
        if not tianji_content_available():
            artifacts = [a for a in artifacts if not read(a, 'tianji')]
    responses = tuple(r for t in techniques for r in _responses(t, 'technique')) + tuple(r for i in artifacts for r in _responses(i, 'artifact'))
    from .authored_techniques import combat_rules
    return replace(source, semantic_rules=source.semantic_rules + combat_rules(game, owner, player=player),
                   technique_tier=max((_tier(t) for t in techniques), default=1),
                   artifact_tier=max((_tier(i) for i in artifacts), default=1), passive_ward_tier=ward,
                   body_voisinage_resistance=resistance,
                   interventions=responses[:8])
