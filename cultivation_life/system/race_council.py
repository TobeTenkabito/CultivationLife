"""Local sect agreements on apprenticeship places and changes of political support."""
from ..content_registry import RACE_DEFINITIONS
from ..models import HistoryRecord
from ..race_diplomacy import relations_for
from ..world_state import race_pair
from .race_faction_directory import local_sects
from .war.occupancy import busy
from .economy.ledger import balance, transfer_value
from .economy.depot import treasury


MOTIONS = {'rotate': '各宗轮荐', 'sponsor': '推举主办山门', 'amend': '主办让席再议', 'mediate': '调让荐额', 'aid': '同地周济', 'invite': '延请客宗'}
PLACES = 6


def minutes(game, world, race):
    return game.strategic_war_state.get('local_councils', {}).get(world, {}).get(race, {})


def remaining(record, age):
    return record.get('places', {}) if record.get('awarded', -20) <= age < record.get('awarded', -20) + 10 else {}


def _slot(motion):
    return 'allocation' if motion in {'rotate', 'sponsor'} else motion


def next_session(record, motion):
    return record.get('sessions', {}).get(_slot(motion), -10) + 10


def ready(record, motion, age):
    if motion == 'amend':
        return bool(record.get('counter')) and age < next_session(record, 'sponsor')
    return age >= next_session(record, motion)


def _on_service(game, org):
    return busy(game, org) or any(w['status'] != 'ended' and any(c['org']['id'] == org.id for c in w['commitments'])
                                  for w in game.strategic_war_state.get('wars', ()))


def _may_leave(game, row):
    if not row['active']:
        return True
    org = game.sects[row['id']]
    return not (org.founded_by_player or org.id == game.player.faction_id or _on_service(game, org))


def _relation(game, world, a, b):
    return relations_for(game, world).get(race_pair(a, b), {})


def candidates(game, world, race, rows):
    return [r for r in rows.values() if r['allegiance'] != race
            and world in RACE_DEFINITIONS.get(r['allegiance'], {}).get('worlds', ())
            and _relation(game, world, race, r['allegiance']).get('status') != 'war'
            and _may_leave(game, r)]


