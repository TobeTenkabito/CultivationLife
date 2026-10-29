"""Pure control rule shared by politics and base-game organization actions."""


def chartered_member(game, entity):
    """Keep original control membership during a pre-authorized frontier visit.

    Local command entry points still check the actual world and location.
    This only prevents ordinary preparation from replacing an absent founder
    or family controller merely because they used their existing charter.
    """
    rows = getattr(game, 'heavens_state', {}).get('runtime', {}).get('outposts', {})
    if not rows:
        return False
    p = game.player
    if not entity or not p.alive or entity.extinct or not (entity is game.family or p.faction_id == entity.id):
        return False
    return any(row['owner_id'] == entity.id and row['issuer_id'] == game.id
               and row['source'] == entity.world and p.world in {row['source'], row['destination']}
               and (row['status'] != 'closed' or (row.get('visit') or {}).get('status') in {'preparing', 'visiting'})
               for row in rows.values())


def player_controls(game, entity, members, *, member, rank=None):
    p = game.player
    if not entity or not p.alive:
        return False
    charter_member = chartered_member(game, entity)
    if (entity.world == p.world or charter_member) and entity.founded_by_player and entity.founder_player_id == game.id:
        return True
    if rank is None:
        seal = p.cultivation_suppression or p.sealed_cultivation or {}
        rank = (seal.get('realm_index', p.realm_index), seal.get('layer', p.layer))
    return (member or charter_member) and rank >= max(((n.realm_index, n.layer) for n in members if n.alive), default=(-1, -1))
