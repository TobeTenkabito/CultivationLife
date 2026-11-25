"""Content-to-capability boundary. No item lookup inside combat rounds.

NPC treasure is deliberately never inspected here. Empty/unresolved slots do
not invent equipment, and a combat snapshot is not another ownership ledger.
"""
from ..definition_data import definition as _content_definition
from dataclasses import replace

from ..content_registry import ITEM_CATALOG, TECHNIQUE_CATALOG
from .combat.contracts import CapabilitySource, Intervention
from .combat.npc_lifecycle import read
from .cultivation_ranks import npc_golden_light


BODY_WARDS = _content_definition(__name__, "BODY_WARDS")


def _tier(entry):
    from .item_qualification import force_tier
    return force_tier(entry)


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


def player_equipment(game, owner):
    techniques = [t for t in [owner.technique, *owner.combat_techniques] if t and t.active_in(owner.world)]
    # Ordinary Item equipment is passive while held under the existing bag
    # model; crafted items must still occupy an equipped crafted slot.
    from ..rules import passive_inventory
    artifacts = [i for i in passive_inventory(owner) if i.quantity > 0 and set(i.tags) & {'artifact', 'equipment'}
                 and (not i.crafted_artifact_id or i.crafted_artifact_id in owner.equipped_crafted_artifact_ids)]
    from .crafting_system import active_crafted_artifacts
    artifacts.extend(active_crafted_artifacts(owner))
    # The bound item has left the ordinary bag. Its real capability still
    # participates once; a cultivation grade never supplies attack tier.
    if game.natal_artifact:
        from .immortal_artifacts import active_natal_tier
        bound = game.natal_artifact
        entry = bound.get('source_item') or next((a for a in owner.crafted_artifacts if a['id'] == bound.get('crafted_artifact_id')), None)
        if entry is None:
            entry = ITEM_CATALOG.get(bound.get('item_id')) or bound
        from ..combat_attributes import profile_for
        artifacts.append(dict(id=bound.get('item_id'), name=bound.get('name') or read(entry,'name'),
                              combat_bonus=owner.natal_artifact_combat_bonus, damage_profile=profile_for(entry), force_tier=active_natal_tier(game)))
    from .tianji_system import tianji_content_available
    if not tianji_content_available():
        artifacts = [a for a in artifacts if not read(a, "tianji")]
    return techniques, artifacts


def player_attributes(game):
    techniques, artifacts = player_equipment(game, game.player)
    return project_attributes(game.player, [t for t in techniques if t.category == "spiritual"],
                              artifacts, player=True)


def project_loadout(game, owner, source=None, *, player=False, tianji_artifacts=()):
    source = source or CapabilitySource()
    if player:
        from .immortal_cultivation import golden_light, golden_light_resistance
        techniques, artifacts = player_equipment(game, owner)
        ward = 2 if golden_light(owner) else 1
        resistance = golden_light_resistance(owner)
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
        resistance = 0.0
        artifacts.extend(tianji_artifacts)
        second = getattr(getattr(game, 'player', None), 'nascent_state', {}).get('second', {})
        if second and second.get('id') == read(owner, 'id'):
            from .npc_techniques import equipped
            techniques = [book for _, book in equipped(game, owner) if book.active_in(read(owner, 'world'))]
            artifacts = list(second['equipment'])
    techniques = [t for t in techniques if read(t, 'category', 'spiritual') == 'spiritual']
    responses = tuple(r for t in techniques for r in _responses(t, 'technique')) + tuple(r for i in artifacts for r in _responses(i, 'artifact'))
    from .authored_techniques import combat_rules
    from .technique_effect_provider import project as project_technique_effects
    from .divine_lights import profile
    lights,levels=profile(owner,player=player)
    from .wuyun import profile as aggregate_profile
    body=aggregate_profile(owner,player=player)
    from .monster_body import profile as monster_profile
    body=body or monster_profile(owner,player=player)
    from .ghost_body import profile as ghost_profile
    body=body or ghost_profile(owner,player=player)
    from ..trait_mechanics import combat_rules as trait_rules
    attributes = project_attributes(owner, techniques, artifacts, player=player)
    return replace(source, attributes=attributes, semantic_rules=source.semantic_rules + combat_rules(game, owner, player=player),
                   trait_rules=trait_rules(attributes["traits"]),
                   technique_effects=project_technique_effects(game, owner, player=player),
                   technique_tier=attributes["attacks"].get("technique", {}).get("tier", 1),
                   artifact_tier=max((_tier(i) for i in artifacts), default=1), passive_ward_tier=ward,
                   body_voisinage_resistance=resistance,
                   divine_lights=lights,divine_light_levels=levels,
                   body_mechanisms=body,
                   interventions=responses[:8])


