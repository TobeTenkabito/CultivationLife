"""Explicit operations for teleport system."""

from __future__ import annotations
import hashlib
import math
from ..content_registry import WORLD_SYSTEMS
from ..models import HistoryRecord
from ..rules import remove_item, effective_fame
from ..runtime import decode_rng, encode_rng, now_iso
from ..time_dependencies import TeleportDependencies
from .heavens.local_control import arrival_notice

def separated(maps, world, origin, destination):
    return origin != destination and destination not in {node for node, _ in maps._graphs[world][origin]}
def arrays(game, maps, world=None):
    world = world or game.player.world
    factions = sorted((s for s in game.sects.values() if s.world == world and not s.extinct and s.id not in {'heavenly_court', 'yaochi'}), key=lambda s: s.id)
    result = {}
    for location in maps.worlds[world]['locations']:
        if not location.get('teleport_array'):
            continue
        seed = int.from_bytes(hashlib.blake2s((world + location['id']).encode(), digest_size=4).digest(), 'big')
        owner = factions[seed % len(factions)] if factions else None
        institution = {'jade_capital':'heavenly_court', 'expanse_celestial_8':'yaochi'}.get(location['id']) if world=='celestial' else None
        if institution in game.sects and not game.sects[institution].extinct:
            owner = game.sects[institution]
        result[location['id']] = dict(id=location['id'], name=location['name'],
            owner_id=owner.id if owner else world + ':array-keepers',
            owner_name=owner.name if owner else WORLD_SYSTEMS['world_names'][world] + '守阵盟')
    for built in game.economy_v2.get('teleport_arrays',{}).values():
        if built['world']!=world: continue
        owner=game.family if game.family and game.family.id==built['owner_id'] else game.sects.get(built['owner_id'])
        if owner and not owner.extinct and owner.world==world and built['location'] not in result:
            site=maps.location(world,built['location'])
            if site: result[built['location']]=dict(id=built['location'],name=site['name'],owner_id=owner.id,owner_name=owner.name)
    return result
def public_teleport(game, maps):
    p = game.player
    rows = arrays(game, maps)
    here = rows.get(p.location_id)
    tier = WORLD_SYSTEMS['world_profiles'][p.world]['tier']
    unit = int(WORLD_SYSTEMS['time_units'][str(p.realm_index)])
    base = float(WORLD_SYSTEMS['spirit_field']['art_experience_base'])
    talisman_level = math.isqrt(int(max(0, p.art_experience.get('talisman', 0)) / base))
    permit = dict(p.teleport_passes.get(f"{p.world}:{here['owner_id']}", {})) if here else {}
    if permit:
        permit['status'] = ('used' if permit.get('used') else 'pending' if p.age < permit['ready_age']
                            else 'expired' if p.age >= permit['expires_age'] else 'ready')
    for row in rows.values():
        row['licensed'] = f"{p.world}:{row['owner_id']}" in p.teleport_permissions or row['owner_id'] == p.faction_id or bool(game.family and not game.family.extinct and game.family.world==p.world and row['owner_id']==game.family.id)
    from .teleport_construction import owners,estimate
    construction=[estimate(game,s) for s in owners(game)] if not here else []
    return dict(arrays=list(rows.values()), origin=here, construction=construction, bribe=1000 * tier ** 2,
        temporary=permit, temporary_fee=500 * tier ** 2, wait_years=unit,
        forge_fee=300 * tier ** 2, forge_chance=min(.95, max(.05, .12 + .035 * talisman_level - .03 * (tier - 1))), talisman_level=talisman_level,
        exposure={'bribe': .12, 'assassinate': .40}, fame_penalty=500 * tier ** 2,
        required_fame=200 * tier, can_request=bool(here and (effective_fame(p) >= 200 * tier or p.faction_id == here['owner_id'])),
        destinations=[row for key, row in rows.items() if here and separated(maps, p.world, p.location_id, key)
                      and maps.travel_plan(p.world, p.location_id, key, p.realm_index).status == 'ok'])


def _instant_arrival(deps: TeleportDependencies, game, destination):
    p = game.player
    if not separated(deps.maps, p.world, p.location_id, destination):
        raise ValueError('传送阵不连接相邻地图，目的地须至少跨过一个节点')
    plan = deps.maps.travel_plan(p.world, p.location_id, destination, p.realm_index)
    if plan.status in {'blocked', 'lethal'}:
        raise ValueError(plan.warning or '目的地不可抵达')
    p.location_id = destination
    deps._clear_market(game)
    rng = decode_rng(game.seed, game.rng_state)
    deps._ensure_market(game, rng)
    game.rng_state = encode_rng(rng)


