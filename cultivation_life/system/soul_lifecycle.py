"""One base-game body/soul lifecycle, shared by ordinary and spatial time."""
from ..soul_rules import wandering, body_cap, soul_cap, assimilation_cost, rebellion_chance
from ..content_registry import WORLD_SYSTEMS, REALMS
from ..models import HistoryRecord, Item
from ..relationship_records import find_person
from ..npc_custody import kill_person


def replace_rank(player, rank, layer):
    """Update recoverable rank snapshots too; seals remain valid return tickets."""
    previous = (player.realm_index, player.layer)
    player.realm_index, player.layer = rank, layer
    player.opportunity = 0.
    player.awaiting_major_breakthrough = player.awaiting_minor_breakthrough = False
    for snapshot in (player.cultivation_suppression, player.sealed_cultivation):
        if snapshot:
            snapshot.update(realm_index=rank, layer=layer)
            if snapshot is player.cultivation_suppression:
                snapshot.update(opportunity=0., awaiting_major_breakthrough=False,
                                awaiting_minor_breakthrough=False, awaiting_ascension=False)
            player.realm_index, player.layer = min(previous, (rank,layer))
    if player.sealed_cultivation and player.sealed_cultivation.get('visit_only'):
        player.sealed_cultivation.update(realm_index=player.realm_index,layer=player.layer)


def record(game, text, changes=None):
    game.history.append(HistoryRecord('SYS_SOUL', 1, game.player.age, '神魂与元婴', None,
                                      'settled', text, changes or {}, ['system', 'soul']))


def unit_years(player):
    return int(WORLD_SYSTEMS['time_units'][str(player.realm_index)])


def address(game):
    # The instance reference is a location constraint, never a transport ticket.
    return dict(world=game.player.world, location=game.player.location_id,
                instance=game.spatial_state.get('current') if game.player.world in {'lost', 'rift'} else None)


def leave_body(game, *, destroyed=False):
    p = game.player
    if wandering(p) and not destroyed:
        raise ValueError('已经处于神游状态')
    p.spirit_state = dict(mode='wandering', body_intact=not destroyed,
        entered=p.age, deadline=p.age + unit_years(p), address=address(game))
    if destroyed:
        p.body_training = 0
        p.body_progress = 0.
        p.awaiting_body_breakthrough = False
        p.body_energy = 0.
        from ..rules import max_hp
        p.hp = max(1., min(max_hp(p), max(p.hp, max_hp(p) * .25)))
    record(game, '肉身已毁，炼体归零。' if destroyed else '元婴离体，肉身留在原处。',
           dict(body_destroyed=True, lost_realm=survival_rank(p)) if destroyed else None)


def second_person(game):
    row = game.player.nascent_state.get('second')
    npc = find_person(game, row['id'], include_inactive=True) if row else None
    if (npc and npc.alive and npc.roster_state == 'held'
            and (npc.custody or {}).get('holder_id') == game.id
            and (npc.custody or {}).get('kind') == 'second_nascent'
            and row['integrity'] > 0
            and (second_lifespan(npc) is None or second_age(game, npc) < second_lifespan(npc))):
        return npc
    return None


def second_lifespan(npc):
    # Below Void Refinement the extracted soul retains its original finite life.
    if npc.realm_index >= 6:
        return None
    return npc.lifespan if npc.lifespan is not None else REALMS[npc.realm_index].lifespan[1]


def second_age(game, npc):
    row = game.player.nascent_state['second']
    return npc.age + max(0, game.player.age - row.get('age_year', game.player.age))


def settle_second(game):
    """Age the same held actor once by elapsed personal/world time, even in space."""
    row = game.player.nascent_state.get('second')
    if not row:
        return
    npc = find_person(game, row['id'], include_inactive=True)
    if npc and npc.alive:
        npc.age = second_age(game, npc)
        row['age_year'] = game.player.age
        npc.lifespan = second_lifespan(npc)
    if not second_person(game):
        consume_second(game, '第二元婴寿尽或已经消散')
        record(game, '第二元婴寿尽或已经消散，托管装备已返还。')


