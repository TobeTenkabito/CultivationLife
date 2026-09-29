"""Map-array authorization and instant arrival, independent of travel clocks."""
import hashlib

from ..content_registry import WORLD_SYSTEMS
from ..models import HistoryRecord
from ..rules import remove_item, effective_fame
from ..runtime import decode_rng, encode_rng, now_iso


def separated(maps, world, origin, destination):
    return origin != destination and destination not in {node for node, _ in maps._graphs[world][origin]}


def arrays(game, maps):
    world = game.player.world
    factions = sorted((s for s in game.sects.values() if s.world == world and not s.extinct), key=lambda s: s.id)
    result = {}
    for location in maps.worlds[world]['locations']:
        if not location.get('teleport_array'):
            continue
        seed = int.from_bytes(hashlib.blake2s((world + location['id']).encode(), digest_size=4).digest(), 'big')
        owner = factions[seed % len(factions)] if factions else None
        result[location['id']] = dict(id=location['id'], name=location['name'],
            owner_id=owner.id if owner else world + ':array-keepers',
            owner_name=owner.name if owner else WORLD_SYSTEMS['world_names'][world] + '守阵盟')
    return result


def public_teleport(game, maps):
    p = game.player
    rows = arrays(game, maps)
    here = rows.get(p.location_id)
    tier = WORLD_SYSTEMS['world_profiles'][p.world]['tier']
    for row in rows.values():
        row['licensed'] = f"{p.world}:{row['owner_id']}" in p.teleport_permissions or row['owner_id'] == p.faction_id
    return dict(arrays=list(rows.values()), origin=here, bribe=1000 * tier ** 2,
        exposure={'bribe': .12, 'assassinate': .40}, fame_penalty=500 * tier ** 2,
        required_fame=200 * tier, can_request=bool(here and (effective_fame(p) >= 200 * tier or p.faction_id == here['owner_id'])),
        destinations=[row for key, row in rows.items() if here and separated(maps, p.world, p.location_id, key)
                      and maps.travel_plan(p.world, p.location_id, key, p.realm_index).status == 'ok'])


class TeleportMixin:
    def _instant_arrival(self, game, destination):
        p = game.player
        if not separated(self.maps, p.world, p.location_id, destination):
            raise ValueError('传送阵不连接相邻地图，目的地须至少跨过一个节点')
        plan = self.maps.travel_plan(p.world, p.location_id, destination, p.realm_index)
        if plan.status in {'blocked', 'lethal'}:
            raise ValueError(plan.warning or '目的地不可抵达')
        p.location_id = destination
        self._clear_market(game)
        rng = decode_rng(game.seed, game.rng_state)
        self._ensure_market(game, rng)
        game.rng_state = encode_rng(rng)

    def teleport_action(self, game_id, action, destination=None):
        game = self._load(game_id)
        p = game.player
        if (not p.alive or game.pending_event or game.active_trial or p.imprisonment or p.ghost_captor
                or game.heavenly_court.get('open_election') or game.guixu_state.get('player_session')):
            raise ValueError('当前状态无法使用传送阵')
        info = public_teleport(game, self.maps)
        here = info['origin']
        if not here:
            raise ValueError('此地没有地图传送阵；商盟内部阵请到商盟办理')
        permission = f"{p.world}:{here['owner_id']}"
        if action == 'request':
            if here['licensed']:
                raise ValueError('已取得此势力的许可')
            if not info['can_request']:
                raise ValueError(f"须属{here['owner_name']}或声望达到 {info['required_fame']} 方可申请许可")
            p.teleport_permissions.append(permission)
            summary = f"{here['owner_name']}授予传送阵通行许可。"
        elif action in {'travel', 'bribe', 'assassinate'}:
            if destination not in {row['id'] for row in info['destinations']}:
                raise ValueError('目的地没有可直达的远程传送阵')
            if action == 'travel' and not here['licensed']:
                raise ValueError('尚未取得执掌此阵的势力许可')
            if action == 'bribe' and not remove_item(p, 'spirit_stone', info['bribe']):
                raise ValueError('贿赂守阵人的灵石不足')
            exposure = ''
            if action != 'travel':
                rng = decode_rng(game.seed, game.rng_state)
                if rng.random() < info['exposure'][action]:
                    p.fame += info['fame_penalty']
                    key = ('sect:' + here['owner_id']) if here['owner_id'] in game.sects else ('world:' + p.world)
                    threshold = float(WORLD_SYSTEMS['faction_conflict']['wanted_threshold'])
                    p.hostility[key] = max(p.hostility.get(key, 0), threshold + 100)
                    p.milestones['became_wanted_target'] = 1
                    exposure = f"行迹暴露！威名 +{info['fame_penalty']}，{here['owner_name']}发出通缉。"
                game.rng_state = encode_rng(rng)
            self._instant_arrival(game, destination)
            method = {'travel': '', 'bribe': '买通守阵人偷渡，', 'assassinate': '暗杀守阵人偷渡，'}[action]
            summary = f"{method}瞬息抵达{self.maps.location(p.world, destination)['name']}，不增加年龄。{exposure}"
        else:
            raise ValueError('未知传送操作')
        game.history.append(HistoryRecord('SYS_TELEPORT', 1, p.age, '挪移虚空', action, 'completed', summary, {}, ['travel']))
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)
