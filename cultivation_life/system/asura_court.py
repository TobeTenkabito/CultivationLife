"""Persistent royal seats and elapsed-time governance, available without DLC."""
import copy
import hashlib

from ..content_registry import FACTION_NPC_TEMPLATES, ITEM_CATALOG, ROOT_DEFINITIONS, WORLD_SYSTEMS
from ..models import SectNpc
from ..rules import combat_power, expected_combat_power, max_hp, max_mp
from .npc_system import npc_combat_power
from . import asura_factions

COURT = 'asura_royal_court'
KING = 5
OFFICES = {
    'treasury': ('府库总管', '每单位府库收入增加才干值的千分之二'),
    'marshal': ('掌军使', '新委托功勋增加才干值的千分之二'),
    'ritual': ('养域使', '本界邻域培养费用额外减免才干值的千分之一'),
}
WORKS = {
    'market': ('万战互市', '每级使府库单位收入增加一成'),
    'barracks': ('血战武院', '每级使新委托功勋增加一成'),
    'sanctum': ('养域坛', '每级使本界邻域培养费用额外减少三个百分点'),
}
DECREES = {
    'relief': ('开仓安抚', 240000, '府库 −240,000，民心 +15'),
    'levy': ('征收战赋', 0, '府库 +300,000，民心 −15；民心至少四十'),
    'reward': ('犒赏群臣', 200000, '府库 −200,000，所有在世廷臣忠诚 +12'),
}


def cfg():
    return WORLD_SYSTEMS['upper_institutions']['worlds']['asura']


def people(game):
    court = game.sects.get(COURT)
    return {n.id: n for n in court.npcs} if court else {}


def present(npc):
    return bool(npc and npc.alive and npc.world == 'asura' and npc.faction_id in (None, COURT))


def initial(state):
    holders = {str(5-i): f'{COURT}_{i}' for i in range(5)}
    if state['joined'] and state['rank'] > 0:
        holders[str(state['rank'])] = 'player'
    return dict(holders=holders, offices={}, loyalty={}, public_support=50,
                buildings={key: 0 for key in WORKS}, project=None, challenge=None,
                protected_until=state['unit']+8, last_challenge=-100, last_duel=-100,
                reviewed_at=state['unit'], challenger_times={}, decree_at=-100,
                appointment_at=-100)


def ensure(game):
    """One-time additive migration; never recreate dead people or reset ranks."""
    from .institution_state import fresh
    state = game.upper_institutions.get('asura')
    if state is None and not (game.player.world == 'asura' and game.player.realm_index >= 9):
        return False
    state = game.upper_institutions.setdefault('asura', fresh())
    if 'court' in state:
        asura_factions.ensure(state)
        return False
    entity = game.sects.get(COURT)
    if entity:
        existing = people(game)
        for raw in FACTION_NPC_TEMPLATES[COURT]:
            if raw['id'] not in existing:
                from .combat.npc_lifecycle import initialize_native
                npc = SectNpc.from_dict(copy.deepcopy(raw))
                npc.faction_id = COURT
                initialize_native(npc, WORLD_SYSTEMS['transcendent_combat'], now=game.player.age)
                entity.npcs.append(npc)
    state['court'] = initial(state)
    asura_factions.ensure(state)
    sync_titles(game, state)
    return True


def is_king(state):
    return state['joined'] and state.get('court', {}).get('holders', {}).get(str(KING)) == 'player'


def talent(npc, office):
    digest = hashlib.sha256(f'{npc.id}:{office}'.encode()).digest()
    return min(95, 35 + digest[0] % 46 + max(0, npc.realm_index - 9) * 5)


def npc_power(npc):
    root = ROOT_DEFINITIONS.get(npc.spirit_root, {})
    return npc_combat_power(npc, expected_combat_power, float(root.get('efficiency', 1)),
                            ITEM_CATALOG.get(npc.treasure_item_id or '')) * max(.1, npc.combat_factor) * max(.35, 1 - npc.wounds * .15) + npc.family_combat_bonus


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


