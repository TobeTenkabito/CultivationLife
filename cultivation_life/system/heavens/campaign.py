"""Bounded military authorization, construction, logistics and local encounters."""
import random

from .campaign_definitions import (CAMPAIGN_ID, SOURCE, DEFENDER, DONOR, SOURCE_SITE, TARGET_SITE,
    REPORT_SITE, BUILD_YEARS, MANDATE_YEARS, BUDGET, ANNUAL_COST, INITIAL_SUPPLY, CARRIED_SUPPLY,
    ROUTE_ID, EVAC_ROUTE, AID_ROUTE, AID_BUDGET, AID_COST, DEFENSE_BUDGET, TERMINAL_UNITS)
from .campaign_logistics import phase, stationed, located, retreat, advance_unit, advance_transport
from .state import record
from . import settlement


def get(game):
    return game.heavens_state.get('runtime', {}).get('campaign')


def report(game, kind, text, year):
    row = get(game)
    row['known'] = True
    row['reports'] = (row['reports']+[dict(kind=kind, text=text, year=year)])[-24:]
    record(game, text, year=year)


def local(deps, game, location):
    return not deps.frontier_player_reason(game, location)


def permit(source, now, *, route=ROUTE_ID):
    return dict(**source, granted_at=now, expires_at=now+MANDATE_YEARS, route_id=route,
                capacity=1, location=TARGET_SITE if route != AID_ROUTE else REPORT_SITE)


def start(deps, game, now):
    runtime = game.heavens_state['runtime']
    recon = runtime.get('frontier')
    if (not game.heavens_state['generation_enabled'] or not deps.get_definitions().generation_available
            or not recon or recon['status'] != 'completed' or recon['withdrawal']
            or not recon['person_id'] or runtime['ruins']['ward']['component'] is not None):
        return
    if not recon.get('landing_evidence'):
        # R1's completed, non-recalled path necessarily includes the full local
        # survey and both return legs. Derive only that existing terminal fact,
        # on a real annual step, never on reading a legacy save.
        surveyed_at = recon['last_year']-recon['road_years']-10
        if surveyed_at < recon['created_at']:
            return
        recon['landing_evidence'] = dict(world='human', location=TARGET_SITE,
            observer_id=recon['person_id'], surveyed_at=surveyed_at)
    plan = deps.campaign_roster(game, SOURCE, ['builder', 'keeper', 'soldier'])
    if not plan or sum((2*u['road_years']+100)*ANNUAL_COST for u in plan['units']) > BUDGET:
        return
    # One registration only. A returned expedition's physical survey is the
    # evidence; an unrelated player victory never grants military permission.
    items = deps.campaign_materials(game, 'demon', CAMPAIGN_ID, 3)
    row = dict(id=CAMPAIGN_ID, revision=1, created_at=now, last_year=now, status='active',
        authorization=permit(plan['permit'], now), evacuation_route=EVAC_ROUTE,
        evidence=dict(recon['landing_evidence']), motive='recover_linked_ward', units=plan['units'],
        budget=dict(owner=SOURCE, total=BUDGET, spent=0, refunded=0),
        materials={key: dict(item=item, owner='source_depot' if key == 'source' else 'carrier')
                   for key, item in zip(('source', 'target', 'reserve'), items)},
        gate=dict(state='planned', source_progress=0, target_progress=0, stability=0, repair_progress=0),
        supply=dict(source=INITIAL_SUPPLY-CARRIED_SUPPLY, carried=CARRIED_SUPPLY, target=0, spent=0, lost=0),
        shipment=None, deliveries=0, defense=None, defense_requested=False, aid=None,
        known=False, surveyed=False, warning_at=None, warning_received=False, reports=[],
        battles=[], last_battle=now, reason=None)
    runtime['campaign'] = row
    game.heavens_state['definition_versions'][CAMPAIGN_ID] = 1
    for unit in row['units']:
        deps.campaign_deploy(game, unit)
    settlement.delegate(deps, game, row, SOURCE, now)
    if recon['reported']:
        row['defense_requested'] = True
        request_defense(deps, game, now)


def request_defense(deps, game, now):
    row = get(game)
    if row['defense'] is not None:
        return
    plan = deps.campaign_roster(game, DEFENDER, ['defender'])
    budget = dict(owner=DEFENDER, total=DEFENSE_BUDGET, spent=0, refunded=0)
    if not plan or (2*plan['units'][0]['road_years']+40)*ANNUAL_COST > DEFENSE_BUDGET:
        budget['refunded'] = DEFENSE_BUDGET
        row['defense'] = dict(status='declined', authorization=None, budget=budget)
        return
    row['defense'] = dict(status='approved', authorization=permit(plan['permit'], now, route='road:human:lanjiang'), budget=budget)
    for unit in plan['units']:
        deps.campaign_deploy(game, unit)
        row['units'].append(unit)
    settlement.delegate(deps, game, row, DEFENDER, now)


