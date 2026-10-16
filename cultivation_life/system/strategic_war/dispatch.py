"""Idle organizations join an existing campaign; nobody changes battle mid-deployment."""
from ...world_state import race_pair
from ..war.occupancy import busy, participant_ids
from ..war import logistics
from ..map_system import TravelPlan
from ..economy import depot
from ..economy.ledger import account, balance, transfer_value
from .rules import SIDES, army, organizations, ref, site, local_races, routes
from .records import note


def remaining_budget(game, row, commitment):
    identity = commitment['org']['id']
    used = 0
    for child in game.wars:
        if child.get('strategic_war_id') != row['id']:
            continue
        used += sum(s.get('contributions', {}).get(identity, 0)
                    for s in child.get('logistics', {}).get('sides', {}).values())
        used += sum(r['paid'] for r in child.get('reinforcements', [])
                    if r['org']['id'] == identity and not r['delivered'])
    return max(0, commitment['budget'] - used)


def plan(deps, game, row, child, org):
    if (row['status'] != 'active' or child.get('strategic_war_id') != row['id']
            or child.get('status') != 'active' or child.get('campaign_phase') not in {'marching', 'engaged'}):
        raise ValueError('只能支援尚未结束的本案战役')
    if not {row['attacker'], row['defender']} <= set(local_races(row['world'])):
        raise ValueError('本案种族内容未开放，不能追加出征')
    commitment = next((c for c in row['commitments'] if c['org'] == ref(org)), None)
    if not commitment or org.extinct or org.world != row['world'] or org.allegiance_race != row[commitment['side']]:
        raise ValueError('须由本界原组织批准本案参战承诺')
    if busy(game, org):
        raise ValueError('只能调遣闲置宗门：原战役行军、交战或撤军尚未结束')
    if org.id in participant_ids(child):
        raise ValueError('此组织已经参加过该战役，不能重复加入')
    side = commitment['side']
    enemies = [r['id'] for r in child['coalitions']['defender' if side == 'attacker' else 'attacker']]
    for enemy in enemies:
        relation = game.sect_relations.get(race_pair(org.id, enemy), {})
        if game.diplomacy_unit < max(relation.get('truce_until_unit', 0), relation.get('war_truce_until_unit', 0)):
            raise ValueError('此组织与战场敌宗仍在停战期')
    capacity = 48 - len(child['roster'][side])
    people = army(deps, game, org)[:min(12, capacity)]
    if not people:
        raise ValueError('没有可出征修士，或本方战场名册已满')
    journeys = routes(deps, game, people, child['location_id'], site(org))
    ceiling = min(j['years'] for j in journeys) + 10
    journeys = [j for j in journeys if j['years'] <= ceiling]
    selected = {j['person_id'] for j in journeys}
    people = [n for n in people if n.id in selected]
    origin=site(org)
    route = (TravelPlan(origin,origin,0,0,(origin,),'ok','') if origin==child['location_id'] else
             deps.maps.travel_plan(org.world, origin, child['location_id'], min(n.realm_index for n in people)))
    if route.status != 'ok':
        raise ValueError('此组织军需没有合法的同界道路')
    paid = min(remaining_budget(game, row, commitment), logistics.cash(game, org), logistics.need(game, child, side) * 3)
    if paid <= 0:
        raise ValueError('本案批准军费已用尽或原府库无可用经费')
    return side, journeys, route, int(paid)


def send(deps, game, row, child, org, *, expected_cost=None):
    side, journeys, route, paid = plan(deps, game, row, child, org)
    if expected_cost is not None and (type(expected_cost) is not int or expected_cost != paid):
        raise ValueError('调度军费已变化，请刷新后核对')
    deps.prepare_formations(game)
    escrow = f"war-supply:{child['id']}:{side}:reserve:{org.id}"
    account(game, escrow)
    transfer_value(game, depot.treasury(game, org), escrow, paid, '闲置组织出征：实际随军灵石封存')
    cargo = dict(origin=site(org), destination=child['location_id'], route=list(route.route),
                 years=route.years, remaining=route.years, phase='outbound', departed_age=game.player.age)
    child.setdefault('reinforcements', []).append(dict(org=ref(org), side=side, wallet=escrow, paid=paid,
                                                       delivered=False, refunded=False, cargo=cargo))
    child.setdefault('org_budget_caps',{})[org.id]=paid
    child['budget_caps'][side]+=paid
    child['coalitions'][side].append(dict(id=org.id, role='ally', joined_unit=game.diplomacy_unit,
                                          called_by=row['commanders'].get(side, {}).get('person_id')))
    for journey in journeys:
        journey.update(reinforcement=True, departed_age=game.player.age)
        identity = journey['person_id']
        child['roster'][side].append(identity)
        child['roster_owner'][identity] = org.id
        child['journeys'][side].append(journey)
    for enemy in child['coalitions']['defender' if side == 'attacker' else 'attacker']:
        game.sect_relations.setdefault(race_pair(org.id, enemy['id']), {}).update(
            status='war', affinity=-75., since_age=game.player.age, strategic_war_id=row['id'])
    # Existing armies keep their battle clock. A distant reserve cannot freeze them.
    row['deadline_age'] = max(row['deadline_age'], game.player.age + max(route.years, max(j['years'] for j in journeys)) + 120)
    note(game, row, '预备队出征', f"{org.name}增援{child['location_id']}，{len(journeys)}名修士；随军经费 {paid}，抵达后方可用于前线。")
    return paid