def sync_titles(game, state):
    court = state['court']
    for identity, npc in people(game).items():
        if not present(npc):
            continue
        titles = [cfg()['ranks'][int(rank)] for rank, holder in court['holders'].items() if holder == identity]
        titles += [OFFICES[key][0] for key, holder in court['offices'].items() if holder == identity]
        npc.title = ' · '.join(titles) if titles else '王庭效命者'


def reconcile(game, state):
    court, roster = state['court'], people(game)
    for rank, identity in list(court['holders'].items()):
        if identity != 'player' and not present(roster.get(identity)):
            court['holders'][rank] = None
    for office, identity in list(court['offices'].items()):
        if not present(roster.get(identity)) or identity == court['holders'].get(str(KING)):
            del court['offices'][office]
    challenge = court['challenge']
    if challenge and (not present(roster.get(challenge['npc_id'])) or
                      state['rank'] != challenge['rank'] or not state['joined']):
        court['challenge'] = None
    sync_titles(game, state)


def change_rank(game, state, rank, *, opponent=None):
    """Exchange adjacent seats; rank zero is an unseated pool of retainers."""
    court, old = state['court'], state['rank']
    holder = opponent if opponent is not None else court['holders'].get(str(rank))
    if opponent is not None and rank:
        previous = next((key for key, value in court['holders'].items() if value == opponent), None)
        if previous and previous not in {str(old), str(rank)}:
            court['holders'][previous] = court['holders'].get(str(rank))
    if old:
        court['holders'][str(old)] = holder
    if rank:
        court['holders'][str(rank)] = 'player'
    state['rank'] = rank
    court['protected_until'] = state['unit'] + 8
    court['challenge'] = None
    if rank == KING:
        state['obligation'] = None
    king_id = court['holders'].get(str(KING))
    court['offices'] = {key:value for key,value in court['offices'].items() if value != king_id}
    sync_titles(game, state)


def vacate(game, state):
    court = state['court']
    for rank, identity in court['holders'].items():
        if identity == 'player':
            court['holders'][rank] = None
    state['rank'] = 0
    court['challenge'] = None
    sync_titles(game, state)


def assessment(game, npc):
    """Estimate actual condition, combat resources, body ward and domain loadout.

    The battle adapter works on a private copy: assessment cannot refill ledgers.
    This runs only once per four elapsed units, never during presentation.
    """
    from .combat_adapter import bind_capabilities, persistent_owners
    from .combat_system import BattleUnit
    preview = copy.deepcopy(game)
    p = preview.player
    units = [BattleUnit('player', p.name, 'player', combat_power(p), p.realm_index, p.path)]
    for row in p.puppets:
        if row.get('alive', True):
            integrity = max(0., min(1., row.get('durability', row.get('corpse_integrity', row.get('control', 100))) / 100))
            units.append(BattleUnit(row['id'], row.get('name', '傀儡'), row.get('type', 'mechanical'),
                row.get('combat_power', 0), row.get('realm_index', p.realm_index), row.get('path', 'dao'), integrity))
    party_ids = {str(r.get('id')) for r in p.party} - {npc.id}
    for identity, companion in persistent_owners(preview, party_ids).items():
        from .combat.npc_lifecycle import read
        if not read(companion, 'alive', True) or read(companion, 'world') != p.world:
            continue
        if isinstance(companion, dict):
            power = expected_combat_power(int(companion.get('realm_index', 0)), int(companion.get('layer', 1)))
        else:
            power = npc_power(companion)
        units.append(BattleUnit(identity, read(companion, 'name', '同行者'), 'companion', power,
                               read(companion, 'realm_index', p.realm_index), read(companion, 'path', 'dao')))
    target = dict(npc_id=npc.id, target_name=npc.name, target_power=npc_power(npc),
                  target_realm_index=npc.realm_index, target_layer=npc.layer, path=npc.path)
    battle = bind_capabilities(preview, units, target, WORLD_SYSTEMS['transcendent_combat']).battle
    scores = dict(player=0., enemy=0.)
    for actor in battle.units.values():
        caps = actor.unit.capabilities
        resource = min(1., caps.current / max(1., caps.capacity))
        domain = min(1., sum(field.strength for field in caps.voisinages) / 400) if resource else 0
        score = actor.unit.power * actor.body * (.65 + .35 * resource) * (1 + domain + .3 * (caps.ward_tier - 1))
        if actor.unit.id == 'player':
            score *= .7 + .3 * min(1., max(0., p.mp / max(1., max_mp(p))))
        scores[actor.unit.side] += score
    return scores


