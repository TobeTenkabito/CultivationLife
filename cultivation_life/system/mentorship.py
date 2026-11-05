"""Personal schools reference original people; reads never instantiate a school."""
from __future__ import annotations

import random
from copy import deepcopy

from ..content_registry import WORLD_SYSTEMS, ITEM_CATALOG, REALMS
from ..models import HistoryRecord, SectNpc
from ..mentorship_schema import RANKS, LABELS
from ..npc_custody import is_free
from ..relationship_records import find_person
from ..spatial_people import accessible, instance_of
from ..rules import add_item, can_player_practice_technique, learn_technique, opportunity_required
from .faction_geography import person_site
from .spatial_capabilities import site_key

def person(game, identity):
    return game.player if identity == 'player' else find_person(game, identity, include_inactive=True)


def capacity(game, teacher, rank):
    if rank == 'registered': return None
    if rank == 'heir': return 1
    if rank == 'personal': return 3
    owner = person(game, teacher)
    realm = getattr(owner, 'realm_index', 0)
    if teacher == 'player': realm = max(realm, int((owner.sealed_cultivation or {}).get('realm_index', 0)))
    return 4 + realm // 2


def schools(game):
    return game.mentorship_state.get('schools', {})


def active(game, teacher, identity, row):
    if row.get('status') != 'active': return False
    owner, student = person(game, teacher), person(game, identity)
    if not owner or not student or not owner.alive or not student.alive: return False
    if identity == 'player': return bool(game.player.master and game.player.master.get('id') == teacher)
    if teacher == 'player': return any(r.get('id') == identity for r in game.player.disciples)
    return is_free(student)


def rows(game, teacher):
    return {key: row for key, row in schools(game).get(teacher, {}).get('students', {}).items()
            if active(game, teacher, key, row)}


def record(game, teacher, identity):
    return schools(game).get(teacher, {}).get('students', {}).get(identity)


def rank_of(game, teacher, identity):
    row = record(game, teacher, identity)
    if row and active(game, teacher, identity, row): return row['rank']
    # Existing structure-12 relationships have actually been admitted. Pure reads
    # project their first rank without generating people or writing a ledger.
    if identity == 'player' and game.player.master and game.player.master.get('id') == teacher:
        return 'true' if sum(r['rank'] == 'true' for r in rows(game, teacher).values()) < capacity(game, teacher, 'true') else 'registered'
    if teacher == 'player':
        ids = [r['id'] for r in game.player.disciples if r.get('alive', True)]
        if identity in ids: return 'true' if ids.index(identity) < capacity(game, teacher, 'true') else 'registered'
    return None


def admission_reason(game, teacher, identity):
    if teacher == identity: return '不能拜自己为师'
    parents = {child: master for master in schools(game) for child in rows(game, master)}
    if game.player.master and game.player.master.get('alive', True): parents['player'] = game.player.master['id']
    for r in game.player.disciples:
        if r.get('alive', True): parents[r['id']] = 'player'
    if identity in parents and parents[identity] != teacher: return '此人已有在世师承'
    seen = {identity}
    cursor = teacher
    while cursor:
        if cursor in seen: return '不能形成循环师承'
        seen.add(cursor)
        cursor = parents.get(cursor)
    return ''


def _entry(game, rank):
    year = game.player.age
    period = max(1, int(WORLD_SYSTEMS['time_units'][str(game.player.realm_index)])) * 5
    return dict(rank=rank, status='active', loyalty=60, discontent=0, merit=0,
                joined=year, period=period, due=year + period, last_tick=year,
                cycle=0, fulfilled=-1, collected=-1, promoted=-1, honored=-1, benefit_cycle=-1,
                benefit_gain=0, benefit_keys=[], support_cycle=-1, support_used=0, warned=False,
                discord_cycle=-1, discord_gain=0)


def _admit(game, teacher, identity, rank=None):
    school = game.mentorship_state.setdefault('schools', {}).setdefault(teacher, {'students': {}, 'initialized': False})
    if identity in school['students']:
        row = school['students'][identity]
        if active(game, teacher, identity, row): return row
        # Rejoining preserves the old counters and obligations; no reset exploit.
        row['status'] = 'active'
        row['rank'] = 'registered'
        prior = row.pop('former_relation', None)
        relation = game.player.master if identity == 'player' else next((r for r in game.player.disciples if r['id'] == identity), None) if teacher == 'player' else None
        if prior and relation is not None:
            for key, value in prior.items():
                if key == 'items':
                    held = relation.setdefault('items', {})
                    for item_id, count in value.items(): held[item_id] = held.get(item_id, 0) + count
                elif key not in {'id', 'npc_id'}: relation.setdefault(key, value)
        return row
    rank = rank or ('true' if sum(r['rank'] == 'true' for r in rows(game, teacher).values()) < capacity(game, teacher, 'true') else 'registered')
    row = _entry(game, rank)
    school['students'][identity] = row
    return row