def teleport_action(deps: TeleportDependencies, game_id, action, destination=None, owner_id=None):
    import copy
    game = copy.deepcopy(deps._load(game_id))
    p = game.player
    if (not p.alive or game.pending_event or game.active_trial or p.imprisonment or p.ghost_captor
            or game.guixu_state.get('player_session') or p.world in {'lost','rift'}):
        raise ValueError('当前状态无法使用传送阵')
    info = public_teleport(game, deps.maps)
    here = info['origin']
    if action=='build':
        from .teleport_construction import build
        summary=build(game,deps.maps,owner_id,arrays(game,deps.maps))
        game.history.append(HistoryRecord('SYS_TELEPORT_BUILD',1,p.age,'当地建阵',owner_id,'completed',summary,{},['travel','construction']))
        game.updated_at=now_iso();deps.store.save(game)
        return deps.present(game)
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
    elif action == 'request_temporary':
        if info['temporary'].get('status') in {'pending','ready'}:
            raise ValueError('已有待答复或尚未使用的临时通行证')
        if not remove_item(p, 'spirit_stone', info['temporary_fee']):
            raise ValueError('申请费所需灵石不足')
        p.teleport_passes[permission] = dict(ready_age=p.age + info['wait_years'], expires_age=p.age + 2 * info['wait_years'], used=False)
        summary = f"已向{here['owner_name']}申请单次临时通行证，{info['wait_years']} 年后答复，答复后再过 {info['wait_years']} 年失效。申请本身不推进时间。"
    elif action in {'travel', 'bribe', 'assassinate', 'forge', 'temporary'}:
        if destination not in {row['id'] for row in info['destinations']}:
            raise ValueError('目的地没有可直达的远程传送阵')
        if action == 'travel' and not here['licensed']:
            raise ValueError('尚未取得执掌此阵的势力许可')
        if action == 'temporary' and info['temporary'].get('status') != 'ready':
            raise ValueError('临时通行证尚未答复、已过期或已经使用')
        if action == 'forge' and not remove_item(p, 'spirit_stone', info['forge_fee']):
            raise ValueError('伪造通行证的材料费用不足')
        if action == 'bribe' and not remove_item(p, 'spirit_stone', info['bribe']):
            raise ValueError('贿赂守阵人的灵石不足')
        exposure = ''
        forged = True
        if action == 'forge':
            rng = decode_rng(game.seed, game.rng_state)
            forged = rng.random() < info['forge_chance']
            game.rng_state = encode_rng(rng)
        if action in {'bribe','assassinate'} or (action == 'forge' and not forged):
            rng = decode_rng(game.seed, game.rng_state)
            if action == 'forge' or rng.random() < info['exposure'][action]:
                p.fame += info['fame_penalty']
                key = ('sect:' + here['owner_id']) if here['owner_id'] in game.sects else ('world:' + p.world)
                threshold = float(WORLD_SYSTEMS['faction_conflict']['wanted_threshold'])
                p.hostility[key] = max(p.hostility.get(key, 0), threshold + 100)
                p.milestones['became_wanted_target'] = 1
                exposure = f"行迹暴露！威名 +{info['fame_penalty']}，{here['owner_name']}发出通缉。"
            game.rng_state = encode_rng(rng)
        if forged:
            deps._instant_arrival(game, destination)
            if action == 'temporary':
                p.teleport_passes[permission]['used'] = True
            method = {'travel': '', 'bribe': '买通守阵人偷渡，', 'assassinate': '暗杀守阵人偷渡，', 'forge':'凭伪造通行证偷渡，', 'temporary':'凭单次临时通行证，'}[action]
            summary = f"{method}瞬息抵达{deps.maps.location(p.world, destination)['name']}，不增加年龄。{exposure}"
            summary += arrival_notice(game)
        else:
            summary = f"伪造通行证被识破，留在原地，材料费用已消耗。{exposure}"
    else:
        raise ValueError('未知传送操作')
    game.history.append(HistoryRecord('SYS_TELEPORT', 1, p.age, '挪移虚空', action, 'completed', summary, {}, ['travel']))
    game.updated_at = now_iso()
    deps.store.save(game)
    return deps.present(game)