def lifespan_exhausted(player):
    from .possession_system import current_body_age
    return player.lifespan is not None and current_body_age(player) >= player.lifespan


def survival_rank(player):
    source = player.cultivation_suppression or player.sealed_cultivation or {}
    return source.get('realm_index', player.realm_index)


def try_wandering(game):
    """A usable original soul is required; a failed soul cannot leave again."""
    p = game.player
    if wandering(p) or p.soul_energy <= 0 or p.ghost_captor:
        return False
    core_path = (p.ghost_core_state or {}).get('path', p.path)
    if core_path == 'ghost':
        floor = float(WORLD_SYSTEMS.get('ghost_cultivation', {}).get('soul_death_intrinsic_floor', 1.))
        if any(value is not None and value < floor for value in
               (p.ghost_intrinsic_hp_current, p.ghost_intrinsic_mp_current)):
            return False
    from .possession_system import is_possessed, leave_host_body
    if is_possessed(p):
        core = p.ghost_core_state
        if core['realm_index'] < 4 or (core['lifespan'] is not None and p.age >= core['lifespan']):
            return False
        leave_host_body(p)
    leave_body(game, destroyed=True)
    p.death_reason = None
    game.pending_event = None
    record(game, '肉身遭遇致命损伤，本魂脱出，进入神游；仍须遵守离体期限。')
    return True


def consume_second(game, reason):
    row = game.player.nascent_state.pop('second', None)
    if row:
        # Equipment is real escrow, returned once even when its soul perishes.
        from ..rules import add_item
        for raw in row['equipment']:
            add_item(game.player, Item.from_dict(raw))
        kill_person(game, row['id'], reason)


def death_excluded(game, event_id, cause=None):
    key = str(event_id).upper()
    if game.active_trial or any(word in key for word in ('TRIAL', 'TRIBULATION', 'ASCENSION', 'LIFESPAN')):
        return True
    if cause is not None:
        return cause in {'story', 'tribulation', 'special', 'lifespan'}
    return bool(not key.startswith(('SYS_', 'ACT_'))
                or any(word in key for word in ('TRIAL', 'TRIBULATION', 'ASCENSION', 'STORY')))


def rescue(game, reason, event_id, cause=None):
    """Consume the actual second soul before changing the original Player."""
    p = game.player
    if death_excluded(game, event_id, cause) or lifespan_exhausted(p) or survival_rank(p) < 4:
        return False
    npc = second_person(game)
    row = p.nascent_state.get('second', {})
    if npc and row.get('control', 100.) >= 50:
        rank, layer = npc.realm_index, npc.layer
        remaining = None if second_lifespan(npc) is None else second_lifespan(npc) - second_age(game, npc)
        consume_second(game, '第二元婴替本尊续命而消散')
        # Discard a destroyed host; never restore a stale pre-rescue cultivation.
        p.ghost_host_body = p.ghost_core_state = None
        p.ghost_captor = p.ghost_attachment = None
        replace_rank(p, rank, layer)
        p.opportunity = 0.
        p.awaiting_major_breakthrough = p.awaiting_minor_breakthrough = False
        p.active_breakthrough_aids = []
        p.soul_energy = max(1., soul_cap(p) * .5)
        p.nascent_state.pop('crisis', None)
        p.ghost_intrinsic_hp_current = p.ghost_intrinsic_hp_reference
        p.ghost_intrinsic_mp_current = p.ghost_intrinsic_mp_reference
        # The replacement inherits this soul's remaining life, never a free refill.
        p.lifespan = None if remaining is None else p.age + remaining
        for snapshot in (p.cultivation_suppression, p.sealed_cultivation):
            if snapshot:
                snapshot['lifespan'] = p.lifespan
        leave_body(game, destroyed=True)
        from ..rules import max_hp, max_mp
        p.hp, p.mp = max_hp(p) * .5, max_mp(p) * .5
        p.alive, p.death_reason = True, None
        game.pending_event = None
        record(game, f'第二元婴抵挡了“{reason}”，修为变为{REALMS[rank].name}第{layer}层，进入神游。',
               dict(second_rescued=True))
        return True
    return False


