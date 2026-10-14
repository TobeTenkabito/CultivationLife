"""Explicit inheritance command and read-only UI quotes, using local settlements."""
import copy

from ..models import HistoryRecord, Technique
from ..rules import learn_technique
from ..runtime import now_iso
from .spirit_inheritance_rules import mode, plan, record, discounted


def blocked(game):
    p = game.player
    from .possession_system import is_possessed
    if (not p.alive or game.pending_event or game.active_trial or p.imprisonment or p.ghost_captor
            or p.sealed_cultivation or p.cultivation_suppression or is_possessed(p)
            or (game.guixu_state.get('player_session') or {}).get('trapped')):
        return '当前状态无法承接传承，请先处理事件、拘束、寄身或修为压制'
    return None


def cost(game, proposal):
    if proposal['mode'] in {'native', 'monster', 'ghost'}:
        from .upper_voisinage import quote
        bill = discounted(quote(game.player, 1, game), proposal['source_level'])
        bill['materials'] = max(1, bill['materials'])
        return bill
    base = {'souls': 100} if proposal['mode'] == 'eightfold' else {'stones': 60000, 'opportunity': 6000, 'traces': 8}
    return discounted(base, proposal['source_level'])


def affordability(game, bill):
    p = game.player
    stones = sum(i.quantity for i in p.inventory if i.id == 'spirit_stone')
    if stones < bill.get('stones', 0):
        return '灵石不足'
    if p.opportunity < bill.get('opportunity', 0):
        return '机缘不足'
    if p.immortal_traces < bill.get('traces', 0):
        return '仙痕不足'
    if p.asura_cultivation.get('souls', 0) < bill.get('souls', 0):
        return '精魂不足'
    if bill.get('owned_materials', 0) < bill.get('materials', 0):
        return '本界筑域材料不足'
    return None


def public(game):
    if not mode(game.player):
        return []
    rows = []
    for book in game.player.known_techniques:
        if not book.spirit_voisinage_id:
            continue
        bill, name, reason = None, book.name, None
        try:
            proposal = plan(game, book.id)
            name = proposal['name']
            bill = cost(game, proposal)
            reason = blocked(game) or affordability(game, bill)
        except ValueError as error:
            reason = str(error)
        rows.append(dict(manual_id=book.id, name=name, source_name=book.name, source_level=book.level,
                         mode=mode(game.player), cost=bill, reason=reason, can_inherit=not reason))
    return rows


def act(deps, game_id, manual_id):
    game = deps._load(game_id)
    reason = blocked(game)
    if reason:
        raise ValueError(reason)
    proposal = plan(game, manual_id)
    if proposal['mode'] in {'native', 'monster', 'ghost'}:
        from .upper_voisinage import act as upper_action
        return upper_action(deps, game_id, 'inherit', manual_id)
    if proposal['mode'] == 'eightfold':
        return deps.asura_action(game_id, 'inherit', target_id=manual_id)
    bill = cost(game, proposal)
    reason = affordability(game, bill)
    if reason:
        raise ValueError(reason)
    p = game.player
    from .economy import organizations as finance
    finance.transfer_value(game, 'player', 'background:celestial', bill['stones'], '灵域传承补全')
    p.opportunity -= bill['opportunity']
    p.immortal_traces -= bill['traces']
    game.doctrine_state['definitions'].setdefault(proposal['doctrine_id'], copy.deepcopy(proposal['celestial_definition']))
    book = Technique(**copy.deepcopy(proposal['upper_manual']))
    book.level = min(4, proposal['source_level'])
    known = next((t for t in p.known_techniques if t.id == book.id), None)
    if known:
        from ..rules import ensure_technique_set
        known.level = max(known.level, book.level)
        ensure_technique_set(p)
    else:
        learn_technique(p, book)
    game.doctrine_state['player'].setdefault('spirit_inheritances', {})[proposal['doctrine_id']] = record(proposal)
    summary = f"补全{proposal['source_name']}的入门功法至 Lv4，前四层参悟所需年数减免；注解、境界与唯一本源仍须正常满足。原残解保留，不增加道统等级或元力。"
    game.history.append(HistoryRecord('SYS_SPIRIT_INHERITANCE', 1, p.age, '传承承接', manual_id, 'completed', summary, {}, ['cultivation']))
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)
