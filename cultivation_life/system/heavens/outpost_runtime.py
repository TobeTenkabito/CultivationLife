"""Original frontier people, cargo and local upkeep on regional years."""
from ...economy_content import material_id
from ...npc_custody import is_free
from ...spatial_people import instance_of
from ...regional_context import task_active
from ..economy import depot
from ..economy.ledger import account, balance, transfer_value
from .outpost_definitions import ENDPOINTS, CROSSING_YEARS, BUILD_YEARS, BUILD_COST, ANNUAL_COST


def get(game, target):
    return game.heavens_state.get('runtime', {}).get('outposts', {}).get(target)


def wallet(row):
    return f'heavens-{row["id"]}:local'


def materials(world):
    return {'item:' + material_id(world, 2, role): quantity for role, quantity in
            (('ore_structure', 6), ('ore_conduct', 2), ('ore_store', 2))}


def note(game, row, text):
    row['history'] = (row['history'] + [dict(year=game.player.age, text=text)])[-24:]


def free(game, npc):
    return bool(npc and is_free(npc) and not instance_of(game, npc.id)
                and npc.id not in game.intrigue_state.get('npc_prisons', {}))


def located(deps, game, row, unit):
    npc = deps.resolve_person(game, unit['person_id'])
    return bool(free(game, npc) and npc.world == row['destination']
                and npc.location_id == ENDPOINTS[row['destination']] and unit['phase'] == 'stationed')


def phase(unit, name, duration=0):
    unit.update(phase=name, progress=0, duration=duration)


def recall(row, unit):
    if unit['phase'] == 'stationed':
        phase(unit, 'returning', CROSSING_YEARS)
    elif unit['phase'] == 'outbound':
        # A crossing has not changed the actual address yet. Return the
        # expedition to its home by the original road, retaining spent fares.
        phase(unit, 'homeward', unit['road_years'])
    elif unit['phase'] == 'gathering':
        # As with ordinary travel, the person remains at the departure site
        # until arrival. No refund of the road years already spent.
        phase(unit, 'homeward', 0)


def collect_local(game, row, unit):
    for key, value in row['stock'].items():
        unit['stock'][key] = unit['stock'].get(key, 0) + value
    row['stock'] = {}
    transfer_value(game, wallet(row), unit['wallet'], balance(game, wallet(row)), '驻地撤回：原库存与当地余额装运')


def deliver_local(game, row, unit):
    """Accept original cargo only on a real destination year after arrival.

    The source calendar may already have recorded an arrival while this
    destination is still frozen. Until its own calendar reaches that person,
    the cargo remains in their original purse and inventory, never available
    to pay retrospectively for earlier local construction or upkeep.
    """
    if row['status'] != 'withdrawing':
        for identity, quantity in unit['stock'].items():
            row['stock'][identity] = row['stock'].get(identity, 0) + quantity
        unit['stock'] = {}
        reserve = (CROSSING_YEARS + unit['road_years']) * ANNUAL_COST
        transfer_value(game, unit['wallet'], wallet(row), max(0, balance(game, unit['wallet']) - reserve), '当地实际接收开拓运输原款')
        if row['status'] == 'authorized':
            row['status'] = 'building'
        if row['governor_id'] is None and not unit['courier']:
            row['governor_id'] = unit['person_id']
    unit['delivered'] = True
    note(game, row, '当地已实际接收原门人携带的钱货，不能用于此前未获补给的历史年份。')
    if unit['courier']:
        if row['status'] == 'withdrawing':
            collect_local(game, row, unit)
        recall(row, unit)


def deliver_home(deps, game, row, unit):
    entity = deps.outpost_owner(game, row['owner_id'])
    # Physical cargo returns to its original fixed warehouse even after HQ
    # relocation. Neither a remote treasury nor a new warehouse mints stock.
    key = f'{row["source"]}:{row["owner_id"]}:{row["home"]}'
    store = game.economy_v2['depots'].get(key)
    if store is None:
        return False
    if sum(store['stock'].values()) + sum(unit['stock'].values()) > 10000:
        return False
    for identity, quantity in unit['stock'].items():
        store['stock'][identity] = store['stock'].get(identity, 0) + quantity
    unit['stock'] = {}
    depot.record(store, game, '开拓门人实际归返，原货物交入原址仓库')
    if entity:
        transfer_value(game, unit['wallet'], depot.treasury(game, entity), balance(game, unit['wallet']), '开拓归返：未耗原款结清')
    else:
        # Extinction does not destroy the original money or invent a new
        # recipient. Preserve it in the original expedition escrow.
        return False
    phase(unit, 'home')
    note(game, row, '原门人和在途物资已实际返抵出发仓库，未耗经费仅结清一次。')
    return True


