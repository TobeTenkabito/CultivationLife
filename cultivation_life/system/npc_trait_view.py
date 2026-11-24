"""Read-only trait details for public NPC views."""
from ..combat_attributes import read
from ..cultivation_coordinates import rank_for
from ..spatial_people import accessible
from ..traits import public as personal_traits
from .trait_study import source_name
from .npc_concealment import concealed_rank


def visible_traits(game, owner):
    if owner is None or not accessible(game, owner) or not read(owner, "alive", True):
        return None
    from ..person_assignments import deployment_assignment
    deployment = deployment_assignment(game, read(owner, "id"))
    if deployment and not deployment.get("observed"):
        return None
    if concealed_rank(owner) is not None:
        if game.player.divine_sense_rank < rank_for(read(owner, "realm_index", 0), read(owner, "layer", 1)):
            return None
    if read(owner, "trait_state") is None:
        return None
    return [dict(row, source_names=[source_name(key) for key in row["sources"]])
            for row in personal_traits(owner)]


def attach_to_views(game, view):
    """Decorate detached public rows. Resolve each person's current state once per view."""
    from ..relationship_records import find_person

    children = {child["id"]: child for child in game.player.offspring}
    cache = {row["id"]: row.get("traits")
             for row in [*view["world_npcs"], *view["faction"].get("roster", [])]
             if not row.get("is_player")}

    def person(row, identity=None):
        if not isinstance(row, dict) or row.get("is_player") or row.get("player") is True:
            return row
        identity = identity or row.get("npc_id") or row.get("id")
        if not identity or identity == "player":
            return row
        row = dict(row)
        row.pop("trait_state", None)
        masked = (row.get("present") is False or row.get("alive") is False
                  or row.get("identity_known") is False or row.get("perceived_alive") is False
                  or row.get("world", True) is None or row.get("same_world") is False
                  or (row.get("cultivation_concealment") or {}).get("revealed") is False)
        if not masked and identity not in cache:
            owner = find_person(game, identity, include_inactive=True) or children.get(identity)
            cache[identity] = visible_traits(game, owner)
        row["traits"] = None if masked else cache[identity]
        if row.get("portrait"):
            row["portrait"] = dict(row["portrait"], traits=row["traits"])
        return row

    def groups(container, *keys):
        for key in keys:
            if isinstance(container.get(key), list):
                container[key] = [person(row) for row in container[key]]

    def single(container, key):
        if container.get(key):
            container[key] = person(container[key])

    player = view["player"]
    for key in ("master", "dao_companion"):
        single(player, key)
    groups(player, "disciples", "disciple_requests", "dao_friends", "concubines", "offspring", "prisoners")
    groups(view, "world_npcs", "dao_friends", "party")
    single(view, "dao_companion")
    groups(view["family"], "roster", "offspring")
    groups(view["faction"], "roster")
    groups(view["spirit_ranking"], "entries")
    groups(view["personal_relations"], "high", "low")
    groups(view["concubine_system"], "concubines")
    groups(view["demonic_system"], "prisoners")
    school = view["mentorship"]
    groups(school, "disciples", "peers")
    if school.get("master"):
        single(school["master"], "teacher_portrait")
    avatar = view["mentorship_advanced"].get("avatar")
    if avatar:
        single(avatar, "portrait")
    for section in view["intrigue_system"].get("sections", []):
        groups(section, "members", "guests")
        section["prison"] = [person(row, row.get("prisoner_id")) for row in section.get("prison", [])]
    for doctrine in view["sage_system"].get("doctrines", []):
        groups(doctrine, "members")
    status = view["concubine_system"].get("status")
    if status:
        view["concubine_system"]["status"] = person(status, status.get("owner_id"))
    for puppet in view["demonic_system"].get("puppets", []):
        if puppet.get("type") == "living" and puppet.get("source_npc_id"):
            puppet.update(person(puppet, puppet["source_npc_id"]))
    for war in view["war_system"].get("wars", []):
        groups(war.get("roster", {}), "attacker", "defender")
    scene = view["spatial"].get("scene") or {}
    groups(scene, "npcs")
    society = scene.get("society") or {}
    for organization in [*society.get("sects", []), *society.get("families", [])]:
        groups(organization, "members")
    institution = view["upper_institution"]
    groups(institution, "people")
    groups(institution.get("court") or {}, "seats")
    court = view["heavenly_court"]
    for office in court.get("offices", []):
        holder = office.get("holder")
        if holder:
            office["holder"] = person(holder, holder.get("holder_id"))
    bureaus = court.get("bureaus") or {}
    groups(bureaus, "staff", "candidates")
    for case in (bureaus.get("inspection") or {}).get("cases", []):
        groups(case, "reviewers")
