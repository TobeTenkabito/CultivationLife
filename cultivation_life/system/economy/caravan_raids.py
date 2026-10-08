"""Local raids materialize two encounter actors only when the player attacks."""
from ...content_registry import REALMS, WORLD_SYSTEMS
from ...models import HistoryRecord
from ...rules import add_item, expected_combat_power
from ...runtime import decode_rng, encode_rng
from .ledger import balance, transfer_value
from .fleet_network import guard_required


def available(game, fleet):
    from .enterprise_state import owner_allowed
    return bool(fleet and fleet['status'] in {'waiting', 'selling'} and not fleet.get('cross_trip')
                and fleet['world'] == game.player.world and fleet['location'] == game.player.location_id
                and not owner_allowed(game, fleet['owner_kind'], fleet['owner_id'], fleet['world'])
                and not fleet.get('player_controlled') and fleet.get('last_raid_unit') != game.diplomacy_unit)


def attack(game, fleet, mode, combat, cache):
    if not available(game, fleet):
        raise ValueError('只能袭击身边驻留或待售的他人商队，每支每单位一次；在途商队尚未抵达')
    if not combat or not cache:
        raise ValueError('战斗入口不可用')
    from .enterprise_state import owner_allowed
    if owner_allowed(game, fleet['owner_kind'], fleet['owner_id'], fleet['world']):
        raise ValueError('不能劫掠自己执掌的商队')
    rng = decode_rng(game.seed, game.rng_state)
    tier = WORLD_SYSTEMS['world_profiles'][fleet['world']]['tier']
    power = max(20, fleet.get('guard_power', 0))
    realm = max(1, tier + 1 - int(power < guard_required(fleet['world']) * .8))
    members = [dict(name=role, power=max(10, power * share), realm_index=realm, layer=1, race='human', path='dao')
               for role, share in [('商队领队', .45), ('随队护卫', .55)]]
    target = dict(target_name=fleet['name'], target_power=sum(r['power'] for r in members),
                  primary_power=members[0]['power'], target_realm_index=realm, target_layer=1,
                  target_realm_display=REALMS[realm].name, combat_type='cultivator', world=fleet['world'],
                  race='human', members=members, objective='kill' if mode == 'exterminate' else 'repel',
                  enemy_objective='kill', kill_karma=True, non_story_combat=True)
    cache(game, target, rng)
    fleet['last_raid_unit'] = game.diplomacy_unit
    kind = fleet['owner_kind']
    issuer = fleet['owner_id']
    if kind in {'alliance', 'sect', 'family'}:
        identity = f"{fleet['world']}:{issuer}" if kind == 'alliance' else issuer
        key = f'{kind}:{identity}'
        threshold = WORLD_SYSTEMS['faction_conflict']['wanted_threshold']
        game.player.hostility[key] = max(game.player.hostility.get(key, 0), threshold + (90 if mode == 'exterminate' else 35))
        game.player.milestones['became_wanted_target'] = 1
    result, summary = combat(game, target, True, rng)
    won = result in {'victory', 'killed', 'victory_escape', 'victory_controlled'}
    if won:
        # Loot is taken from the one fleet wallet and its actual held cargo.
        source = f'caravan:{fleet["id"]}'
        cash = balance(game, source) * (100 if mode == 'exterminate' and result == 'killed' else 40) // 100
        transfer_value(game, source, 'player', cash, '劫掠商队实际周转金')
        cargo = fleet.get('cargo')
        goods = 0
        if cargo and cargo['quantity']:
            goods = cargo['quantity'] if mode == 'exterminate' and result == 'killed' else max(1, cargo['quantity'] // 2)
            add_item(game.player, cargo['item'], goods)
            cargo['quantity'] -= goods
            fleet['lost'] += goods
        fleet['guard_power'] = max(0, round(power * .5))
        summary += f' 从原商队取得灵石 {cash}、实货 {goods} 件。'
        if mode == 'exterminate' and result == 'killed':
            # The resolved kill destroys the operating collective. Surviving
            # encounter actors keep their real life/custody state, never fake deaths.
            if cargo:
                fleet['lost'] += cargo['quantity']
            fleet.update(status='retired', cargo=None, last_result='遭玩家灭队，商队解散；其余货物毁失')
        else:
            fleet['last_result'] = '遭劫掠，货物与周转金受损'
    if kind in {'alliance', 'sect', 'family'}:
        summary += ' 背后势力已发布通缉令。'
    game.history.append(HistoryRecord('SYS_CARAVAN_RAID', 1, game.player.age, '商路劫掠',
        fleet['id'], result, summary, {'mode': mode}, ['economy', 'combat', 'wanted']))
    game.rng_state = encode_rng(rng)