def advance_unit(deps, game, row, unit, year, lane_holder):
    name = unit['phase']
    if name in {'home', 'lost'} or unit['last_year'] >= year:
        return
    npc = deps.resolve_person(game, unit['person_id'])
    owning_world = row['destination'] if name in {'stationed', 'returning'} else row['source']
    if not task_active(game, owning_world):
        return
    unit['last_year'] = year
    if not npc or not npc.alive:
        if balance(game, unit['wallet']):
            transfer_value(game, unit['wallet'], f'background:{owning_world}', balance(game, unit['wallet']), '开拓途中陨落，原随身款遗失')
        unit['stock'] = {}
        phase(unit, 'lost')
        note(game, row, '一位原派驻门人陨落，行程终止；未交货物与随身款遗失，不补生替身。')
        return
    if not free(game, npc) or npc.faction_id != row['owner_id']:
        return
    if row['status'] == 'withdrawing' and name in {'gathering', 'outbound'}:
        recall(row, unit)
        name = unit['phase']
    if name == 'stationed':
        if not unit['delivered'] and npc.world == row['destination'] and npc.location_id == ENDPOINTS[row['destination']]:
            deliver_local(game, row, unit)
        return
    expected = row['home'] if name == 'gathering' or name == 'homeward' and unit['duration'] == 0 else ENDPOINTS[row['destination']] if name == 'returning' else ENDPOINTS[row['source']]
    if (npc.world, npc.location_id) != (owning_world, expected):
        return
    if name in {'outbound', 'returning'}:
        if (lane_holder != unit['person_id'] or not deps.outpost_lane(game, row, returning=name == 'returning', person_id=unit['person_id'])
                or not 1 <= npc.realm_index <= 5):
            return
    elif unit['duration']:
        plan = deps.outpost_road(game, row['source'], row['home'], ENDPOINTS[row['source']], npc.realm_index)
        if not plan or plan['years'] > unit['road_years']:
            return
    if unit['progress'] < unit['duration']:
        if balance(game, unit['wallet']) < ANNUAL_COST:
            return
        transfer_value(game, unit['wallet'], f'background:{owning_world}', ANNUAL_COST, '开拓行程实际年度费用')
        unit['progress'] += 1
    if unit['progress'] < unit['duration']:
        return
    if name == 'gathering':
        deps.outpost_move_npc(game, unit['person_id'], row['source'], ENDPOINTS[row['source']])
        phase(unit, 'outbound', CROSSING_YEARS)
    elif name == 'outbound':
        deps.outpost_move_npc(game, unit['person_id'], row['destination'], ENDPOINTS[row['destination']])
        phase(unit, 'stationed')
        note(game, row, '原门人已实际抵达异界落点；原钱货仍随身，待当地实际年度接收后才可使用。')
    elif name == 'returning':
        deps.outpost_move_npc(game, unit['person_id'], row['source'], ENDPOINTS[row['source']])
        phase(unit, 'homeward', unit['road_years'])
    elif name == 'homeward':
        deps.outpost_move_npc(game, unit['person_id'], row['source'], row['home'])
        # Leave a full original warehouse unchanged and retry unloading in
        # later source years; do not make a second copy of the cargo.
        unit['duration'] = unit['progress'] = 0
        deliver_home(deps, game, row, unit)


def year_step(deps, game):
    from ...regional_context import ordinary_year, region
    if not ordinary_year(game) or (region(game) or game.player.world) in {'lost', 'rift'}:
        return
    from ...person_assignments import outpost_lane_holder
    lane_holder = outpost_lane_holder(game, eligible=lambda row, unit, npc:
        deps.outpost_lane(game, row, returning=unit['phase'] == 'returning', person_id=npc.id))
    for row in game.heavens_state.get('runtime', {}).get('outposts', {}).values():
        year = game.player.age
        resident_ids = {u['person_id'] for u in row['units'] if u['phase'] == 'stationed' and u['last_year'] < year}
        for unit in row['units']:
            advance_unit(deps, game, row, unit, year, lane_holder)
        if (row['status'] == 'withdrawing' and all(u['phase'] in {'home', 'lost'} for u in row['units'])
                and not any(row['stock'].values()) and not balance(game, wallet(row))):
            row.update(status='closed', governor_id=None)
        if not task_active(game, row['destination']) or row['last_year'] >= year:
            continue
        row['last_year'] = year
        residents = [u for u in row['units'] if not u['courier'] and located(deps, game, row, u) and u['person_id'] in resident_ids]
        if row['status'] == 'withdrawing':
            if residents:
                # Exactly one original person carries the remaining local
                # assets. Every resident still performs a real return trip.
                collect_local(game, row, residents[-1])
                for unit in residents:
                    recall(row, unit)
            if all(u['phase'] in {'home', 'lost'} for u in row['units']) and not any(row['stock'].values()) and not balance(game, wallet(row)):
                row.update(status='closed', governor_id=None)
            continue
        entity = deps.outpost_owner(game, row['owner_id'])
        if not entity or entity.extinct:
            row['status'] = 'withdrawing'
            continue
        if row['status'] in {'authorized', 'closed'}:
            continue
        if not residents:
            if row['status'] == 'active':
                row['status'] = 'suspended'
            continue
        if row['status'] == 'building':
            required = materials(row['source'])
            yearly = BUILD_COST // BUILD_YEARS
            if balance(game, wallet(row)) < yearly:
                continue
            if row['progress'] == 0:
                if any(row['stock'].get(k, 0) < n for k, n in required.items()):
                    continue
                for key, quantity in required.items():
                    row['stock'][key] -= quantity
            transfer_value(game, wallet(row), f'background:{row["destination"]}', yearly, '异界驻地实际施工劳务')
            row['progress'] += 1
            if row['progress'] == BUILD_YEARS:
                row['status'] = 'active'
                note(game, row, '异界分驻地施工完成；原总部、人员身份和组织府库保持原归属。')
        elif row['status'] == 'active':
            if row['governor_id'] not in {u['person_id'] for u in residents}:
                row['status'] = 'suspended'
                note(game, row, '原负责人已不能在场履职，驻地暂停；可任命原在场门人接任。')
            elif balance(game, wallet(row)) < ANNUAL_COST:
                row['status'] = 'suspended'
                note(game, row, '当地维护经费不足，驻地暂停经营；库存和人员保留。')
            else:
                transfer_value(game, wallet(row), f'background:{row["destination"]}', ANNUAL_COST, '异界分驻地年度养护')