def request_aid(deps, game, now):
    row = get(game)
    authority = deps.campaign_authority(game, DONOR, 'one_material_aid')
    if authority and deps.campaign_world_open('spirit') and deps.campaign_world_open('human'):
        item = deps.campaign_materials(game, 'spirit', 'lanjiang-aid', 1)[0]
        row['aid'] = dict(status='transit', authorization=permit(authority, now, route=AID_ROUTE),
            material=item, progress=0, duration=16, spent=0, refunded=0, owner='shipment', last_year=now,
            notice_progress=0, notice_delivered=False)
        report(game, 'aid', '太玄门批准一件灵界阵材，经限定物资路线运至无棣原，实际运输需十六年；不附带征兵或越界作战权限。', now)
    else:
        row['aid'] = dict(status='declined', authorization=None, material=None, progress=0, duration=16,
                          spent=0, refunded=AID_BUDGET, owner='donor', last_year=now,
                          notice_progress=0, notice_delivered=False)
        report(game, 'aid', '灵界未能批准此次物资援助，未派出运输，也未生成替代人物。', now)


def advance_aid(deps, game, row, now):
    aid = row['aid']
    if not aid or aid['status'] not in {'transit', 'cancelled'} or aid['last_year'] >= now:
        return
    aid['last_year'] = now
    if aid['status'] == 'cancelled':
        if deps.campaign_world_open('human') and deps.campaign_world_open('spirit'):
            aid['notice_progress'] = min(16, aid['notice_progress']+1)
        if aid['notice_progress'] == 16 and not aid['notice_delivered'] and local(deps, game, REPORT_SITE):
            aid['notice_delivered'] = True
            report(game, 'aid_cancelled', '你在无棣原收到灵界回函：原批准已失效，未交付阵材留归原专项；此前运输耗费不退。', now)
        return
    authority = deps.campaign_authority(game, DONOR, 'one_material_aid')
    if (not authority or authority['issuer_id'] != aid['authorization']['issuer_id']
            or now > aid['authorization']['expires_at']):
        aid.update(status='cancelled', owner='donor', refunded=AID_BUDGET-aid['spent'])
        return
    if not deps.campaign_world_open('human') or not deps.campaign_world_open('spirit'):
        return
    aid['progress'] += 1
    aid['spent'] += AID_COST
    if aid['progress'] == aid['duration']:
        aid.update(status='arrived', owner='wudi_depot', refunded=AID_BUDGET-aid['spent'])


def withdraw(row, reason):
    if row['status'] == 'active':
        row.update(status='withdrawing', reason=reason)
        if row['gate']['state'] != 'destroyed':
            row['gate']['state'] = 'interrupted'


def construction(deps, game, row):
    gate = row['gate']
    if gate['state'] == 'destroyed':
        return
    for endpoint, role in [('source', 'keeper'), ('target', 'builder')]:
        unit = stationed(deps, game, row, role)
        if not unit:
            continue
        material = row['materials'][endpoint]
        if material['owner'] == endpoint+'_depot':
            material['owner'] = endpoint+'_gate'
        if endpoint == 'target' and row['materials']['reserve']['owner'] == 'carrier':
            row['materials']['reserve']['owner'] = 'target_depot'
        if material['owner'] == endpoint+'_gate' and gate[endpoint+'_progress'] < BUILD_YEARS:
            gate[endpoint+'_progress'] += 1
            gate['state'] = 'building'
    if min(gate['source_progress'], gate['target_progress']) < BUILD_YEARS:
        return
    supported = bool(stationed(deps, game, row, 'keeper') and stationed(deps, game, row, 'builder')
                     and deps.campaign_world_open('human') and deps.campaign_world_open('demon'))
    if gate['state'] == 'building':
        gate.update(state='open', stability=100)
    if supported and row['supply']['target']:
        row['supply']['target'] -= 1
        row['supply']['spent'] += 1
        reserve = row['materials']['reserve']
        if gate['stability'] < 80 and reserve['owner'] == 'target_depot':
            gate['repair_progress'] += 1
            if gate['repair_progress'] == 4:
                reserve['owner'] = 'spent'
                gate['stability'] = 100
    else:
        gate['stability'] = max(0, gate['stability']-10)
    gate['state'] = 'open' if supported and gate['stability'] >= 50 else 'interrupted'
    if not gate['stability']:
        withdraw(row, '界门失稳且补给无法维持，按已批准单人路线撤离')


def observe(deps, game, row, now):
    builder = next(u for u in row['units'] if u['role'] == 'builder')
    present = located(deps, game, builder, 'human', TARGET_SITE)
    if present and stationed(deps, game, row, 'defender') and row['warning_at'] is None:
        row['warning_at'] = now+2  # One authorized human warning relay, not the broken inter-world ward.
    direct = present and local(deps, game, TARGET_SITE)
    delivered = row['warning_at'] is not None and now >= row['warning_at'] and local(deps, game, REPORT_SITE)
    if not row['warning_received'] and (direct or delivered):
        row['warning_received'] = True
        report(game, 'warning', '岚疆发现血狱魔宗界门施工。消息来自现场目击，尚须亲自查勘；这不是对整个人界的宣战。', now)
        runtime = game.heavens_state['runtime']
        runtime['notifications'] = (runtime['notifications']+[dict(id=CAMPAIGN_ID, text='岚疆界门施工预警已送达', expires_at=now+120)])[-3:]
        if game.heavens_state['watch'] and runtime['pause_on_opportunity']:
            runtime['pause_requested'] = True
    if direct:
        for unit in row['units']:
            if located(deps, game, unit, 'human', TARGET_SITE):
                unit['observed'] = True