def aid_offers(game, world, race):
    """Only funded sects at the actual meeting site can settle a cash grant."""
    local = []
    for org in game.sects.values():
        if (org.kind != 'sect' or org.extinct or org.allegiance_race != race or org.world != world
                or not org.location_id or org.location_id != game.player.location_id):
            continue
        account = treasury(game, org)
        books = game.economy_v2.get('organizations', {}).get(account, {})
        if 'expected_upkeep' not in books or 'resources' not in game.intrigue_state.get('factions', {}).get('sect:' + org.id, {}):
            continue
        if _on_service(game, org):
            continue
        local.append((org, balance(game, account), max(0, int(books['expected_upkeep']))))
    offers = []
    for receiver, cash, upkeep in local:
        shortfall = 3 * upkeep - cash
        if shortfall <= 0:
            continue
        for donor, donor_cash, donor_upkeep in local:
            amount = min(shortfall, (donor_cash - 3 * donor_upkeep) // 10)
            if amount > 0 and not (donor.founded_by_player and donor.id != game.player.faction_id):
                offers.append(dict(id=receiver.id, name=receiver.name, donor=donor.id, donor_name=donor.name, amount=amount))
    return offers


def _plan(record, members, motion, target, age):
    old = remaining(record, age)
    places = {key: old.get(key, 0) for key in members}
    if motion in {'invite', 'aid'}:
        return places, None
    if motion in {'mediate', 'sponsor', 'amend'} and target not in members:
        raise ValueError('请在本族议席中选一座山门')
    if motion == 'mediate':
        donor = max(places, key=places.get)
        if places[donor] - places[target] < 2:
            raise ValueError('两宗须至少相差两席，方可调让一席')
        places[donor] -= 1
        places[target] += 1
        return places, donor
    # The most frequently passed-over sects take the first places this term.
    order = sorted(members, key=lambda key: (-record.get('grievances', {}).get(key, 0), key))
    places = dict.fromkeys(order, 0)
    if motion in {'sponsor', 'amend'}:
        places[target] = 3 if motion == 'sponsor' else 2
        order.remove(target)
    for index in range(PLACES - sum(places.values())):
        places[order[index % len(order)]] += 1
    return places, None


def _realign(game, world, guest, race):
    identity = guest['id']
    previous = minutes(game, world, guest['allegiance'])
    for key in ('places', 'grievances'):
        previous.get(key, {}).pop(identity, None)
    if guest['active']:
        game.sects[identity].allegiance_race = race
    else:
        overrides = game.strategic_war_state.setdefault('directory_support', {}).setdefault(world, {})
        if race == guest['home_race']:
            overrides.pop(identity, None)
        else:
            overrides[identity] = race


def convene(game, world, race, motion, target, rng, *, rows=None, player_ballot=None, offer=None):
    if game.player.world != world or world not in RACE_DEFINITIONS.get(race, {}).get('worlds', ()):
        raise ValueError('此族议须在所属界面召开')
    rows = local_sects(game, world) if rows is None else rows
    members = {key: r for key, r in rows.items() if r['allegiance'] == race}
    age = game.player.age
    record = minutes(game, world, race)
    if motion not in MOTIONS or len(members) < 2 or not ready(record, motion, age):
        raise ValueError('议期或到会宗门已变，请重看议簿')
    if motion == 'amend' and record.get('counter') != target:
        raise ValueError('复议须由原案主办山门让出一席')
    grant = None
    if motion == 'aid':
        grant = next((q for q in aid_offers(game, world, race)
                      if q['id'] == target and [q['donor'], q['amount']] == offer), None)
        if not grant:
            raise ValueError('宗门驻地或府库账目已变，请重核周济数目')
    guest = None
    if motion == 'invite':
        guest = next((r for r in candidates(game, world, race, rows) if r['id'] == target), None)
        if not guest:
            raise ValueError('这座山门眼下不能改换盟书')
    proposed, donor = _plan(record, members, motion, target, age)
    old = remaining(record, age)
    grievances = record.get('grievances', {})
    ballots = []
    for key, member in members.items():
        seats = proposed[key]
        if grant:
            if key == grant['donor']:
                chance, interest = .62, f"本宗须从库中拨出{grant['amount']}灵石"
            elif key == target:
                chance, interest = .95, '这笔接济可补门下弟子供养'
            else:
                chance, interest = .72, '两宗同地守望，冬荒时也可彼此照应'
        elif guest:
            crowded = grievances.get(key, 0) > 0 or old.get(key, 0) == 0 and bool(old)
            chance, interest = (.35, '上届荐额尚未分匀，又要添一宗') if crowded else (.75, '愿与客宗互通门下')
        elif motion == 'mediate':
            if key == donor:
                chance, interest = .38, '门下已有待荐弟子，交出一席须另作安排'
            elif key == target:
                chance, interest = .98, '这一席正可留给候补弟子'
            else:
                chance, interest = .78, '两宗各退一步，来年仍可同办'
        elif seats * len(members) < PLACES:
            chance, interest = .35, f'本宗分得{seats}席，门下弟子多有落空'
        else:
            chance, interest = .90, f'本宗分得{seats}席，足以安排门下弟子'
        if motion in {'sponsor', 'amend'} and key != target:
            ties = game.sect_relations.get(race_pair(key, target), {})
            chance += max(-.2, min(.2, ties.get('affinity', 0) / 400))
        if motion == 'amend' and key != target:
            chance += .12
        if key == game.player.faction_id and player_ballot is not None:
            ballots.append(dict(id=key, name=member['name'], yes=player_ballot, reason='你代表本宗署名回函'))
            continue
        if key == game.player.faction_id and game.sects[key].founded_by_player:
            ballots.append(dict(id=key, name=member['name'], yes=False, abstain=True, reason='此案留待掌门亲署'))
            continue
        vote = rng.random() < max(.05, min(.98, chance))
        if vote and chance < .5:
            interest += '，但愿为往后来往退一步'
        elif not vote and chance >= .5:
            interest += '，仍请先顾及上届落选的同道'
        ballots.append(dict(id=key, name=member['name'], yes=vote, reason=interest))
    yes = sum(b['yes'] for b in ballots)
    passed = yes * 2 > len(ballots)
    reply = ''
    if grant and passed:
        signed = next(b['yes'] for b in ballots if b['id'] == grant['donor'])
        if signed and (grant['donor'] != game.player.faction_id or player_ballot is True):
            transfer_value(game, treasury(game, game.sects[grant['donor']]), treasury(game, game.sects[target]),
                           grant['amount'], '同地宗门族议周济')
            reply = f"{grant['donor_name']}已向{grant['name']}交割{grant['amount']}灵石。"
        else:
            passed = False
            reply = f"{grant['donor_name']}未署拨款书，府库封存如故。"
    if guest and passed:
        prior = guest['allegiance']
        grievance = minutes(game, world, prior).get('grievances', {}).get(target, 0)
        relation = _relation(game, world, race, prior)
        chance = min(.95, max(.1, .35 + .13 * grievance + relation.get('affinity', 0) / 240))
        passed = rng.random() < chance
        reply = (f"{guest['name']}收下盟书，转而支持{RACE_DEFINITIONS[race]['name']}。" if passed
                 else f"{guest['name']}仍愿守旧盟，婉辞来使。")
        if passed:
            _realign(game, world, guest, race)
    if not record:
        record = game.strategic_war_state.setdefault('local_councils', {}).setdefault(world, {}).setdefault(race, {})
    record.setdefault('sessions', {})[_slot(motion)] = age
    if motion in ('rotate', 'sponsor', 'amend'):
        record.pop('counter', None)
        if motion == 'sponsor' and not passed:
            record['counter'] = target
            reply = '诸宗请主办山门让出一席，再议此案。'
        if motion == 'amend' and passed:
            record['sessions']['allocation'] = age
    if passed and motion in {'sponsor', 'amend', 'rotate', 'mediate'}:
        if motion != 'mediate':
            record['awarded'] = age
            record.pop('used_at', None)
        record['places'] = {k: n for k, n in proposed.items() if n}
        record['grievances'] = {k: min(5, max(0, grievances.get(k, 0) +
            (1 if proposed[k] * len(members) < sum(proposed.values()) else -1))) for k in members}
    title = MOTIONS[motion]
    subject = rows[target]['name'] if target in rows else ''
    outcome = '议定' if passed else '搁置'
    summary = f"{title}{' · ' + subject if subject else ''}，{len(ballots)}宗到会，{yes}宗赞成。{reply or outcome + '。'}"
    meeting = dict(age=age, motion=motion, summary=summary, passed=passed, ballots=ballots)
    record['recent'] = (record.get('recent', []) + [meeting])[-3:]
    races = [race, guest['allegiance']] if guest else [race]
    game.history.append(HistoryRecord('SYS_LOCAL_RACE_COUNCIL', 1, age, title, target or None, outcome, summary,
        {'races': races}, ['system', 'race', 'diplomacy', 'world_news', f'world:{world}']))
    return summary


def advance(game, rng):
    world = game.player.world
    races = [k for k, r in RACE_DEFINITIONS.items() if world in r.get('worlds', ())]
    if not races:
        return None
    race = rng.choice(races)
    rows = local_sects(game, world)
    members = [r['id'] for r in rows.values() if r['allegiance'] == race]
    if len(members) < 2:
        return None
    record = minutes(game, world, race)
    if ready(record, 'amend', game.player.age) and record['counter'] in members:
        return convene(game, world, race, 'amend', record['counter'], rng, rows=rows)
    available = remaining(record, game.player.age)
    if available and ready(record, 'mediate', game.player.age):
        least = min(members, key=lambda key: available.get(key, 0))
        if max(available.get(key, 0) for key in members) - available.get(least, 0) >= 2:
            return convene(game, world, race, 'mediate', least, rng, rows=rows)
    if rng.random() < .35 and ready(record, 'invite', game.player.age):
        guests = candidates(game, world, race, rows)
        if guests:
            weights = [1 + minutes(game, world, g['allegiance']).get('grievances', {}).get(g['id'], 0) for g in guests]
            guest = rng.choices(guests, weights=weights, k=1)[0]
            return convene(game, world, race, 'invite', guest['id'], rng, rows=rows)
    if ready(record, 'rotate', game.player.age):
        motion = rng.choice(('sponsor', 'rotate'))
        return convene(game, world, race, motion, rng.choice(members) if motion == 'sponsor' else '', rng, rows=rows)
    return None


def actor_available(game):
    from ..soul_rules import wandering
    p = game.player
    return (p.alive and not (p.imprisonment or p.ghost_captor or wandering(p) or game.pending_event
            or game.active_trial or game.dungeon_state.get('active') or game.guixu_state.get('player_session')
            or game.generated_event_state.get('active') or game.trial_site_state.get('active')))
