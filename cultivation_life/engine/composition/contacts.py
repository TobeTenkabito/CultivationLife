"""Bind contact operations without a system-to-engine import."""
from ...system.npc_contact_dependencies import NpcContactDependencies
from ..actions.relationships import manage_faction_relationship


def bind_contacts(engine) -> NpcContactDependencies:
    return NpcContactDependencies(
        _adjust_person_affinity=lambda *args, **kwargs: engine._adjust_person_affinity(*args, **kwargs),
        _find_npc=lambda *args, **kwargs: engine._find_npc(*args, **kwargs),
        _load=lambda *args, **kwargs: engine._load(*args, **kwargs),
        _promote_cached_npc=lambda *args, **kwargs: engine._promote_cached_npc(*args, **kwargs),
        _sage_affinity_gain=lambda *args, **kwargs: engine._sage_affinity_gain(*args, **kwargs),
        assert_buddhist_operation_allowed=lambda *args, **kwargs: engine.assert_buddhist_operation_allowed(*args, **kwargs),
        begin_relationship_capture=lambda *args, **kwargs: engine.begin_relationship_capture(*args, **kwargs),
        manage_concubine=lambda *args, **kwargs: engine.manage_concubine(*args, **kwargs),
        manage_dao_companion=lambda *args, **kwargs: engine.manage_dao_companion(*args, **kwargs),
        manage_dao_friend=lambda *args, **kwargs: engine.manage_dao_friend(*args, **kwargs),
        manage_known_relationship=lambda game_id, npc_id, role: manage_faction_relationship(
            engine._dependencies.relationship_actions, game_id, npc_id, role, known_target=True),
        manage_party=lambda *args, **kwargs: engine.manage_party(*args, **kwargs),
        present=lambda *args, **kwargs: engine.present(*args, **kwargs),
        relationship_violence=lambda *args, **kwargs: engine.relationship_violence(*args, **kwargs),
        _get_store=lambda: engine.store,
    )
