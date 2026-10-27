"""One base-game body/soul lifecycle, shared by ordinary and spatial time."""
from ..soul_rules import wandering, body_cap, soul_cap, assimilation_cost
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


def record(game, text):
    game.history.append(HistoryRecord('SYS_SOUL', 1, game.player.age, '神魂与元婴', None,
                                      'settled', text, {}, ['system', 'soul']))


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
    record(game, '肉身已毁，炼体归零。' if destroyed else '元婴离体，肉身留在原处。')


def second_person(game):
    row = game.player.nascent_state.get('second')
    npc = find_person(game, row['id'], include_inactive=True) if row else None
    if npc and npc.alive and npc.roster_state == 'held' and (npc.custody or {}).get('holder_id') == game.id:
        return npc
    return None


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
    if game.active_trial or any(word in key for word in ('TRIAL', 'TRIBULATION', 'ASCENSION')):
        return True
    if cause is not None:
        return cause in {'story', 'tribulation'}
    return bool(not key.startswith(('SYS_', 'ACT_'))
                or any(word in key for word in ('TRIAL', 'TRIBULATION', 'ASCENSION', 'STORY')))


def rescue(game, reason, event_id, cause=None):
    """Consume the actual second soul before changing the original Player."""
    p = game.player
    if death_excluded(game, event_id, cause):
        return False
    npc = second_person(game)
    if npc:
        rank, layer = npc.realm_index, npc.layer
        consume_second(game, '第二元婴替本尊续命而消散')
        # Discard a destroyed host; never restore a stale pre-rescue cultivation.
        p.ghost_host_body = p.ghost_core_state = None
        replace_rank(p, rank, layer)
        p.opportunity = 0.
        p.awaiting_major_breakthrough = p.awaiting_minor_breakthrough = False
        p.active_breakthrough_aids = []
        p.soul_energy = max(1., soul_cap(p) * .5)
        p.nascent_state.pop('crisis', None)
        p.ghost_intrinsic_hp_current = p.ghost_intrinsic_hp_reference
        p.ghost_intrinsic_mp_current = p.ghost_intrinsic_mp_reference
        # A new soul is still mortal; one time unit to acquire a body is real.
        if p.lifespan is not None and p.age >= p.lifespan:
            p.lifespan = p.age + unit_years(p) + 1
        leave_body(game, destroyed=True)
        from ..rules import max_hp, max_mp
        p.hp, p.mp = max_hp(p) * .5, max_mp(p) * .5
        p.alive, p.death_reason = True, None
        game.pending_event = None
        record(game, f'第二元婴抵挡了“{reason}”，修为变为{REALMS[rank].name}第{layer}层，进入神游。')
        return True
    return False


def resolve_energy(game, rng, die):
    p = game.player
    p.body_energy = min(body_cap(p), max(0., p.body_energy))
    p.soul_energy = min(soul_cap(p), max(0., p.soul_energy))
    if p.body_energy <= 0 and not wandering(p):
        if p.realm_index >= 4:
            leave_body(game, destroyed=True)
        else:
            die(game, '体魄能量耗尽，爆体而亡', 'SYS_BODY_COLLAPSE')
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
    resolve_energy(game, rng, die)
    if not p.alive:
        return False
    state = p.nascent_state
    if wandering(p) and p.path != 'ghost' and p.age > p.spirit_state['deadline']:
        die(game, '神游超过一个时间单位，本魂消散', 'SYS_SPIRIT_TIMEOUT')
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
            record(game, f'同化第二元婴，消耗{cost}点神魂能量。')
        elif rng.random() < .35:
            # The rebel is the threat, so it cannot also provide its own rescue.
            consume_second(game, '反噬夺舍，本魂与第二元婴争斗')
            die(game, '未能镇压第二元婴，遭到夺舍', 'SYS_NASCENT_REBELLION')
            return False
        else:
            record(game, '第二元婴同化不足，本次侥幸未遭夺舍；下期仍有35%反噬风险。')
        row['due'] = p.age + row['interval']
        resolve_energy(game, rng, die)
    return p.alive and not state.get('crisis')


def restore(player, fraction=.2):
    if not wandering(player) or player.spirit_state.get('body_intact'):
        player.body_energy = min(body_cap(player), player.body_energy + body_cap(player) * fraction)
    player.soul_energy = min(soul_cap(player), player.soul_energy + soul_cap(player) * fraction)