def admit(game, teacher, identity):
    reason = admission_reason(game, teacher, identity)
    if reason: raise ValueError(reason)
    # Register existing player students first, so adopting an older structure-12
    # game cannot hand out a second set of true-disciple seats.
    if teacher == 'player':
        for relation in game.player.disciples:
            if relation.get('alive', True) and record(game, teacher, relation['id']) is None:
                _admit(game, teacher, relation['id'])
    row = _admit(game, teacher, identity)
    if identity == 'player':
        initialize_peers(game, teacher)
        if row['rank'] == 'registered':
            restricted = {teacher, *rows(game, teacher)}
            game.player.party = [r for r in game.player.party if r.get('id') not in restricted]
            game.player.joint_friend_crossing = [r for r in game.player.joint_friend_crossing if r.get('id') not in restricted]
    return row


def initialize_peers(game, teacher):
    school = schools(game)[teacher]
    if school['initialized']: return
    master = person(game, teacher)
    if not master or not game.player.master or game.player.master['id'] != teacher: return
    school['initialized'] = True
    # Sparse personal school, born at the teacher's actual address. No recursive
    # families, no periodic refill, no relocation of existing inhabitants.
    from ..npc_names import person_name
    from .combat.npc_lifecycle import initialize_native
    rng = random.Random(f'mentorship:{game.seed}:{teacher}')
    for index in range(2):
        identity = f'school:{teacher}:{index}'
        if find_person(game, identity, include_inactive=True): continue
        realm = max(0, master.realm_index - 1)
        span = REALMS[realm].lifespan
        lifespan = rng.randint(*span) if span else None
        age = max(18, min(master.age - 1, lifespan // 3 if lifespan else master.age // 3))
        peer = SectNpc(identity, person_name(rng), f'{master.name}的门人', realm,
                       max(1, master.layer - 1), age,
                       lifespan, spirit_root=master.spirit_root, path=master.path,
                       race=master.race, world=master.world,
                       location_id=person_site(game, master), gender='female' if index else 'male')
        game.notable_npcs[identity] = peer
        instance = instance_of(game, master.id)
        if instance is not None: game.spatial_state['instances'][instance].setdefault('npc_ids', []).append(identity)
        initialize_native(peer, WORLD_SYSTEMS.get('transcendent_combat', {}), now=game.player.age)
        row = _admit(game, teacher, identity, 'personal' if index == 0 else 'true')
        # These are the teacher's existing students, even if the player only
        # registers the old school years later. Registration is not admission.
        row['joined'] = school['students']['player']['joined']


def contact_reason(game, identity, *, rebellion_event=False):
    p, npc = game.player, person(game, identity)
    if game.map_journey or game.guixu_state.get('player_session'): return '请先结束行旅或离开归墟亲自副本'
    pending = game.pending_event and not (rebellion_event and game.pending_event.get('id') == 'EVT_MENTORSHIP_REBELLION_001')
    if not p.alive or pending or game.active_trial or p.imprisonment or p.ghost_captor or (game.guixu_state.get('player_session') or {}).get('trapped'):
        return '请先结束事件、战斗或拘禁'
    if not npc or not is_free(npc) or getattr(npc, 'custody', None) or not accessible(game, npc):
        return '人物不在当前界面或同一空间，或已失去自由'
    if not person_site(game, npc) or person_site(game, npc) != site_key(game): return '师门事务须在同一实际地点办理'
    from ..person_assignments import require_unassigned
    try:
        require_unassigned(game, identity)
        require_unassigned(game, 'player')
    except ValueError as exc: return str(exc)
    if game.trial_site_state.get('active'): return '请先离开正在探索的试境'
    if game.heavens_state.get('runtime'):
        from .heavens.state import active_task
        if active_task(game.heavens_state['runtime']): return '请先结束诸天亲自任务'
    if identity in game.intrigue_state.get('npc_prisons', {}): return '人物正在监禁中'
    return ''


def require_contact(game, identity):
    reason = contact_reason(game, identity)
    if reason: raise ValueError(reason)


def school_restriction(game, identity):
    master = game.player.master
    if not master or rank_of(game, master['id'], 'player') != 'registered': return ''
    if identity == master['id'] or identity in rows(game, master['id']):
        return '记名弟子无师门福利、交流或同行权利，请先申请晋位'
    return ''


def school_contact_reason(game, identity):
    master = game.player.master
    if master and (identity == master['id'] or identity in rows(game, master['id'])):
        return contact_reason(game, identity)
    return ''


def displease(game, identity):
    master = game.player.master
    if not master or (identity != master['id'] and identity not in rows(game, master['id'])): return ''
    row = admit(game, master['id'], 'player')
    if row['discord_cycle'] != row['cycle']: row.update(discord_cycle=row['cycle'], discord_gain=0)
    gain = min(5, 15 - row['discord_gain'])
    row['discord_gain'] += gain
    row['discontent'] = min(100, row['discontent'] + gain)
    return f' 这次师门争执已被记录，师门不满 +{gain}（每周期争执累计最多15）。' if gain else ''


def end(game, teacher, identity, status):
    row = record(game, teacher, identity)
    relation = game.player.master if identity == 'player' else next((r for r in game.player.disciples if r['id'] == identity), None) if teacher == 'player' else None
    if identity == 'player' and relation and relation['id'] != teacher: relation = None
    if row is None and relation is not None: row = _admit(game, teacher, identity, rank_of(game, teacher, identity))
    if row:
        row['status'] = status
        if 'advanced' in row: row['advanced'].update(pact_possession=False, pact_avatar=False, plot=False)
        if relation is not None:
            from ..relationship_schema import PERSON_FIELDS, LABEL_FIELDS
            # Move the sole relation metadata (including gifts) to its history.
            # The actor and all grown attributes remain on the original NPC.
            row['former_relation'] = {key: value for key, value in relation.items() if key not in PERSON_FIELDS | LABEL_FIELDS}
    if identity == 'player' and game.player.master and game.player.master['id'] == teacher:
        game.player.master = None
    if teacher == 'player': game.player.disciples = [r for r in game.player.disciples if r['id'] != identity]


def end_person_relations(game, identity, status='departed'):
    """Old custody, violence and departure routes must close the same ledger."""
    if game.player.master and game.player.master.get('id') == identity:
        end(game, identity, 'player', status)
    if any(row.get('id') == identity for row in game.player.disciples):
        end(game, 'player', identity, status)


def replace_master(game, relation):
    """Admitted new teacher: archive the previous real relation before replacing it."""
    previous = game.player.master
    if previous and previous['id'] != relation['id']:
        end(game, previous['id'], 'player', 'departed')
    game.player.master = relation


def benefit(game, identity, key, gain):
    if not any(r['id'] == identity for r in game.player.disciples): return
    row = admit(game, 'player', identity)
    if row['benefit_cycle'] != row['cycle']:
        row.update(benefit_cycle=row['cycle'], benefit_gain=0, benefit_keys=[])
    if key in row['benefit_keys']: return
    gain = max(0, min(gain, 12 - row['benefit_gain']))
    if not gain: return
    row['benefit_keys'].append(key)
    row['benefit_gain'] += gain
    row['loyalty'] = min(100, row['loyalty'] + gain)


def advance(game):
    from ..regional_context import region, historical
    if historical(game) or (region(game) and region(game) != game.player.world): return
    year = game.player.age
    for teacher, school in list(schools(game).items()):
        for identity, row in list(school['students'].items()):
            if not active(game, teacher, identity, row): continue
            elapsed = max(0, year - row['last_tick'])
            if not elapsed: continue
            row['last_tick'] = year
            target = teacher if identity == 'player' else identity
            # No absentee penalties, catches or remote rewards during travel,
            # independent spaces, missions or custody. Clock remains monotonic.
            if contact_reason(game, target):
                row['due'] += elapsed
                continue
            if year < row['due']: continue
            periods = 1 + (year - row['due']) // row['period']
            previous_cycle = row['cycle']
            row['cycle'] += periods
            row['due'] += periods * row['period']
            if identity == 'player':
                was_warned = row['warned']
                if row['rank'] != 'registered' and row['fulfilled'] != previous_cycle:
                    row['discontent'] = min(100, row['discontent'] + 15 * RANKS.index(row['rank']))
                row['warned'] = row['discontent'] >= 60
                if was_warned and row['discontent'] >= 100:
                    end(game, teacher, identity, 'expelled')
                    log(game, 'expelled', '师门不满经预警后仍未缓解，你已被逐出师门。')
                elif row['warned']:
                    log(game, 'warning', '师门已发出不满警告，请及时履约或呈交心得化解争执，以免被逐。')
            elif row['rank'] == 'registered' and row['loyalty'] < 20:
                end(game, teacher, identity, 'departed')
                log(game, 'departed', f'{getattr(person(game, identity), "name", "记名弟子")}因忠诚过低自行离门。')


def duty_cost(game, row):
    return round(max(1, opportunity_required(game.player) * .02 * RANKS.index(row['rank'])), 1)


def graduation_reason(game, teacher, row):
    reason = contact_reason(game, teacher)
    if reason: return reason
    if row['rank'] == 'registered' or (row['merit'] < 3 and game.player.realm_index < person(game, teacher).realm_index):
        return '正式出师需要非记名身份，且履约资历达到3或境界达到师父当前境界'
    return ''


def teachable_arts(game, npc):
    """Actual learned arts, filtered through the existing player eligibility."""
    from .npc_techniques import levels, resolve
    from .spatial import current
    from ..models import Technique
    scene = current(game) if game.player.world in {'lost', 'rift'} else None
    local = {entry['id']: Technique(**entry) for entry in scene.get('techniques', [])} if scene else {}
    known = {t.id for t in game.player.known_techniques}
    return [art for key in sorted(levels(npc)) if key not in known
            for art in [local.get(key) or resolve(game, key)]
            if art and can_player_practice_technique(game.player, art)]


def grant_support(game, npc, kind, gain=0):
    """Shared master/peer settlement; items leave their original holder once."""
    if kind == 'consult':
        game.player.opportunity += gain
        return f'{npc.name}悉心指点，机缘 +{gain:g}。'
    if kind == 'item':
        item = ITEM_CATALOG.get(npc.treasure_item_id)
        if not item or npc.treasure_looted: raise ValueError('对方当前没有可赠予的实际随身物品')
        add_item(game.player, item.id)
        npc.treasure_looted = True
        npc.treasure_item_id = None
        return f'{npc.name}将随身的{item.name}交给你。'
    candidates = teachable_arts(game, npc)
    if not candidates: raise ValueError('对方没有已掌握且适合传授给你的新功法')
    art = candidates[0]
    learn_technique(game.player, art)
    return f'{npc.name}传授其所学《{art.name}》。'


PEER_ACTIONS = {'peer_consult':'请教修行', 'peer_spar':'切磋论道',
                'peer_item':'索要物品', 'peer_technique':'索要功法'}


def peer_reason(game, identity, action):
    if action not in PEER_ACTIONS: return '未知同门事务'
    master = game.player.master
    if not master: return '你尚未正式拜师'
    teacher = master['id']
    own = record(game, teacher, 'player')
    peer = rows(game, teacher).get(identity)
    if not own or not active(game, teacher, 'player', own) or identity == 'player' or not peer:
        return '此人不是同一师门的在籍同门'
    if own['rank'] == 'registered' or peer['rank'] == 'registered': return '记名弟子无师门福利或交流权利'
    if peer['joined'] > own['joined']: return '此人入门晚于你，并非师兄师姐'
    reason = contact_reason(game, identity)
    if reason: return reason
    if own.get('peer_requests', {}).get(identity, {}).get(action) == own['cycle']:
        return '本周期已向这位同门办理过此项事务'
    npc = person(game, identity)
    required = {'peer_consult':0, 'peer_spar':0, 'peer_item':20, 'peer_technique':30}[action]
    if (npc.affinity or 0) < required: return f'此项事务需要同门好感至少{required}'
    if action == 'peer_spar' and game.player.hp <= 0: return '当前伤势无法切磋'
    if action == 'peer_item' and (npc.treasure_looted or npc.treasure_item_id not in ITEM_CATALOG):
        return '对方当前没有可赠予的实际随身物品'
    if action == 'peer_technique' and not teachable_arts(game, npc):
        return '对方没有已掌握且适合传授给你的新功法'
    return ''


def interact_peer(engine, game, identity, action, rng):
    reason = peer_reason(game, identity, action)
    if reason: raise ValueError(reason)
    own = record(game, game.player.master['id'], 'player')
    npc = person(game, identity)
    gain = round(max(1, opportunity_required(game.player) * .01), 1)
    if action == 'peer_spar':
        power = engine._npc_power(npc)
        target = dict(target_name=npc.name, target_power=power, primary_power=power,
                      target_realm_index=npc.realm_index, target_layer=npc.layer,
                      npc_id=npc.id, path=npc.path, race=npc.race, world=npc.world,
                      faction_id=npc.faction_id, combat_type='cultivator', action='spar',
                      mentorship_contest=True, non_story_combat=True)
        _, summary = engine._combat(game, target, False, rng)
        if game.player.alive:
            game.player.opportunity += gain
            summary += f' 切磋有所领悟，机缘 +{gain:g}；本次不改变师门位次。'
    else:
        summary = grant_support(game, npc, action.removeprefix('peer_'), gain)
    own.setdefault('peer_requests', {}).setdefault(identity, {})[action] = own['cycle']
    return summary


def request_support(game, kind):
    if not isinstance(kind, str) or kind not in {'consult', 'item', 'technique'}: raise ValueError('未知师门福利')
    if not game.player.master: raise ValueError('你尚无师承')
    teacher = game.player.master['id']
    require_contact(game, teacher)
    reason = school_restriction(game, teacher)
    if reason: raise ValueError(reason)
    if game.player.master.get('last_requests', {}).get(kind) == game.player.age:
        raise ValueError('本年度已经向师父提出过这类请求')
    row = record(game, teacher, 'player') or _entry(game, rank_of(game, teacher, 'player'))
    rank = RANKS.index(row['rank'])
    used = row['support_used'] if row['support_cycle'] == row['cycle'] else 0
    if used >= rank: raise ValueError('本周期师门指导额度已用尽')
    master = person(game, teacher)
    summary = grant_support(game, master, kind, round(opportunity_required(game.player) * (.02 + .02 * rank), 1))
    row = admit(game, teacher, 'player')
    row.update(support_cycle=row['cycle'], support_used=used + 1)
    game.player.master.setdefault('last_requests', {})[kind] = game.player.age
    return summary


def log(game, action, summary):
    game.history.append(HistoryRecord('SYS_MENTORSHIP', 1, game.player.age, '师门事务', action,
                                      action, summary, {}, ['system', 'relationship', 'mentorship']))


def public(game):
    result = dict(ranks=LABELS, master=None, disciples=[], peers=[], history=[])
    master = game.player.master
    def project(teacher, identity):
        npc = person(game, identity)
        saved = record(game, teacher, identity)
        row = deepcopy(saved) if saved else _entry(game, rank_of(game, teacher, identity) or 'registered')
        row.update(id=identity, name=getattr(npc, 'name', '无法确认的人物'),
                   rank_name=LABELS[row['rank']], reason=contact_reason(game, teacher if identity == 'player' else identity))
        if npc and identity != 'player':
            from .npc_development.portraits import FIELDS
            row['portrait'] = {key: getattr(npc, key, None) for key in FIELDS}
            row.update(row['portrait'])
        row['duty_cost'] = duty_cost(game, row) if row['rank'] != 'registered' else 0
        row['honor_cost'] = duty_cost(game, {**row, 'rank':'true'})
        row['support_limit'] = RANKS.index(row['rank'])
        row['support_remaining'] = max(0, row['support_limit'] - (row['support_used'] if row['support_cycle'] == row['cycle'] else 0))
        return row
    if master and master.get('alive', True):
        result['master'] = project(master['id'], 'player')
        result['master'].update(teacher_id=master['id'], teacher_name=master.get('name'),
                                teacher_affinity=getattr(person(game, master['id']), 'affinity', 0) or 0,
                                graduation_reason=graduation_reason(game, master['id'], result['master']),
                                initialized=bool(schools(game).get(master['id'], {}).get('initialized')))
        from .npc_development.portraits import FIELDS
        result['master']['teacher_portrait'] = {key:getattr(person(game, master['id']),key,None) for key in FIELDS}
        result['peers'] = [project(master['id'], key) for key in rows(game, master['id']) if key != 'player']
        for peer in result['peers']:
            senior = peer['joined'] <= result['master']['joined']
            peer['kinship'] = ('师姐' if peer.get('gender') == 'female' else '师兄') if senior else ('师妹' if peer.get('gender') == 'female' else '师弟')
            peer['affinity'] = getattr(person(game, peer['id']), 'affinity', 0) or 0
            peer['interactions'] = [dict(action=action, label=label, reason=peer_reason(game, peer['id'], action)) for action, label in PEER_ACTIONS.items()]
    result['disciples'] = [project('player', r['id']) for r in game.player.disciples if r.get('alive', True)]
    result['capacity'] = {rank: capacity(game, 'player', rank) for rank in RANKS}
    for teacher, school in schools(game).items():
        for identity, row in school['students'].items():
            if not active(game, teacher, identity, row) and (teacher == 'player' or identity == 'player'):
                result['history'].append(dict(teacher_id=teacher, id=identity, rank_name=LABELS[row['rank']], status=row['status'],
                    name=getattr(person(game, identity), 'name', '昔日门人'), teacher_name=getattr(person(game, teacher), 'name', '昔日师父')))
    return result
