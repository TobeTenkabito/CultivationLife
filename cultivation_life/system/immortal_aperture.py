"""Independent player energy reservoirs; no automatic refill during battle/UI reads."""
from ..content_registry import WORLD_SYSTEMS
from ..models import HistoryRecord
from ..rules import max_hp, max_mp
from ..runtime import now_iso


def true_realm(player):
    return max(player.realm_index, int((player.sealed_cultivation or {}).get('realm_index', 0)))


def cultivation_stage(player):
    sealed = player.sealed_cultivation or {}
    realm, layer = max((player.realm_index, player.layer),
                       (int(sealed.get('realm_index', 0)), int(sealed.get('layer', 1))))
    return max(0, (realm - 9) * 3 + (max(1, layer) - 1) // 3)


def investment_multiplier(player):
    return 1 if lower_world(player) else 1 + .5 * cultivation_stage(player)


def spirit_books(player):
    return [t for t in player.known_techniques if t.spirit_voisinage_id and t.level >= 4 and t.active_in(player.world)]


def lower_world(player):
    return WORLD_SYSTEMS['world_profiles'].get(player.world, {}).get('tier', 1) < 3


def available(player):
    return true_realm(player) >= 9 or bool(spirit_books(player))


def ensure_aperture(player):
    if not available(player):
        return False
    capacity = 1000 * (1 + cultivation_stage(player))
    if player.immortal_aperture:
        old = player.immortal_aperture['capacity']
        player.immortal_aperture['capacity'] = max(old, capacity)
        return old != player.immortal_aperture['capacity']
    # One-time legacy conversion. Subsequent loads and realm crossings conserve reserves.
    player.immortal_aperture = {'version': 1, 'capacity': capacity,
        'current': capacity * min(1, max(0, player.mp / max_mp(player))) if player.immortal_power_converted else 0,
        'imitation_current': 0, 'imitation_capacity': 60}
    return True


def energy_state(player):
    ensure_aperture(player)
    if not available(player):
        return None
    ledger = player.immortal_aperture
    lower = lower_world(player)
    from .immortal_cultivation import golden_light
    from .asura import active as asura_active
    asura_conversion = player.asura_cultivation.get('conversion', 0) if asura_active(player) else 0
    converted = player.immortal_power_converted or player.immortal_conversion_stage > 0 or asura_conversion > 0
    return dict(version=1, resource_link='independent',
        capacity=ledger['imitation_capacity'] if lower else ledger['capacity'],
        current=ledger['imitation_current'] if lower else ledger['current'],
        conversion=asura_conversion / 5 if asura_active(player) else 1,
        force_tier=2 if converted and true_realm(player) >= 9 else 1,
        ward_tier=2 if golden_light(player) else 1,
        attack_cost=1 if lower else 10, ward_cost=0)


def commit_energy(player, current):
    ensure_aperture(player)
    ledger = player.immortal_aperture
    pool, capacity = ('imitation_current', 'imitation_capacity') if lower_world(player) else ('current', 'capacity')
    ledger[pool] = max(0, min(ledger[capacity], current))


def public_aperture(player, game=None):
    if not available(player):
        return {'available': False}
    ensure_aperture(player)
    ledger = player.immortal_aperture
    lower = lower_world(player)
    state = energy_state(player)
    from .asura import active as asura_active
    asura_conversion = player.asura_cultivation.get('conversion', 0) / 5 if asura_active(player) else None
    from .upper_voisinage import world_config, available as upper_available
    upper = world_config(player) if upper_available(player) else None
    from ..rules import intrinsic_resource_breakdown
    intrinsic = intrinsic_resource_breakdown(player)
    field = None
    if lower and game is not None:
        from .spirit_voisinage import player_source
        source = player_source(game)
        if source.voisinages:
            from dataclasses import asdict
            field = asdict(source.voisinages[0])
    return {'available': True, 'lower': lower, 'field': field,
            'name': upper['energy'] if upper else '仿仙灵力' if lower else '仙灵力',
            'title': upper['aperture'] if upper else '仙窍', 'native': bool(upper),
            'asura_conversion': asura_conversion is not None,
            'current': min(state['current'], state['capacity'] * state['conversion']),
            'capacity': state['capacity'] * state['conversion'],
            'investment_multiplier': investment_multiplier(player),
            'sealed_reserve': ledger['current'] if lower else 0,
            'conversion': asura_conversion if asura_conversion is not None else 1 if upper or player.immortal_power_converted else player.immortal_conversion_stage / 5,
            'origin_hp': intrinsic['hp']['current'], 'origin_mp': intrinsic['mp']['current'],
            'max_hp': intrinsic['hp']['maximum'], 'max_mp': intrinsic['mp']['maximum'],
            'refine_gain': 20 if lower else ledger['capacity'] / 4,
            'hp_cost': intrinsic['hp']['maximum'] * (upper['hp_fraction'] if upper else .15 if lower else 0),
            'mp_cost': intrinsic['mp']['maximum'] * (upper['mp_fraction'] if upper else .35 if lower else .2),
            'spirit_fields': [{'id': t.id, 'name': t.name, 'level': t.level} for t in spirit_books(player)],
            'active_manual': player.spirit_voisinage_manual}


class ImmortalApertureMixin:
    def upper_voisinage_action(self, game_id, action, voisinage_id):
        from .upper_voisinage import act
        return act(self, game_id, action, voisinage_id)

    def aperture_action(self, game_id, action, manual_id=None):
        game = self._load(game_id)
        p = game.player
        if (not p.alive or game.pending_event or game.active_trial or p.imprisonment or p.ghost_captor
            or (game.guixu_state.get('player_session') or {}).get('trapped')):
            raise ValueError('当前状态不能操持仙窍')
        if not available(p):
            raise ValueError('真仙或灵域功法修至四级后方可开启仙窍')
        ensure_aperture(p)
        if action == 'select':
            if manual_id not in {t.id for t in spirit_books(p)}:
                raise ValueError('灵域功法须至少四级')
            p.spirit_voisinage_manual = manual_id
            summary = '已选定斗法所用灵域。'
        elif action == 'refine':
            info = public_aperture(p)
            if info['asura_conversion'] and info['conversion'] < 1:
                raise ValueError('须先在八部面板完成五重煞元转化')
            if not info['lower'] and not info['native'] and not p.immortal_power_converted:
                raise ValueError('请先完成仙灵力转化')
            if info['current'] >= info['capacity']:
                raise ValueError('仙窍已满，无需转化')
            if info['origin_hp'] <= info['hp_cost'] or info['origin_mp'] < info['mp_cost']:
                raise ValueError('本源气血或法力不足，不能强行凝练')
            gain = min(info['refine_gain'], info['capacity'] - info['current'])
            fraction = gain / info['refine_gain']
            p.hp -= info['hp_cost'] * fraction * max_hp(p) / max(1, info['max_hp'])
            p.mp -= info['mp_cost'] * fraction * max_mp(p) / max(1, info['max_mp'])
            commit_energy(p, info['current'] + gain)
            summary = f"凝练{info['name']} {gain:g}，储量 {info['current'] + gain:g}/{info['capacity']:g}。本源上限不变。"
        else:
            raise ValueError('未知仙窍操作')
        game.history.append(HistoryRecord('SYS_APERTURE', 1, p.age, '仙窍运转', action, 'completed', summary, {}, ['system','cultivation']))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)