def battles(deps, game, row, now):
    if settlement.treaty_active(row):
        return
    if now-row['last_battle'] < 8 or len(row['battles']) >= 6:
        return
    attacker, defender = stationed(deps, game, row, 'soldier'), stationed(deps, game, row, 'defender')
    if not attacker or not defender or not row['supply']['target']:
        return
    rng = random.Random(f'{game.seed}:{CAMPAIGN_ID}:{len(row["battles"])}')
    result = deps.campaign_battle(game, attacker['person_id'], defender['person_id'], rng)
    row['last_battle'] = now
    row['battles'].append(dict(year=now, attacker=attacker['person_id'], defender=defender['person_id'], outcome=result.outcome))
    if result.outcome != 'stalemate':
        loser = defender if result.outcome == 'victory' else attacker
        retreat(loser, deps.campaign_facts(game, loser))
    if local(deps, game, TARGET_SITE):
        report(game, 'battle', '你亲见双方在界门附近交锋，实际伤势与败退已经保留；此次交锋没有改变任何地点的政治归属。', now)


def year_step(deps, game):
    runtime = game.heavens_state.get('runtime')
    if not runtime:
        return
    now = runtime['processed_years']+1
    row = get(game)
    if row is None:
        start(deps, game, now)
        return
    if row['last_year'] >= now:
        return
    row['last_year'] = now
    advance_aid(deps, game, row, now)
    settlement.before_year(deps, game, row, now, withdraw)
    if row['status'] in {'withdrawn', 'failed'}:
        settlement.after_year(deps, game, row, now, withdraw)
        return
    if row['status'] == 'active' and runtime['frontier']['reported'] and not row['defense_requested']:
        row['defense_requested'] = True
        request_defense(deps, game, now)
    authorization = deps.campaign_authority(game, SOURCE, 'build_and_supply')
    if (not authorization or authorization['issuer_id'] != row['authorization']['issuer_id']
            or now > row['authorization']['expires_at']):
        withdraw(row, '军事批准已失效，停止施工和输送')
    reserve = sum((u['road_years']+8)*ANNUAL_COST for u in row['units'] if u['faction_id'] == SOURCE)
    if BUDGET-row['budget']['spent'] <= reserve:
        withdraw(row, '只余已预留的实际返乡经费')
    evacuation_busy = False
    for unit in row['units']:
        if unit['faction_id'] == DEFENDER:
            defense = row['defense']
            authority = deps.campaign_authority(game, DEFENDER, 'guard_lanjiang')
            if (not authority or authority['issuer_id'] != defense['authorization']['issuer_id']
                    or now > defense['authorization']['expires_at']
                    or DEFENSE_BUDGET-defense['budget']['spent'] <= unit['road_years']*ANNUAL_COST):
                retreat(unit, deps.campaign_facts(game, unit))
        before = (unit['phase'], unit['progress'])
        advance_unit(deps, game, row, unit, evacuation_busy=evacuation_busy)
        changed = (unit['phase'], unit['progress']) != before
        if (before[0] == 'returning' or unit['phase'] == 'returning') and changed:
            evacuation_busy = True
        chargeable = (changed and unit['phase'] != 'lost' or unit['phase'] == 'stationed') and deps.campaign_facts(game, unit)['free']
        if chargeable:
            ledger = row['budget'] if unit['faction_id'] == SOURCE else row['defense']['budget']
            ledger['spent'] += ANNUAL_COST
        if unit['faction_id'] == DEFENDER and unit['phase'] in TERMINAL_UNITS:
            ledger = row['defense']['budget']
            ledger['refunded'] = DEFENSE_BUDGET-ledger['spent']
    builder = next(u for u in row['units'] if u['role'] == 'builder')
    if builder['phase'] == 'lost':
        withdraw(row, '原阵师已无法履职，不补生施工人物')
        for key in ('target', 'reserve'):
            if row['materials'][key]['owner'] == 'carrier':
                row['materials'][key]['owner'] = 'lost'
        row['supply']['lost'] += row['supply']['carried']
        row['supply']['carried'] = 0
    if row['status'] == 'active':
        construction(deps, game, row)
        observe(deps, game, row, now)
        battles(deps, game, row, now)
    advance_transport(deps, game, row)
    if all(u['phase'] in TERMINAL_UNITS for u in row['units']):
        row['status'] = 'withdrawn'
        row['budget']['refunded'] = BUDGET-row['budget']['spent']
    settlement.after_year(deps, game, row, now, withdraw)