def tick(game, state):
    from .institution_state import record, policy
    reconcile(game, state)
    court, unit = state['court'], state['unit']
    current = policy(game, state)
    court['public_support'] = min(100, max(0, court['public_support'] + current.get('support', 0)))
    benefit = benefits(game, state)
    gross = int(WORLD_SYSTEMS['upper_institutions']['unit_income'] * benefit['revenue'] * current.get('revenue', 1))
    state['treasury'] += max(0, gross - benefit['wages'])
    project = court['project']
    if project and unit >= project['complete_at']:
        court['buildings'][project['id']] += 1
        record(game, state, f"{WORKS[project['id']][0]}竣工，升至 {court['buildings'][project['id']]} 级。")
        court['project'] = None
    challenge = court['challenge']
    if challenge and unit > challenge['deadline']:
        npc = people(game)[challenge['npc_id']]
        asura_factions.settle_duel(state, challenge, False)
        change_rank(game, state, state['rank'] - 1, opponent=npc.id)
        record(game, state, f'血战战书逾期未应，依王庭律让位于{npc.name}。')
    asura_factions.tick(game, state, people(game))
    if (not state['joined'] or state['rank'] <= 0 or not game.player.alive or court['challenge']
            or unit < court['protected_until'] or unit - court['last_challenge'] < 12
            or unit - court['reviewed_at'] < 4):
        return
    court['reviewed_at'] = unit
    if game.pending_event or game.active_trial or game.player.imprisonment or game.player.ghost_captor:
        return
    roster = people(game)
    lower = court['holders'].get(str(state['rank'] - 1))
    seated = set(court['holders'].values())
    candidates = [n for n in roster.values() if present(n) and
                  (n.id == lower if state['rank'] > 1 else n.id not in seated)]
    candidates = [n for n in candidates if unit - court['challenger_times'].get(n.id, -100) >= 24]
    if not candidates:
        return
    npc = max(candidates, key=npc_power)
    scores = assessment(game, npc)
    loyalty = court['loyalty'].get(npc.id, 50)
    # A clear advantage is needed, particularly for trusted appointees.
    if scores['enemy'] < scores['player'] * (1.15 + max(0, loyalty - 50) / 100):
        return
    roll = hashlib.sha256(f'{game.seed}:{npc.id}:{unit}:blood'.encode()).digest()[0]
    if roll >= 64:
        return
    court['last_challenge'] = unit
    court['challenger_times'][npc.id] = unit
    court['challenge'] = dict(npc_id=npc.id, rank=state['rank'], issued_at=unit, deadline=unit+4,
                              player_score=round(scores['player']), challenger_score=round(scores['enemy']))
    record(game, state, f'{npc.name}评估双方实力后递上换位战书；须在第 {unit+4} 单位前回王庭应战或让位。')