def project_attributes(owner, techniques, artifacts, *, player=False):
    from ..combat_attributes import profile_for
    from ..traits import SPECIAL_EFFECTS, NON_COMBAT_TRAITS, active, state
    from ..technique_affinity import can_practice_technique
    attacks = {}
    from ..models import Technique
    books = [Technique(**t) if isinstance(t, dict) else t for t in techniques]
    if not player:
        from .duel_techniques import npc_eligible
        permitted = [t for t in books if npc_eligible(owner, t)]
    else:
        permitted = [t for t in books if can_practice_technique(owner, t)]
        from ..rules import combat_requirement_met, qi_levels
        levels = qi_levels(owner)
        permitted = [t for t in permitted if combat_requirement_met(t.combat_requirements, levels)
                     and owner.body_training >= t.required_body_training
                     and (not t.requires_immortal_power or owner.immortal_power_converted)]
    from .combat.actor_state import has_body
    body_book = read(owner, "body_technique") if player and has_body(owner) else None
    if (body_book and body_book.active_in(owner.world) and can_practice_technique(owner, body_book)
            and body_book.required_body_training <= owner.body_training
            and (not body_book.requires_immortal_power or owner.immortal_power_converted)):
        permitted.append(body_book)
    def attack_tier(entry):
        # Body training supplies the composition of an unarmed strike. Higher
        # force still requires the ordinary body's original energy payment.
        return 1 if body_book is not None and entry is body_book else _tier(entry)

    def power(entry):
        return read(entry, "combat_bonus", 0) or (read(entry,"actual_stats",{}) or {}).get("combat_power",0)

    for kind, entries in (("technique", permitted), ("artifact", artifacts)):
        if entries:
            best = max(entries, key=lambda e: (attack_tier(e), power(e)))
            attacks[kind] = dict(name=read(best,"name") or "法宝", id=read(best,"id"), tier=attack_tier(best),
                                 profile=profile_for(best), power=power(best))
    ward_sources = {}
    for kind, entries in (("technique", permitted), ("artifact", artifacts)):
        for entry in entries:
            for element in profile_for(entry):
                if element != "physical" and kind not in ward_sources.setdefault(element, []):
                    ward_sources[element].append(kind)
    traits = [t for t in active(owner) if t not in NON_COMBAT_TRAITS]
    for trait, elements in BODY_WARDS.items():
        if trait in traits:
            for element in elements:
                sources = ward_sources.setdefault(element, [])
                if "body" not in sources:
                    sources.append("body")
    ward_options = list(ward_sources)
    preferred = state(owner).get("ward")
    ward_element = preferred if preferred in ward_options else next(iter(ward_options), None)
    return dict(attacks=attacks, traits=traits, ward=ward_element, wards=ward_options, ward_sources=ward_sources,
                      flame=state(owner).get("flame", SPECIAL_EFFECTS["default_flame"]))


def npc_attribute_sources(attackers, defenders, sources):
    from ..traits import active
    sources = dict(sources or {})
    for npc, _ in [*attackers, *defenders]:
        if npc.id in sources:
            continue
        book = TECHNIQUE_CATALOG.get(npc.main_technique_id)
        artifact = ITEM_CATALOG.get(npc.combat_artifact_id)
        if book or artifact or active(npc):
            projection = project_attributes(npc, [book] if book and book.active_in(npc.world) else [],
                                            [artifact] if artifact else [])
            if projection["ward"] or projection["traits"]:
                from ..trait_mechanics import combat_rules as trait_rules
                sources[npc.id] = CapabilitySource(attributes=projection, trait_rules=trait_rules(projection["traits"]),
                    technique_tier=projection["attacks"].get("technique", {}).get("tier",1),
                    artifact_tier=projection["attacks"].get("artifact", {}).get("tier",1))
    return sources