def resolve_energy(game, rng, die):
    p = game.player
    if not p.alive:
        return
    p.body_energy = min(body_cap(p), max(0., p.body_energy))
    p.soul_energy = min(soul_cap(p), max(0., p.soul_energy))
    if p.body_energy <= 0 and not wandering(p):
        die(game, '体魄能量耗尽，肉身崩毁', 'SYS_BODY_COLLAPSE')
        if not p.alive:
            return
    state = p.nascent_state
    if p.soul_energy > 0:
        state.pop('depleted', None)
    elif not state.get('depleted'):
        state['depleted'] = True
        outcome = rng.randrange(3)
        if outcome == 0:
            state['stagnant'] = True
            p.awaiting_major_breakthrough = p.awaiting_minor_breakthrough = False
            record(game, '神魂枯竭，道基永久受损，此生无法再精进修为。')
        elif outcome == 1:
            state['crisis'] = 'possession'
            record(game, '神魂枯竭引来夺舍邪魂；请在人物详情中进行神魂抗争。未处理前无法继续耗时行动。')
        else:
            from ..soul_rules import lower_minor
            source = p.cultivation_suppression or p.sealed_cultivation or {}
            rank, layer = lower_minor(source.get('realm_index',p.realm_index), source.get('layer',p.layer), REALMS)
            replace_rank(p, rank, layer)
            if p.ghost_core_state:
                core = p.ghost_core_state
                core['realm_index'],core['layer'] = lower_minor(core['realm_index'],core['layer'],REALMS)
                core.update(opportunity=0.,awaiting_major_breakthrough=False,awaiting_minor_breakthrough=False)
            p.opportunity = 0.
            p.awaiting_major_breakthrough = p.awaiting_minor_breakthrough = False
            record(game, '神魂枯竭，修为跌落一个小境界。')


def tick(game, rng, die):
    p = game.player
    if not p.alive:
        return False
    if lifespan_exhausted(p):
        die(game, '寿元已尽', 'SYS_LIFESPAN')
        return False
    settle_second(game)
    before_spirit = p.spirit_state
    resolve_energy(game, rng, die)
    if not p.alive or p.spirit_state is not before_spirit:
        return False
    state = p.nascent_state
    if wandering(p) and p.path != 'ghost' and p.age > p.spirit_state['deadline']:
        die(game, '神游超过一个时间单位，本魂消散', 'SYS_SPIRIT_TIMEOUT', survival_stage='spirit_failed')
        return False
    # Persistent world-year anchor prevents a second charge through another port.
    if state.get('last_year') == p.age:
        return not state.get('crisis')
    state['last_year'] = p.age
    npc = second_person(game)
    row = state.get('second')
    if row and not npc:
        consume_second(game, '第二元婴已经消散')
    elif npc and p.age >= row['due']:
        cost = assimilation_cost(npc.realm_index)
        if row['auto'] and p.soul_energy >= cost:
            p.soul_energy -= cost
            row['integrity'] = min(100., row['integrity'] + 20)
            row['control'] = min(100., row.get('control', 100.) + 20)
            record(game, f'同化第二元婴，消耗{cost}点神魂能量。')
        else:
            row['control'] = max(0., row.get('control', 100.) - 2)
            chance = rebellion_chance(row['control'])
            if chance > 0 and rng.random() < chance:
                # The rebel cannot also provide its own rescue.
                consume_second(game, '反噬夺舍，本魂与第二元婴争斗')
                die(game, '未能镇压第二元婴，遭到夺舍', 'SYS_NASCENT_REBELLION', survival_stage='spirit_failed')
                return False
            record(game, f'第二元婴同化不足，控制力降低2；本期反噬概率{chance:.1%}，未遭夺舍。')
        row['due'] = p.age + row['interval']
        resolve_energy(game, rng, die)
    return p.alive and not state.get('crisis')


def restore(player, fraction=.2):
    if not wandering(player) or player.spirit_state.get('body_intact'):
        player.body_energy = min(body_cap(player), player.body_energy + body_cap(player) * fraction)
    player.soul_energy = min(soul_cap(player), player.soul_energy + soul_cap(player) * fraction)