def act(engine, game, state, action, target):
    """Actions return a journal entry; caller persists the single transaction."""
    from ..runtime import decode_rng, encode_rng
    reconcile(game, state)
    court = state['court']
    if action in ('blood_duel', 'answer_duel', 'yield_duel'):
        incoming = action != 'blood_duel'
        challenge = court['challenge']
        if incoming and not challenge:
            raise ValueError('当前没有待回应的血战战书')
        if not incoming and challenge:
            raise ValueError('请先处理下级递来的血战战书')
        if not incoming and state['unit'] - court['last_duel'] < 2:
            raise ValueError('两次主动血战须相隔两个政历单位')
        rank = state['rank'] - 1 if incoming else state['rank'] + 1
        if rank not in range(KING+1):
            raise ValueError('只能挑战上一级爵位')
        identity = challenge['npc_id'] if incoming else court['holders'].get(str(rank))
        if target and target != identity:
            raise ValueError('爵位持有人已经变化，请刷新后再挑战')
        npc = people(game).get(identity)
        if not present(npc):
            if incoming:
                raise ValueError('挑战者已经无法参战')
            change_rank(game, state, rank)
            court['last_duel'] = state['unit']
            return f"上一级爵位空缺，你接任{cfg()['ranks'][rank]}。"
        if action == 'yield_duel':
            asura_factions.settle_duel(state, challenge, False)
            change_rank(game, state, rank, opponent=identity)
            return f"你承认{npc.name}的挑战，让出爵位，降为{cfg()['ranks'][rank]}。"
        if game.player.hp < max_hp(game.player) * .25:
            raise ValueError('伤势过重，须恢复至至少四分之一气血才能应战')
        target_data = dict(npc_id=npc.id, faction_id=COURT, target_name=npc.name,
            target_power=engine._npc_power(npc), target_realm_index=npc.realm_index,
            target_layer=npc.layer, path=npc.path, race=npc.race, world=npc.world,
            combat_type='cultivator', objective='repel', enemy_objective='repel',
            player_defending=incoming, exclude_allied_ids=[npc.id])
        rng = decode_rng(game.seed, game.rng_state)
        result, summary = engine._combat(game, target_data, False, rng)
        game.rng_state = encode_rng(rng)
        court['last_duel'] = state['unit']
        # A nonlethal domain duel can stop at the engine's safety floor even
        # after one side has lost all morale. The court recognises surrender,
        # never substitutes a power-ratio roll for the actual battle.
        report = game.last_combat_report or {}
        if result == 'stalemate':
            updates = report.get('capability_updates', [])
            enemies = [u for u in updates if u.get('side') == 'enemy']
            own = next((u for u in updates if u.get('id') == 'player'), {})
            rounds = report.get('rounds', [])
            morale = rounds[-1].get('voisinage', {}).get('morale', {}) if rounds else {}
            if own.get('suppressed') or morale.get('player', 100) <= 0:
                result = 'defeat'
            elif enemies and all(u.get('suppressed') or morale.get(u['id'], 100) <= 0 for u in enemies):
                result = 'victory'
            if result != 'stalemate':
                report.update(result=result, outcome=result, result_grade='血战胜出' if result == 'victory' else '血战落败')
                summary = '魔域交锋后，一方被镇压或战意耗尽，王庭裁定认负，停止追击。'
        # A stalemate or unusable technique is not a decision on ownership.
        if result in ('stalemate', 'technique_blocked'):
            return '血战未分胜负，爵位与战书保留。' + summary
        won = result == 'victory'
        asura_factions.settle_duel(state, challenge, won)
        court['challenge'] = None
        court['protected_until'] = state['unit'] + 8
        if won:
            npc.wounds = min(4, max(1, npc.wounds))
        else:
            game.player.hp = max(1, min(game.player.hp, max_hp(game.player) * .85))
        if won != incoming:
            change_rank(game, state, rank, opponent=identity)
        game.last_combat_report['title'] = f'换位血战 · {npc.name}'
        return (f"血战{'获胜' if won else '落败'}；现爵位为{cfg()['ranks'][state['rank']]}，双方保留性命。" + summary)
    if not is_king(state):
        raise ValueError('只有在位修罗王可以办理此项内政')
    if court['challenge']:
        raise ValueError('须先回应换位战书，再行使王权')
    if action in {'faction_decree', 'royal_tribute'}:
        roster = {**game.world_npcs, **game.notable_npcs,
                  **{n.id: n for sect in game.sects.values() for n in sect.npcs}}
        return asura_factions.act(game, state, action, target, roster)
    if action == 'appoint':
        office, separator, identity = target.partition(':')
        if not separator or office not in OFFICES:
            raise ValueError('请选择有效官职与人选')
        if state['unit'] - court['appointment_at'] < 1:
            raise ValueError('每个政历单位只能调整一项人事')
        if not identity:
            if office not in court['offices']:
                raise ValueError('该官职已经空缺')
            del court['offices'][office]
            text = f'免去{OFFICES[office][0]}，停止该职俸禄与加成。'
        else:
            npc = people(game).get(identity)
            if not present(npc) or identity in court['offices'].values() or identity == court['holders'].get(str(KING)):
                raise ValueError('人选须为在世廷臣，同一人不得兼任多个官职')
            if state['treasury'] < 60000:
                raise ValueError('任命须府库 60,000 灵石')
            state['treasury'] -= 60000
            court['offices'][office] = identity
            court['loyalty'][identity] = min(100, court['loyalty'].get(identity, 50) + 10)
            text = f'任命{npc.name}为{OFFICES[office][0]}，才干 {talent(npc, office)}，每单位俸禄 30,000 灵石。'
        court['appointment_at'] = state['unit']
        sync_titles(game, state)
        return text
    if action == 'build':
        if target not in WORKS or court['project'] or court['buildings'][target] >= 3:
            raise ValueError('同时只能营建一处，每项上限三级')
        cost = 400000 * (court['buildings'][target] + 1)
        if state['treasury'] < cost:
            raise ValueError('营建府库不足')
        state['treasury'] -= cost
        court['project'] = dict(id=target, complete_at=state['unit']+4, cost=cost)
        return f'{WORKS[target][0]}开工，支出 {cost:,} 灵石，四单位后竣工。'
    if action == 'decree':
        if target not in DECREES or state['unit'] - court['decree_at'] < 4:
            raise ValueError('请选择内政决策；两次决策须相隔四单位')
        title, cost, description = DECREES[target]
        if state['treasury'] < cost or (target == 'levy' and court['public_support'] < 40):
            raise ValueError('府库或民心不足以执行此决策')
        state['treasury'] -= cost
        if target == 'relief':
            court['public_support'] = min(100, court['public_support'] + 15)
        elif target == 'levy':
            court['public_support'] -= 15
            state['treasury'] += 300000
        else:
            for npc in people(game).values():
                if present(npc):
                    court['loyalty'][npc.id] = min(100, court['loyalty'].get(npc.id, 50) + 12)
        court['decree_at'] = state['unit']
        return f'颁行{title}：{description}。'
    raise ValueError('未知王庭事务')


