"""Explicit school commands. The engine owns transaction, RNG and combat."""
from ...system import mentorship as school
from ...runtime import now_iso, decode_rng, encode_rng
from ...rules import add_item
from ...content_registry import ITEM_CATALOG


def act(engine, game_id, action, npc_id='', rank='', rival_id=''):
    from ...system.mentorship_advanced import ACTIONS, execute
    if isinstance(action, str) and (action in ACTIONS or action in school.PEER_ACTIONS):
        if not all(isinstance(v, str) for v in (action, npc_id, rank, rival_id)): raise ValueError('师门参数无效')
        game = engine._load(game_id)
        rng = decode_rng(game.seed, game.rng_state)
        summary = (school.interact_peer(engine, game, npc_id, action, rng) if action in school.PEER_ACTIONS
                   else execute(engine, game, action, npc_id, rng))
        school.log(game, action, summary)
        game.rng_state = encode_rng(rng)
        game.updated_at = now_iso()
        engine.store.save(game)
        return engine.present(game)
    if not isinstance(action, str) or action not in {'register', 'appoint', 'promote', 'fulfill', 'honor', 'collect', 'graduate'}:
        raise ValueError('未知师门事务')
    if not all(isinstance(v, str) for v in (npc_id, rank, rival_id)): raise ValueError('师门参数无效')
    game = engine._load(game_id)
    p = game.player
    teacher = p.master['id'] if p.master else None
    if action in {'register', 'promote', 'fulfill', 'honor'} or action == 'graduate' and not npc_id:
        if not teacher: raise ValueError('你尚未正式拜师')
        school.require_contact(game, teacher)
        row = school.record(game, teacher, 'player') or school._entry(game, school.rank_of(game, teacher, 'player'))
    else:
        if not any(r['id'] == npc_id for r in p.disciples): raise ValueError('此人不是你的在籍弟子')
        school.require_contact(game, npc_id)
        row = school.record(game, 'player', npc_id) or school._entry(game, school.rank_of(game, 'player', npc_id))
    if action == 'register':
        school.admit(game, teacher, 'player')
        summary = '师门名册已经登记；同门只会在首次正式登记时建立。'
    elif action == 'appoint':
        if rank not in school.RANKS: raise ValueError('未知弟子位次')
        if rank == row['rank']: raise ValueError('此人已经处于该位次')
        limit = school.capacity(game, 'player', rank)
        # Include not-yet-adopted structure-12 relationships in seat accounting.
        count = sum(school.rank_of(game, 'player', r['id']) == rank for r in p.disciples if r['id'] != npc_id and r.get('alive', True))
        if limit is not None and count >= limit: raise ValueError('该位次名额已满，请先调整在位弟子')
        row = school.admit(game, 'player', npc_id)
        old = school.RANKS.index(row['rank'])
        row['rank'] = rank
        if rank != 'heir' and 'advanced' in row:
            row['advanced'].update(pact_possession=False, pact_avatar=False)
        if school.RANKS.index(rank) < old: row['loyalty'] = max(0, row['loyalty'] - 10)
        summary = f'{school.person(game, npc_id).name}被任命为{school.LABELS[rank]}。'
    elif action == 'honor':
        if row['honored'] == row['cycle']: raise ValueError('本周期已自愿呈交心得')
        cost = school.duty_cost(game, {**row, 'rank':'true'})
        if p.opportunity < cost: raise ValueError(f'自愿呈交心得需要机缘 {cost:g}')
        row = school.admit(game, teacher, 'player')
        p.opportunity -= cost
        row['honored'] = row['cycle']
        row['discontent'] = max(0, row['discontent'] - 10)
        row['warned'] = row['discontent'] >= 60
        master = school.person(game, teacher)
        master.affinity = min(100, master.affinity + 10)
        summary = f'你自愿呈交修行心得，机缘 -{cost:g}、师父好感 +10、不满降低10；这不属于记名弟子的义务。'
    elif action == 'fulfill':
        if row['rank'] == 'registered': raise ValueError('记名弟子没有师门义务')
        if row['fulfilled'] == row['cycle']: raise ValueError('本周期已经履约')
        cost = school.duty_cost(game, row)
        if p.opportunity < cost: raise ValueError(f'呈交修行心得需要机缘 {cost:g}')
        row = school.admit(game, teacher, 'player')
        p.opportunity -= cost
        row.update(fulfilled=row['cycle'], merit=row['merit'] + 1,
                   discontent=max(0, row['discontent'] - 20))
        row['warned'] = row['discontent'] >= 60
        school.person(game, teacher).affinity = min(100, school.person(game, teacher).affinity + 3)
        summary = f'你呈交修行心得，机缘 -{cost:g}，履约资历 +1，师门不满降低20。'
    elif action == 'collect':
        if row['rank'] == 'registered': raise ValueError('记名弟子没有贡物义务')
        if row['collected'] == row['cycle']: raise ValueError('本周期已经领取贡物')
        relation = next(r for r in p.disciples if r['id'] == npc_id)
        npc = school.person(game, npc_id)
        inventory = relation.get('items', {})
        item_id = next((key for key, count in inventory.items() if count > 0 and key in ITEM_CATALOG), None)
        treasure = not item_id and npc.treasure_item_id in ITEM_CATALOG and not npc.treasure_looted
        if treasure: item_id = npc.treasure_item_id
        if not item_id: raise ValueError('弟子暂无实际贡物，不会凭空生成收益')
        row = school.admit(game, 'player', npc_id)
        if treasure:
            npc.treasure_looted = True
            npc.treasure_item_id = None
        else: inventory[item_id] -= 1
        add_item(p, item_id)
        row.update(collected=row['cycle'], loyalty=max(0, row['loyalty'] - 8))
        summary = f'收到{npc.name}奉上的{ITEM_CATALOG[item_id].name}，其忠诚 -8。'
    elif action == 'graduate':
        if npc_id:
            school.admit(game, 'player', npc_id)
            school.end(game, 'player', npc_id, 'graduated')
            summary = f'{school.person(game, npc_id).name}正式出师，保留培养和师承履历，不再占活动名额。'
        else:
            reason = school.graduation_reason(game, teacher, row)
            if reason: raise ValueError(reason)
            school.admit(game, teacher, 'player')
            school.end(game, teacher, 'player', 'graduated')
            summary = '师父准你正式出师，师承履历与既有成长保留，停止在籍福利和义务。'
    else:
        index = school.RANKS.index(row['rank'])
        if index == 3: raise ValueError('你已经是嫡传弟子')
        if row['promoted'] == row['cycle']: raise ValueError('本周期已经申请过晋位')
        if row['discontent'] >= 60: raise ValueError('师门不满过高，请先履约')
        master = school.person(game, teacher)
        required_affinity = (20, 45, 75)[index]
        required_merit = (0, 2, 5)[index]
        if master.affinity < required_affinity or row['merit'] < required_merit:
            raise ValueError(f'晋位需要师父好感{required_affinity}、履约资历{required_merit}')
        target_rank = school.RANKS[index + 1]
        incumbents = [key for key, r in school.rows(game, teacher).items() if r['rank'] == target_rank]
        full = len(incumbents) >= school.capacity(game, teacher, target_rank)
        if full:
            if rival_id not in incumbents: raise ValueError('名额已满，请选择该位次的在位同门比试')
            school.require_contact(game, rival_id)
            rival = school.person(game, rival_id)
            if p.hp <= 0: raise ValueError('当前伤势无法比试')
        row = school.admit(game, teacher, 'player')
        row['promoted'] = row['cycle']
        won, summary = True, ''
        if full:
            rng = decode_rng(game.seed, game.rng_state)
            power = engine._npc_power(rival)
            target = dict(target_name=rival.name, target_power=power, primary_power=power,
                          target_realm_index=rival.realm_index, target_layer=rival.layer,
                          npc_id=rival.id, path=rival.path, race=rival.race, world=rival.world,
                          faction_id=rival.faction_id, combat_type='cultivator', action='spar',
                          mentorship_contest=True, non_story_combat=True)
            outcome, summary = engine._combat(game, target, False, rng)
            game.rng_state = encode_rng(rng)
            won = outcome == 'victory'
        if won:
            old_rank = row['rank']
            row['rank'] = target_rank
            if full: school.record(game, teacher, rival_id)['rank'] = old_rank
            summary += f' 你晋升为{school.LABELS[target_rank]}。'
        else: summary += ' 本次未能晋位，双方位次保留。'
    school.log(game, action, summary)
    game.updated_at = now_iso()
    engine.store.save(game)
    return engine.present(game)
