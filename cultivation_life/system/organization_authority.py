"""Pure control rule shared by politics and base-game organization actions."""


def player_controls(game, entity, members, *, member, rank=None):
    p = game.player
    if not entity or not p.alive:
        return False
    if entity.world == p.world and entity.founded_by_player and entity.founder_player_id == game.id:
        return True
    if rank is None:
        seal = p.cultivation_suppression or p.sealed_cultivation or {}
        rank = (seal.get('realm_index', p.realm_index), seal.get('layer', p.layer))
    return member and rank >= max(((n.realm_index, n.layer) for n in members if n.alive), default=(-1, -1))