def public(game, state):
    court = copy.deepcopy(state.get('court') or initial(state))
    view_state = dict(state, court=court)
    roster = people(game)
    rows = []
    for rank in range(KING, 0, -1):
        identity = court['holders'].get(str(rank))
        npc = roster.get(identity)
        occupied = identity == 'player' or present(npc)
        rows.append(dict(rank=rank, title=cfg()['ranks'][rank], id=identity if occupied else None,
                         name=game.player.name if identity == 'player' else npc.name if occupied else '虚位待授',
                         player=identity == 'player', present=occupied,
                         realm_index=game.player.realm_index if identity == 'player' else npc.realm_index if occupied else None))
    challenge = court['challenge']
    if challenge:
        npc = roster.get(challenge['npc_id'])
        if present(npc):
            challenge['name'] = npc.name
        else:
            challenge = None
    return dict(**{k:v for k,v in court.items() if k not in {'challenge', 'factions'}}, challenge=challenge,
        king=is_king(view_state), seats=rows, effects=benefits(game, view_state),
        factions=asura_factions.public(game, view_state),
        policy_categories=[dict(id=k, name=v) for k,v in asura_factions.CATEGORIES.items()],
        policy_categories_by_id=asura_factions.POLICY_CATEGORIES,
        tribute_candidates=[dict(id=n.id, name=n.name) for n in
            {**game.world_npcs, **game.notable_npcs, **{n.id:n for s in game.sects.values() for n in s.npcs}}.values()
            if n.alive and n.roster_state == 'active' and n.world == 'asura'],
        candidates=[dict(id=n.id, name=n.name, title=n.title, loyalty=court['loyalty'].get(n.id, 50),
                        skills={key:talent(n,key) for key in OFFICES}) for n in roster.values() if present(n)],
        office_definitions=[dict(id=key, name=value[0], description=value[1]) for key,value in OFFICES.items()],
        works=[dict(id=key, name=value[0], description=value[1], level=court['buildings'][key],
                    cost=400000*(court['buildings'][key]+1)) for key,value in WORKS.items()],
        decrees=[dict(id=key, name=value[0], cost=value[1], description=value[2]) for key,value in DECREES.items()])
