"""Independent player energy reservoirs; no automatic refill during battle/UI reads."""
from ..content_registry import WORLD_SYSTEMS
from ..models import HistoryRecord
from ..rules import max_hp, max_mp
from ..runtime import now_iso

from .aperture_resources import (
    true_realm as true_realm,
    cultivation_stage as cultivation_stage,
    investment_multiplier as investment_multiplier,
    spirit_books as spirit_books,
    lower_world as lower_world,
    available as available,
    ensure_aperture as ensure_aperture,
    energy_state as energy_state,
    commit_energy as commit_energy,
)


def public_aperture(player, game=None):
    if not available(player):
        return {'available': False}
    ensure_aperture(player)
    ledger = player.immortal_aperture
    lower = lower_world(player)
    state = energy_state(player)
    from .asura import active as asura_active
    asura_conversion = player.asura_cultivation.get('conversion', 0) / 5 if asura_active(player) else None
    from .upper_voisinage_rules import world_config, available as upper_available
    upper = world_config(player) if upper_available(player) else None
    origin_world = (player.sealed_cultivation or {}).get('upper_world',
        {'demonic':'asura', 'monster':'nether', 'ghost':'reincarnation'}.get(player.path, 'celestial'))
    origin_energy = WORLD_SYSTEMS['upper_voisinages']['worlds'].get(origin_world, {}).get('energy', '仙灵力')
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
            'energy_kind': player.world if upper else 'imitation' if lower else 'immortal',
            'sealed_name': origin_energy,
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
            raise ValueError('当前状态不能操持元府')
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
