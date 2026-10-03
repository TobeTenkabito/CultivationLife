"""An on-demand directory command adapter; existing relationship services own outcomes."""
from ..content_registry import WORLD_SYSTEMS
from .npc_contact_dependencies import NpcContactDependencies
from ..models import HistoryRecord, SectNpc
from ..runtime import decode_rng, encode_rng, now_iso
from ..rules import has_living_master


def relation_kind(player, npc_id):
    for kind, rows in [('master', [player.master]), ('companion', [player.dao_companion]),
                       ('disciple', player.disciples), ('friend', player.dao_friends),
                       ('concubine', player.concubines), ('party', player.party)]:
        if any(row and row.get('id') == npc_id for row in rows):
            return kind
    return 'npc'


def availability(game, npc):
    p = game.player
    blocked = ('此人不在当前界面或已经陨落' if not npc.alive or npc.world != p.world else
               '请先结束当前事件、战斗或拘禁' if not p.alive or game.pending_event or game.active_trial or p.imprisonment or p.ghost_captor
               or (game.guixu_state.get('player_session') or {}).get('trapped') else '')
    actions = dict.fromkeys(['party','companion','friend','master','disciple','concubine','slay','improve','worsen','capture'], blocked)
    if blocked:
        return actions
    kind = relation_kind(p, npc.id)
    rules = WORLD_SYSTEMS['relationship']
    if kind not in {'npc','party','friend'}:
        for a in ['companion','friend','master','disciple','concubine']:
            actions[a] = '已有名分，请先在下方关系名册中解除'
    if kind == 'friend': actions['friend'] = '已经结为道友'
    if has_living_master(p): actions['master'] = '已有师承'
    if (npc.realm_index, npc.layer) <= (p.realm_index, p.layer): actions['master'] = '对方修为须高于你'
    if (npc.realm_index, npc.layer) >= (p.realm_index, p.layer): actions['disciple'] = '对方修为须低于你'
    if len(p.disciples) + len(p.disciple_requests) >= rules['max_disciples']: actions['disciple'] = '弟子名额已满'
    for a in ['master','disciple']:
        if f'{a}:{npc.id}' in p.relationship_attempts: actions[a] = '已向此人提出过同类请求'
    if p.dao_companion and p.dao_companion.get('alive', True): actions['companion'] = '已有道侣'
    if npc.gender != 'female': actions['concubine'] = '侍妾名分只可向女性修士提出'
    elif (npc.realm_index, npc.layer) > (p.realm_index, p.layer): actions['concubine'] = '对方修为须不高于你'
    if float(npc.affinity or 0) < rules['friend_affinity_required']: actions['friend'] = '尚需增进好感'
    if not any(row.get('id') == npc.id for row in p.party) and len(p.party) >= WORLD_SYSTEMS['party']['max_companions']: actions['party'] = '同行队伍已满'
    if p.path != 'demonic': actions['capture'] = '魔修方可施展生擒魔禁'
    elif kind in {'disciple','concubine','party'}: actions['capture'] = '请先解除此段名分或同行，再行生擒'
    if game.governance_actions.get(f'party_interaction:{npc.id}') == p.age:
        actions['improve'] = actions['worsen'] = '本行动单位已与此人交流'
    return actions


def act(deps: NpcContactDependencies, game_id, npc_id, action):
    game = deps._load(game_id)
    # Resolve only existing people. Opening or searching never generates population.
    npc = deps._find_npc(game, npc_id)
    if not npc:
        raw = next((r.get('npc') for r in game.encounter_npc_cache if (r.get('npc') or {}).get('id') == npc_id), None)
        npc = SectNpc.from_dict(raw) if raw else None
    if not npc:
        raise ValueError('此人已不在已知人物名册中')
    options = availability(game, npc)
    if action not in options:
        raise ValueError('未知交往方式')
    if options[action]:
        raise ValueError(options[action])
    deps.assert_buddhist_operation_allowed(game_id, 'npc-contact')
    p = game.player
    kind = relation_kind(p, npc_id)
    if action == 'party':
        return deps.manage_party(game_id, npc_id, 'leave' if any(r.get('id') == npc_id for r in p.party) else 'invite')
    if action == 'companion': return deps.manage_dao_companion(game_id, 'propose', npc_id=npc_id)
    if action == 'friend': return deps.manage_dao_friend(game_id, npc_id, 'befriend')
    if action == 'concubine': return deps.manage_concubine(game_id, npc_id, 'recruit')
    if action in {'master','disciple'}:
        return deps.manage_known_relationship(game_id, npc_id, action)
    if action == 'capture' and kind in {'master','companion','friend'}:
        return deps.begin_relationship_capture(game_id, kind, npc_id)
    if action in {'slay','capture'}:
        return deps.relationship_violence(game_id, kind, npc_id, capture=action=='capture')
    npc = deps._find_npc(game, npc_id) or deps._promote_cached_npc(game, npc_id, '交往')
    rng = decode_rng(game.seed, game.rng_state)
    low, high = WORLD_SYSTEMS['party'].get('interaction_affinity', [4,8])
    gain = rng.randint(int(low), int(high))
    raw_delta = gain if action == 'improve' else -gain
    # The shared affinity service already applies the player's path modifier.
    delta = deps._sage_affinity_gain(p, raw_delta)
    affinity = deps._adjust_person_affinity(game, npc_id, raw_delta)
    game.governance_actions[f'party_interaction:{npc_id}'] = p.age
    summary = f"你与{npc.name}{'畅谈修行，增进了解' if action == 'improve' else '言语相争，渐生嫌隙'}，好感 {delta:+g}，当前为 {affinity:g}。"
    game.history.append(HistoryRecord('SYS_NPC_CONTACT',1,p.age,'故人交往',npc_id,action,summary,{'affinity':delta},['system','relationship']))
    game.updated_at = now_iso()
    game.rng_state = encode_rng(rng)
    deps.store.save(game)
    return deps.present(game)
