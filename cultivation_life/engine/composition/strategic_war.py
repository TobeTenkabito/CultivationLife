"""The sole bridge between strategic decisions and ordinary campaign execution."""
from ...system.strategic_war.dependencies import StrategicWarDependencies
from ...system.war.lifecycle import _advance_wars_unit
from ...system.war.diplomacy import player_side
from ...relationship_records import find_person


def bind(host):
    return StrategicWarDependencies(
        maps=host.maps,
        start_campaign=lambda *a, **kw: host._start_war(*a, **kw),
        advance_campaigns=lambda game, rng, wars: _advance_wars_unit(
            host._dependencies.war.lifecycle, game, rng, campaigns=wars),
        find_person=find_person,
        player_side=lambda *a: player_side(host._dependencies.war.diplomacy, *a),
        members=lambda *a: host._sect_members(*a),
        has_sect_voice=lambda *a: host._has_sect_voice(*a),
        has_family_voice=lambda *a: host._has_family_voice(*a),
        has_race_voice=lambda *a: host._has_race_voice(*a),
        imprisoned=lambda *a: host._intrigue_is_imprisoned(*a),
        power=lambda *a: host._npc_power(*a),
        recruit=lambda *a: host._recruit_sect_npc(*a),
        peace_preview=lambda *a: host._generate_ai_peace_offer(*a),
        vote_probability=lambda *a: host._vote_probability(*a),
        prepare_formations=lambda *a: host._ensure_npc_formations(*a),
    )
