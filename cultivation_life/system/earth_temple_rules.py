"""Local faith references the original city and temple; no population replicas."""
from ..building_schema import address
from ..building_rules import may_use, initial_rows
from .westward_rules import enabled, record
from .cultivation_guard import cultivation_blocked


def root(game):
    return record(game).get('earth', {})


def ledgers(game):
    main = root(game)
    return ([main] + list(main.get('branches', {}).values())) if main.get('temple_id') else []


def state(game, identity=None):
    records = game.building_state.get('records', {})
    for s in ledgers(game):
        row = records.get(s['temple_id'])
        matches = s['temple_id'] == identity if identity is not None else row and row['address'] == address(game)
        if matches:
            return s
    return {} if identity is not None else root(game)


def temple(game, identity=None):
    return game.building_state.get('records', {}).get(state(game, identity).get('temple_id'))


def pending(game):
    return next((s for s in ledgers(game) if s.get('duty') or s.get('works') or s.get('cases',{}).get('active')), None)


def occupied_reason(game):
    current=state(game).get('temple_id')
    if game.economy_v2.get('institution_agendas',{}).get('scopes',{}).get('temple:'+str(current),{}).get('job'):
        return '本庙已有执事筹办，须先交接，不能为同一轮护民重复立项'
    from .westward_activity import occupied
    if occupied(game):return '请先交接访古或项目议政的本人事务'
    if record(game).get('project') or game.yaochi_state.get('job'):
        return '请先结清专修或交付瑶池委托，再承接地方事务'
    if any(r['status']=='active' for r in record(game).get('fair',{}).get('entries',[])):return '请先完成或退出仙会赛事'
    bureaus=game.heavenly_court.get('bureaus',{})
    if bureaus.get('review') or any(c['status']=='active' for c in bureaus.get('inquiries',[])) or any(j['person']=='player' and j['status']=='active' for j in bureaus.get('jobs',[])):
        return '请先完成或交接本人当前职司公务'
    s = pending(game)
    if not s:
        return ''
    row = temple(game, s['temple_id'])
    return f"请先完成或退出{row['name'] if row else '原庙'}的当前事务；本人一次只能主持一项庙务"


def slots(game):
    return list((temple(game) or {}).get('temple_facilities', [None, None]))


def city(game, building=None):
    building = building or temple(game)
    if not building:
        return None
    original = game.building_state.get('records', {}).get(building['city_id'])
    if original is not None:
        return original if original['type'] == 'city' and original['address'] == building['address'] else None
    # The annual path reads the single original city, not every estate/temple.
    return next((r for r in initial_rows(building['address'])
                 if r['type'] == 'city' and r['id'] == building['city_id']), None)


def reason(game, *, recovery=False):
    p = game.player
    if p.world != 'celestial':
        return '须亲临仙界原庙所在地办理'
    if (cultivation_blocked(game) or p.nascent_state.get('crisis') or game.map_journey
            or game.guixu_state.get('player_session') or game.trial_site_state.get('active')):
        return '请先处理事件、旅行、试炼或拘束'
    if p.spirit_state.get('mode') == 'wandering':
        return '请先结束神游，再亲自办理庙务'
    from .heavens.state import active_task
    runtime = game.heavens_state.get('runtime')
    if runtime and active_task(runtime):
        return '请先结束诸天亲自任务'
    if recovery:
        return ''
    if not enabled():
        return '《瑶池西望：紫气东来》尚未启用'
    if p.path != 'dao' or p.realm_index < 9 or not p.immortal_power_converted:
        return '须由完成仙灵力转化的真仙及以上道修主持'
    if p.sealed_cultivation or p.cultivation_suppression:
        return '请先解除修为压制'
    return ''


def local_reason(game, *, recovery=False):
    if blocked := reason(game, recovery=recovery):
        return blocked
    building = temple(game)
    if not building or building['address'] != address(game):
        return '须亲临原土地庙所在地；离庙期间助修与履约暂停'
    if building['owner'] != dict(kind='player', id=game.id):
        return '已不拥有此庙，不能主持庙务'
    if recovery:
        return ''
    original = city(game, building)
    if (building['status'] != 'intact' or not original or
            original.get('population') not in {'mortal', 'mixed'} or
            not may_use(original, 'player', game.id)):
        return '庙宇或原城市不可用；须恢复建筑与城市使用许可'
    from .immortal_identity_rules import official,public_service
    civic=public_service(game,building)
    if official(game) and not civic:
        return '玄仙在编期间停用地仙主持与香火；公共服务协议另按原决议履约'
    if not state(game).get('active') and not civic:
        return '已暂停地仙主持，可在原庙恢复；旧额度不续期'
    return ''


def bonus(game, *, year_end=False):
    from .immortal_identity_rules import official
    if official(game):return 0.
    s = state(game)
    if (not s or not s.get('allowance') or game.player.age > s.get('until', 0)
            or not year_end and game.player.age == s.get('until', 0)):
        return 0.
    if local_reason(game):
        return 0.
    return min(100, max(0, s.get('trust', 0))) * .005


def activity(game, base_gain, action):
    """Only an executed ordinary cultivation year consumes one allowance."""
    factor = bonus(game, year_end=True) if action == 'cultivate' else 0.
    from .immortal_identity_rules import official
    if (action == 'cultivate' and not official(game) and state(game).get('allowance', 0) > 0
            and game.player.age <= state(game).get('until', 0) and not local_reason(game)):
        state(game)['allowance'] -= 1
    return max(0., base_gain) * factor, 1. + factor
