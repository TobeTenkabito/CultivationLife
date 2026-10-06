"""One military lane, explicit people and finite supplies on actual world years."""
from .campaign_definitions import (SOURCE, DEFENDER, SOURCE_SITE, TARGET_SITE, LIFT_YEARS,
                                   EVAC_YEARS, BATCH, ANNUAL_COST, TERMINAL_UNITS)


def phase(unit, name, duration=0):
    unit.update(phase=name, duration=duration, progress=0, reason=None)


def located(deps, game, unit, world, location):
    facts = deps.campaign_facts(game, unit)
    return facts['free'] and facts['world'] == world and facts['location'] == location and facts['rank'] <= 5


def stationed(deps, game, row, role):
    return next((u for u in row['units'] if u['role'] == role and u['phase'] == 'stationed'
                 and located(deps, game, u, 'human' if role in {'builder', 'soldier', 'defender'} else 'demon',
                             TARGET_SITE if role in {'builder', 'soldier', 'defender'} else SOURCE_SITE)
                 and deps.campaign_facts(game, u)['wounds'] < 3), None)


def retreat(unit, facts):
    if unit['phase'] in TERMINAL_UNITS or unit['phase'] in {'returning', 'homeward'}:
        return
    world = 'human' if unit['faction_id'] == DEFENDER else 'demon'
    if facts['world'] == world and facts['location'] == unit['home']:
        phase(unit, 'home')
    elif unit['faction_id'] == SOURCE and facts['world'] == 'human':
        phase(unit, 'returning', EVAC_YEARS)
    else:
        phase(unit, 'homeward', unit['road_years'])


def advance_unit(deps, game, row, unit, *, evacuation_busy=False):
    if unit['phase'] in TERMINAL_UNITS:
        return
    facts = deps.campaign_facts(game, unit)
    if not facts['alive'] or facts['rank'] > 5 or facts['world'] not in {'human', 'demon'}:
        phase(unit, 'lost')
        return
    if not facts['free']:
        unit['reason'] = '人物受控，保留身份及原行程'
        return
    if row['status'] == 'withdrawing':
        retreat(unit, facts)
    name = unit['phase']
    if name in {'stationed', 'transport', 'home'}:
        return
    world = 'human' if unit['faction_id'] == DEFENDER else 'demon'
    endpoint = TARGET_SITE if world == 'human' else SOURCE_SITE
    origin = unit['home'] if name == 'gathering' else TARGET_SITE if name == 'returning' else endpoint
    expected_world = 'human' if name == 'returning' else world
    if (facts['world'], facts['location']) != (expected_world, origin):
        unit['reason'] = '人物已离开原地，不能隔空推进行程'
        return
    if name == 'returning' and evacuation_busy:
        unit['reason'] = '单人撤离路线已有先行者'
        return
    if name in {'outbound', 'returning'}:
        target_world = 'human' if name == 'outbound' else 'demon'
        if not deps.campaign_world_open(target_world):
            unit['reason'] = '目标界面关闭，保留原地人物'
            return
    elif not deps.campaign_road(game, world, origin, endpoint if name == 'gathering' else unit['home'],
                               facts['rank'], unit['road_years']):
        unit['reason'] = '原道路不再可通行'
        return
    unit['reason'] = None
    unit['progress'] += 1
    if unit['progress'] < unit['duration']:
        return
    if name == 'gathering':
        deps.campaign_move(game, unit, world, endpoint)
        phase(unit, 'outbound', EVAC_YEARS) if unit['role'] == 'builder' else phase(unit, 'stationed')
    elif name == 'outbound':
        deps.campaign_move(game, unit, 'human', TARGET_SITE)
        phase(unit, 'stationed')
        row['supply']['target'] += row['supply']['carried']
        row['supply']['carried'] = 0
        row['materials']['target']['owner'] = 'target_depot'
    elif name == 'returning':
        deps.campaign_move(game, unit, 'demon', SOURCE_SITE)
        phase(unit, 'homeward', unit['road_years'])
    elif name == 'homeward':
        deps.campaign_move(game, unit, world, unit['home'])
        phase(unit, 'home')


def advance_transport(deps, game, row):
    shipment = row['shipment']
    if row['status'] == 'withdrawing':
        if shipment:
            row['supply']['source'] += shipment['quantity']
            for u in row['units']:
                if u['person_id'] == shipment['person_id'] and u['phase'] == 'transport':
                    phase(u, 'stationed')
            row['shipment'] = None
        return
    if row['gate']['state'] != 'open' or not deps.campaign_world_open('human') or not deps.campaign_world_open('demon'):
        return
    if not stationed(deps, game, row, 'keeper') or not stationed(deps, game, row, 'builder'):
        return
    if shipment is None:
        soldier = next((u for u in row['units'] if u['role'] == 'soldier' and u['phase'] == 'stationed'
                        and located(deps, game, u, 'demon', SOURCE_SITE)), None)
        if soldier:
            phase(soldier, 'transport', LIFT_YEARS)
            row['shipment'] = dict(kind='troop', person_id=soldier['person_id'], quantity=0, progress=0, duration=LIFT_YEARS)
        elif row['supply']['source'] >= BATCH and row['supply']['target'] <= BATCH:
            row['supply']['source'] -= BATCH
            row['shipment'] = dict(kind='supply', person_id=None, quantity=BATCH, progress=0, duration=LIFT_YEARS)
        return
    if shipment['kind'] == 'troop':
        soldier = next(u for u in row['units'] if u['person_id'] == shipment['person_id'])
        if soldier['phase'] != 'transport':
            row['shipment'] = None
            return
        if not located(deps, game, soldier, 'demon', SOURCE_SITE):
            return
    shipment['progress'] += 1
    row['budget']['spent'] += ANNUAL_COST
    if shipment['progress'] < LIFT_YEARS:
        return
    if shipment['kind'] == 'troop':
        deps.campaign_move(game, soldier, 'human', TARGET_SITE)
        phase(soldier, 'stationed')
    else:
        row['supply']['target'] += shipment['quantity']
    row['shipment'] = None
    row['deliveries'] += 1