def advance_cargo(game, child):
    """Advance each original escrow once a real year; hand over only on arrival."""
    from ..economy.organizations import register
    for reinforcement in child.get('reinforcements', []):
        cargo = reinforcement['cargo']
        if cargo['phase']=='home':
            continue
        if cargo['phase'] in {'outbound', 'returning'} and game.player.age > cargo.get('last_age',cargo['departed_age']):
            cargo['remaining'] = max(0, cargo['remaining'] - 1)
            cargo['last_age']=game.player.age
        if cargo['remaining']:
            continue
        returning = cargo['phase']=='returning' or child['campaign_phase'] == 'returning'
        cargo['phase'] = 'home' if returning else 'stationed'
        if not returning and not reinforcement['delivered']:
            side = reinforcement['side']
            transfer_value(game, reinforcement['wallet'], logistics.wallet(child, side),
                           balance(game, reinforcement['wallet']), '援军抵达：交付原随军灵石')
            supply = child['logistics']['sides'][side]
            identity = reinforcement['org']['id']
            supply['contributions'][identity] = supply['contributions'].get(identity, 0) + reinforcement['paid']
            supply['mobilized'] += reinforcement['paid']
            reinforcement['delivered'] = True
        elif returning and not reinforcement['delivered'] and not reinforcement['refunded']:
            org = next((o for o in organizations(game, child['world']) if ref(o) == reinforcement['org']), None)
            target = f"background:{child['world']}"
            if org:
                register(game, depot.owner_kind(game, org), org.id, org.world)
                target = depot.treasury(game, org)
            transfer_value(game, reinforcement['wallet'], target, balance(game, reinforcement['wallet']),
                           '援军原路归返：未交付随军经费结清')
            reinforcement['refunded'] = True


def recall(game, child, org):
    """Recall only this organization's actual troops; allies keep their orders."""
    if org.id in child.get('withdrawn_orgs', []):
        raise ValueError('此组织已经撤回，不能重复下令')
    child.setdefault('withdrawn_orgs', []).append(org.id)
    for rows in child['journeys'].values():
        for journey in rows:
            if child['roster_owner'].get(journey['person_id'])==org.id and journey['phase'] not in {'home','lost','returning'}:
                elapsed=journey['years']-journey['remaining'] if journey['phase']=='outbound' else journey['years']
                journey.update(destination=journey['origin'],remaining=elapsed,phase='returning')
    side=next(s for s in SIDES if org.id in {r['id'] for r in child['coalitions'][s]})
    cargo=child['cargo_journeys'][side] if child[f'{side}_id']==org.id else next(r['cargo'] for r in child['reinforcements'] if r['org']==ref(org))
    if all(r['id'] in child['withdrawn_orgs'] for r in child['coalitions'][side]) and cargo['phase'] in {'outbound','stationed'}:
        child['logistics']['sides'][side]['return_location']=cargo['origin']
    if cargo['phase'] not in {'home','lost','returning'}:
        elapsed=cargo['years']-cargo['remaining'] if cargo['phase']=='outbound' else cargo['years']
        cargo.update(destination=cargo['origin'],remaining=elapsed,phase='returning')
    if all(r['id'] in child['withdrawn_orgs'] for r in child['coalitions'][side]):
        child.update(status='peace_ready',winner='defender' if side=='attacker' else 'attacker')
        return True
    return False


def auto_dispatch(deps, game, row):
    from .politics import player_commander
    if row['status'] != 'active' or not {row['attacker'], row['defender']} <= set(local_races(row['world'])):
        return
    for side in SIDES:
        if (player_commander(deps, game, row) == side or not row['commanders'].get(side)
                or game.player.age - row.get('dispatch_ages', {}).get(side, -1000) < 10):
            continue
        row.setdefault('dispatch_ages', {})[side] = game.player.age
        candidates = sorted((w for w in game.wars if w.get('strategic_war_id') == row['id'] and w['status'] == 'active'),
                            key=lambda w: (w['morale'][side], len(w['coalitions'][side]), w['id']))
        for child in candidates:
            sent = False
            for org in organizations(game, row['world']):
                if org.allegiance_race != row[side]:
                    continue
                try:
                    send(deps, game, row, child, org)
                except ValueError:
                    continue
                sent = True
                break
            if sent:
                break
