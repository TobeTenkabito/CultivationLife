"""Bounded ten-year organization decisions; never a second army or treasury."""
from ...npc_custody import is_free
from ...spatial_people import instance_of
from .rules import SIDES, ref, committed_org, owns
from .records import note
from ..war.logistics import cash
from ..war.requirements import deployed_people


def baseline(people):
    return {n.id: n.wounds for n in people}


def evaluate(deps, game, row):
    children = [w for w in game.wars if w.get('strategic_war_id') == row['id']]
    forces = {}
    for c in row['commitments']:
        org = committed_org(game, row, c)
        people = {n.id: n for n in deps.members(game, org)} if org else {}
        forces[c['org']['id']] = sum(deps.power(n) for n in people.values() if is_free(n)
            and n.world == row['world'] and not instance_of(game, n.id) and not deps.imprisoned(game, n.id))
    totals = {s: sum(forces[c['org']['id']] for c in row['commitments'] if c['side'] == s) for s in SIDES}
    task_forces = {w['id']: {s: sum(deps.power(n) for n in deployed_people(game, w, s)) for s in SIDES}
                   for w in children if w.get('status') == 'active'}
    result = {}
    for c in row['commitments']:
        identity = c['org']['id']; side = c['side']; enemy = 'defender' if side == 'attacker' else 'attacker'
        org = committed_org(game, row, c)
        child = next((w for w in children if identity in {r['id'] for r in w['coalitions'][side]}
                      and w.get('status') == 'active' and identity not in w.get('withdrawn_orgs', [])), None)
        def balance(own, other):
            return round(100 * own / max(1, own + other))
        task = balance(task_forces[child['id']][side], task_forces[child['id']][enemy]) if child else 60
        alliance = balance(totals[side], totals[enemy])
        reserves = min(100, round(100 * cash(game, org) / max(1, c['budget']))) if org else 0
        supply = reserves
        if child:
            from ..war.supply import turns
            physical = min(100, round(turns(game, child, side) * 50))
            supply = round((reserves + physical) / 2)
        originals = c.get('will_baseline', {})
        loss = 0
        for identity_npc, wounds in originals.items():
            n = deps.find_person(game, identity_npc)
            loss += (1 if not n.alive else min(1, max(0, n.wounds - wounds) / 4)) if n else 0
        casualty = round(100 * loss / max(1, len(originals)))
        target = max(5, min(95, round(5 + .30 * task + .20 * alliance + .45 * supply - .65 * casualty)))
        old = c.get('willingness', 70)
        value = max(old - 8, min(old + 5, target))
        result[identity] = dict(value=value, task=task, alliance=alliance, supply=supply,
                                casualties=casualty, posture='消极守备' if value < 35 else '积极参战')
    return result


def advance(deps, game, row):
    if row['status'] not in {'mobilizing', 'active'} or game.player.age - row.get('will_age', row['start_age']) < 10:
        return
    row['will_age'] = game.player.age
    values = evaluate(deps, game, row)
    for c in row['commitments']:
        org = committed_org(game, row, c)
        if not c.get('will_baseline') and org:
            c['will_baseline'] = baseline(deps.members(game, org)[:24])
        c['willingness'] = values[c['org']['id']]['value']
        c['will_factors'] = values[c['org']['id']]
    for child in game.wars:
        if child.get('strategic_war_id') != row['id'] or child.get('status') != 'active':
            continue
        passive = []
        for c in row['commitments']:
            org = committed_org(game, row, c)
            if not org or owns(deps, game, org) or org.id not in child.get('roster_owner', {}).values():
                continue
            if c['willingness'] < 35:
                passive.append(org.id)
            if c['willingness'] < 20 and child.get('battles', 0) >= 3 and org.id not in child.get('withdrawn_orgs', []):
                from .dispatch import recall
                from .settlement import receipt
                finished = recall(game, child, org)
                note(game, row, '战意低落', f'{org.name}因军需与损耗请求撤回，盟宗仍按原令作战。')
                if finished:
                    receipt(game, row, child)
                    break
        child['passive_orgs'] = passive


def personal_side(deps, game, row, child):
    p = game.player
    if (row['status'] != 'active' or child.get('status') != 'active' or child.get('campaign_phase') != 'engaged'
            or p.world != row['world'] or p.location_id != child.get('location_id') or instance_of(game, 'player')
            or not p.alive or p.imprisonment or p.ghost_captor or game.pending_event or game.active_trial
            or game.player.age - child.get('last_personal_age', -1000) < 10):
        return None
    identities = {p.faction_id}
    if game.family:
        identities.add(game.family.id)
    sides = {c['side'] for c in row['commitments'] if c['org']['id'] in identities
             and committed_org(game, row, c) and c['org']['id'] not in child.get('withdrawn_orgs', [])
             and c['org']['id'] in {r['id'] for r in child['coalitions'][c['side']]}}
    return next(iter(sides)) if len(sides) == 1 else None
