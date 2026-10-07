"""Read-only royal personnel and fiscal modifiers; no government actions."""
import hashlib

COURT = 'asura_royal_court'


def people(game):
    court = game.sects.get(COURT)
    return {n.id: n for n in court.npcs} if court else {}


def present(npc):
    return bool(npc and npc.alive and npc.world == 'asura' and npc.faction_id in (None, COURT))


def talent(npc, office):
    digest = hashlib.sha256(f'{npc.id}:{office}'.encode()).digest()
    return min(95, 35 + digest[0] % 46 + max(0, npc.realm_index - 9) * 5)


def benefits(game, state):
    court, roster = state['court'], people(game)
    result = dict(revenue=1., service=1., discount=0., wages=0)
    for office, identity in court['offices'].items():
        npc = roster.get(identity)
        if not present(npc):
            continue
        skill = talent(npc, office)
        result['wages'] += 30000
        key, scale = {'treasury': ('revenue', .002), 'marshal': ('service', .002), 'ritual': ('discount', .001)}[office]
        result[key] += skill * scale
    result['revenue'] += .1 * court['buildings']['market']
    result['service'] += .1 * court['buildings']['barracks']
    result['discount'] += .03 * court['buildings']['sanctum']
    # Starting at fifty preserves the old basic treasury economy.
    result['revenue'] *= .75 + court['public_support'] / 200
    return result
