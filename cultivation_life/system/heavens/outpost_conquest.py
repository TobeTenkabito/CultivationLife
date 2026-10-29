"""Player-chartered local campaigns over original armies, wars and treaties."""
from .outpost_routes import profile
import random
from ...regional_context import task_active, ordinary_year
from ...runtime import decode_rng, encode_rng
from ...world_state import race_pair
from ..economy.ledger import balance, transfer_value
from ..faction_geography import faction_site
from ..territory import state as territory
from ..territory.anchors import operational
from ..war.occupancy import busy
from ..war.creation import create
from ..war import logistics, requirements
from . import outpost_runtime as base, outpost_development as development, conquest_logistics as stores
from .conquest_definitions import LABELS, BATTLE_INTERVAL, WAR_LIMIT
from .outpost_definitions import ENDPOINTS


def wars(game, row):
    return [w for w in game.wars if w.get('outpost_id') == row['id']]


def current(game, row):
    return next((w for w in reversed(wars(game, row)) if w['campaign_phase'] != 'home'), None)


def unit_for(row, identity):
    return next((u for u in row['units'] if u['person_id'] == identity), None)


def plan(deps, game, row, options):
    development.ready(deps, game, row)
    if not row.get('development') or not row.get('military'):
        raise ValueError('须先开办地方经营，并由原总部另行批准当地征战军令')
    if current(game, row):
        raise ValueError('原驻地战役仍在行军、交战或撤回')
    own, enemy = deps.outpost_owner(game, row['owner_id']), deps.outpost_owner(game, options['rival_id'])
    if not enemy or enemy.extinct or enemy.kind not in {'sect', 'family'} or enemy.world != row['destination'] or enemy.id == own.id:
        raise ValueError('须选择目的界面真实存在的其他宗门或家族')
    if enemy.id == game.player.faction_id or enemy is game.family:
        raise ValueError('不能使用开拓军令进攻本人所属的宗门或家族')
    if busy(game, own) or busy(game, enemy):
        raise ValueError('参战组织已有战争，原军队归返前不能另开战役')
    relation = game.sect_relations.get(race_pair(own.id, enemy.id), {})
    if relation.get('status') in {'alliance', 'vassal'}:
        raise ValueError('不能以此军令直接进攻现有盟友或依附关系对象')
    if game.player.age < relation.get('truce_until_age', 0) or game.diplomacy_unit < max(relation.get('truce_until_unit', 0), relation.get('war_truce_until_unit', 0)):
        raise ValueError('原和约停战期尚未结束')
    maps = deps.outpost_maps()
    location = faction_site(enemy, persist=False)['id']
    site = maps.location(row['destination'], location)
    if not site or site.get('min_realm_index', 0) or deps.outpost_site_reason(game, row, location):
        raise ValueError('目标驻地受境界门槛或实际驻军封锁限制')
    book = territory.snapshot(game, maps, row['destination'])
    frontier = [location, *(loc for loc, _ in maps._graphs[row['destination']][location])]
    if not any((claim := book.get(loc, {}).get(own.id)) and claim['outpost'] and claim['value'] >= 50 for loc in frontier):
        raise ValueError('须先在目标或相邻地区经营出一处影响至少50的实际驻点')
    person = options['person_id']
    if person not in {p['id'] for p in development.workers(deps, game, row)}:
        raise ValueError('须选择实际到场的空闲原门人，负责人须留守驻地')
    npc = deps.resolve_person(game, person)
    outward = deps.outpost_road(game, row['destination'], ENDPOINTS[row['destination']], location, npc.realm_index)
    homeward = deps.outpost_road(game, row['destination'], location, ENDPOINTS[row['destination']], npc.realm_index)
    if not outward or not homeward:
        raise ValueError('原出征门人没有合法往返道路')
    defense = deps.outpost_defenders(game, row, location, enemy.id)
    defenders = defense['people']
    if not defenders:
        raise ValueError('当地没有可实际应战的原守军，不虚构战争或战果')
    travel = (outward['years'] + homeward['years']) * profile(row['source'])['annual']
    if balance(game, base.wallet(row)) < profile(row['source'])['war_budget'] + travel + 3*profile(row['source'])['annual']:
        raise ValueError(f'当地须实有军费{profile(row['source'])['war_budget']}、往返行旅{travel}及驻地养护{3*profile(row['source'])['annual']}灵石')
    history = wars(game, row)
    if len(history) >= WAR_LIMIT and not any(w['campaign_phase'] == 'home' and not stores.pending(w) for w in history):
        raise ValueError('原战役仍有未结清实物，请先结清归返军需')
    return dict(enemy=enemy, npc=npc, outward=outward, homeward=homeward, defenders=defenders, guests=defense['guests'], location=location, travel=travel)


def quote(deps, game, row, action, options):
    if action == 'outpost_military_authorize':
        entity = deps.outpost_owner(game, row['owner_id'])
        if not deps.outpost_control(game, entity, row) or (game.player.world, game.player.location_id) != (row['source'], row['home']) or faction_site(entity, persist=False)['id'] != row['home']:
            raise ValueError('须原实际控制者亲自在未迁址的原总部签发军令')
        if row.get('military') or row['status'] in {'closed', 'withdrawing'}:
            raise ValueError('已有原军令，或驻地已撤回')
        message = '单独批准已到场门人的当地征战；民用跨界通道仍只运送民用派驻者，不另授军队跨界输送权。'
    elif action == 'outpost_war_start':
        p = plan(deps, game, row, options)
        return dict(years=0, costs={'organization_stones': profile(row['source'])['war_budget']+p['travel']}, refundable={}, message=f'原门人循路赴{p["enemy"].name}驻地；去程{p["outward"]["years"]}年，返程{p["homeward"]["years"]}年。军费从当地实付，原总部不出虚兵。')
    else:
        war = current(game, row) or next(iter(reversed(wars(game, row))), None)
        if not war:
            raise ValueError('没有本驻地原战役')
        if not deps.outpost_control(game, deps.outpost_owner(game, row['owner_id']), row):
            raise ValueError('原组织控制权已经失效')
        if action == 'outpost_war_fight':
            if war['status'] != 'active' or war['campaign_phase'] != 'engaged' or (game.player.world, game.player.location_id) != (war['world'], war['location_id']):
                raise ValueError('须本人循地图道路抵达仍在交战的实际战场')
            if game.player.age < war['frontier']['player_last_year'] + BATTLE_INTERVAL:
                raise ValueError('本人参战每十个实际年一次，不能连续刷新会战')
            if not requirements.deployed_people(game, war, 'attacker', arrived_only=True) or not requirements.deployed_people(game, war, 'defender', arrived_only=True):
                raise ValueError('须有双方实际在场的原参战者')
            message = '使用原会战与本人战斗结算，消耗原军需并承担真实伤亡。'
        else:
            if (game.player.world, game.player.location_id) != (row['destination'], ENDPOINTS[row['destination']]):
                raise ValueError('须亲自在异界主驻地处理军令及和约')
            if action == 'outpost_war_vassal':
                if war['status'] != 'peace_ready' or war.get('winner') != 'attacker' or not war['frontier']['victory_battles'] or war['war_score'] < deps.outpost_vassal_cost():
                    raise ValueError('须有原战役真实胜利且战争分数达到原依附条款要求')
                enemy = deps.outpost_owner(game, war['defender_id'])
                if not enemy or enemy.extinct or enemy.world != war['world'] or faction_site(enemy, persist=False)['id'] != war['location_id']:
                    raise ValueError('战败组织或原目标驻地已变化，不能套用旧战果')
                if not requirements.deployed_people(game, war, 'attacker', arrived_only=True):
                    raise ValueError('实际战场已无本方部众，不能远领征服战果')
                message = '沿原战争依附条款确立原组织的宗主／附庸关系，不复制对方宗门、人物或资产。'
            elif action == 'outpost_war_stop':
                if war['campaign_phase'] in {'returning', 'home'}:
                    raise ValueError('原军队已经在撤回或结清')
                message = '沿原白和收束，原部众实际循路返驻地后才退剩余原款与实物。'
            elif action == 'outpost_war_settle':
                if war['campaign_phase'] != 'home' or not stores.pending(war):
                    raise ValueError('没有已实际归返且待交割的原军需')
                message = '仅向实际当地市场出售已归返的原军需，买方不足款则保留剩余实物。'
    return dict(years=0, costs={}, refundable={}, message=message)


def journey(person, origin, destination, outward, homeward, travel):
    return dict(person_id=person, origin=origin, destination=destination, route=outward['route'], years=outward['years'],
                return_route=homeward['route'], return_years=homeward['years'], progress=0, duration=outward['years'],
                phase='outbound' if outward['years'] else 'stationed', travel_paid=travel, travel_spent=0)


def execute(deps, game, row, action, options):
    if action == 'outpost_military_authorize':
        row['military'] = dict(issuer_id=game.id, granted_at=game.player.age, source=row['source'], destination=row['destination'])
    elif action == 'outpost_war_start':
        p = plan(deps, game, row, options)
        history = wars(game, row)
        if len(history) >= WAR_LIMIT:
            old = next(w for w in history if w['campaign_phase'] == 'home' and not stores.pending(w))
            for side in ('attacker', 'defender'):
                game.economy_v2['accounts'].pop(logistics.wallet(old, side), None)
            game.wars.remove(old)
        war = create(game, 'sect', row['destination'], row['owner_id'], p['enemy'].id, [p['npc'].id], [n.id for n in p['defenders']])
        war.update(outpost_id=row['id'], location_id=p['location'], defensive_guests=p['guests'], player_side='attacker', controller='player', campaign_phase='marching',
            frontier=dict(last_year=game.player.age, next_battle=game.player.age+BATTLE_INTERVAL, deadline=game.player.age+p['outward']['years']+200,
                          player_last_year=0, victory_battles=0, occupation=0, occupation_awarded=False))
        war['journeys'] = {'attacker': [journey(p['npc'].id, ENDPOINTS[row['destination']], p['location'], p['outward'], p['homeward'], p['travel'])],
                          'defender': [journey(n.id, p['location'], p['location'], dict(route=[p['location']], years=0), dict(route=[p['location']], years=0), 0) for n in p['defenders']]}
        unit = unit_for(row, p['npc'].id)
        transfer_value(game, base.wallet(row), unit['wallet'], p['travel'], '原门人地方军事往返费用独立随身预留')
        unit.update(phase='campaign', progress=0, duration=0, war_id=war['id'])
        for npc in p['defenders']:
            if npc.location_id is None:
                # None is the native roster's existing implicit headquarters
                # address, already verified by local_people; make it explicit
                # for the shared battlefield-presence checks, without travel.
                deps.outpost_move_npc(game, npc.id, row['destination'], p['location'])
        stores.initialize(deps, game, row, war)
        deps.outpost_register_war(game, war)
        game.sect_relations.setdefault(race_pair(row['owner_id'], p['enemy'].id), {}).update(status='war', affinity=-75., since_age=game.player.age)
    else:
        war = current(game, row) or wars(game, row)[-1]
        if action == 'outpost_war_fight':
            rng = decode_rng(game.seed, game.rng_state)
            deps.outpost_war_round(game, war, rng, True)
            game.rng_state = encode_rng(rng)
            war['frontier']['player_last_year'] = game.player.age
        elif action in {'outpost_war_vassal', 'outpost_war_stop'}:
            conclude(deps, game, row, war, 'vassal' if action == 'outpost_war_vassal' else 'white_peace')
        else:
            stores.refund(deps, game, row, war)
    base.note(game, row, LABELS[action]+'，沿原人物、原战役与实款办理。')
    return {'message': LABELS[action]+'已办理'}


def conclude(deps, game, row, war, term='white_peace'):
    deps.outpost_conclude_war(game, war, term)
    war.update(status='withdrawing', campaign_phase='returning')
    for side, journeys in war['journeys'].items():
        for j in journeys:
            if j['phase'] in {'home', 'lost'}: continue
            j.update(duration=0 if j['phase'] == 'outbound' else j['return_years'], progress=0, phase='returning')


def advance_person(deps, game, row, war, side, j):
    if j['phase'] in {'home', 'lost'}: return
    npc = deps.resolve_person(game, j['person_id'])
    unit = unit_for(row, j['person_id']) if side == 'attacker' else None
    if not npc or not npc.alive:
        j['phase'] = 'lost'
        if unit:
            transfer_value(game, unit['wallet'], f'background:{war["world"]}', balance(game, unit['wallet']), '当地征战陨落，原随身款遗失')
            unit.update(phase='lost', war_id=war['id'])
        return
    entity = deps.outpost_owner(game, war[f'{side}_id'])
    member = npc.faction_id == war[f'{side}_id'] or bool(entity and any(n.id == npc.id for n in entity.npcs)) or side == 'defender' and npc.id in war['defensive_guests']
    if not base.free(game, npc) or not member or npc.world != war['world']:
        return
    if j['phase'] == 'stationed': return
    outward = j['phase'] == 'outbound'
    expected = j['origin'] if outward or not j['duration'] else j['destination']
    if npc.location_id != expected: return
    if j['progress'] < j['duration']:
        route = deps.outpost_road(game, war['world'], expected, j['destination'] if outward else j['origin'], npc.realm_index)
        if not route or route['years'] > j['duration']: return
        if unit:
            if j['travel_spent']+profile(row['source'])['annual'] > j['travel_paid'] or balance(game, unit['wallet']) < profile(row['source'])['annual']: return
            transfer_value(game, unit['wallet'], f'background:{war["world"]}', profile(row['source'])['annual'], '原驻地部众实际年度行军')
            j['travel_spent'] += profile(row['source'])['annual']
        j['progress'] += 1
    if j['progress'] < j['duration']: return
    deps.outpost_move_npc(game, npc.id, war['world'], j['destination'] if outward else j['origin'])
    j.update(phase='stationed' if outward else 'home', progress=0, duration=0)
    if not outward and unit:
        transfer_value(game, unit['wallet'], base.wallet(row), j['travel_paid']-j['travel_spent'], '原部众实际返抵驻地，未耗地方路费归还')
        unit.pop('war_id', None)
        unit.update(phase='stationed', last_year=game.player.age)


def advance(deps, game, row):
    if not task_active(game, row['destination']) or not ordinary_year(game): return
    war = current(game, row)
    if not war or war['frontier']['last_year'] >= game.player.age: return
    war['frontier']['last_year'] = game.player.age
    for side, journeys in war['journeys'].items():
        for j in journeys: advance_person(deps, game, row, war, side, j)
    if war['campaign_phase'] == 'returning':
        if all(j['phase'] in {'home', 'lost'} for rows in war['journeys'].values() for j in rows):
            war.update(status='ended', campaign_phase='home')
            stores.refund(deps, game, row, war)
        return
    enemy = deps.outpost_owner(game, war['defender_id'])
    if (row['status'] in {'closed', 'withdrawing'} or not operational(game, row) or not enemy or enemy.extinct
            or enemy.world != war['world'] or faction_site(enemy, persist=False)['id'] != war['location_id']
            or game.player.age >= war['frontier']['deadline']):
        conclude(deps, game, row, war)
        return
    if war['campaign_phase'] == 'marching':
        if not any(j['phase'] == 'outbound' for j in war['journeys']['attacker']):
            war['campaign_phase'] = 'engaged'
            war['frontier']['next_battle'] = game.player.age+BATTLE_INTERVAL
            for side in ('attacker', 'defender'):
                requirements.refresh(game, war, side)
                logistics.replenish(game, deps.outpost_maps(), war, side)
        return
    attackers = requirements.deployed_people(game, war, 'attacker', arrived_only=True)
    if not attackers:
        conclude(deps, game, row, war)
        return
    if war['status'] == 'active' and game.player.age >= war['frontier']['next_battle']:
        rng = random.Random(f'{game.seed}:{row["id"]}:{war["start_age"]}:{war["battles"]}')
        deps.outpost_war_round(game, war, rng, False)
        war['frontier']['next_battle'] = game.player.age+BATTLE_INTERVAL
    if war['status'] == 'peace_ready' and war.get('winner') == 'attacker' and war['frontier']['victory_battles'] and not requirements.deployed_people(game, war, 'defender', arrived_only=True):
        # Five actual years of uncontested, supplied occupation of the real
        # headquarters earn one 35-point objective, never a replayed click.
        if not war['frontier']['occupation_awarded'] and balance(game, logistics.wallet(war, 'attacker')) >= profile(row['source'])['annual']:
            transfer_value(game, logistics.wallet(war, 'attacker'), f'background:{war["world"]}', profile(row['source'])['annual'], '原部众实际控制目标驻地年度开支')
            war['frontier']['occupation'] += 1
            if war['frontier']['occupation'] == 5:
                war['frontier']['occupation_awarded'] = True
                war['war_score'] = min(100., war['war_score']+35)
                base.note(game, row, '原部众实际控制战败总部五年，取得一次35分总部目标战果。')


def project(deps, game, row, target, blocked=None):
    result = dict(actions=[], rivals=[], workers=[], war=None)
    if not row: return result
    result['authorized'] = bool(row.get('military'))
    result['workers'] = development.workers(deps, game, row)
    local = (game.player.world, game.player.location_id) == (row['destination'], ENDPOINTS[row['destination']])
    if local:
        for entity in deps.outpost_organizations(game):
            if entity.world == row['destination'] and entity.id != row['owner_id'] and not entity.extinct and entity.kind in {'sect', 'family'}:
                location = faction_site(entity, persist=False)['id']
                site = deps.outpost_maps().location(row['destination'], location)
                result['rivals'].append(dict(id=entity.id, name=entity.name, location=location, location_name=site['name'] if site else '未知地点'))
    war = current(game, row) or next(iter(reversed(wars(game, row))), None)
    if war and game.player.world == row['destination']:
        enemy = deps.outpost_owner(game, war['defender_id'])
        result['war'] = dict(id=war['id'], enemy_name=enemy.name if enemy else war['defender_id'],
            location=war['location_id'], location_name=deps.outpost_maps().location(war['world'],war['location_id'])['name'], status=war['status'], phase=war['campaign_phase'], score=round(war['war_score'], 1),
            battles=war['battles'], winner=war.get('winner'), occupation=war['frontier']['occupation'],
            troops=[dict(id=j['person_id'],name=(p.name if (p:=deps.resolve_person(game,j['person_id'])) else '原人物'),phase=j['phase'],progress=j['progress'],duration=j['duration']) for j in war['journeys']['attacker']],
            logs=list(war['logs'][-6:]))
    for action, label in LABELS.items():
        options = {}
        if action == 'outpost_war_start':
            options = dict(person_id=result['workers'][0]['id'] if result['workers'] else '', rival_id=result['rivals'][0]['id'] if result['rivals'] else '')
        item = dict(action=action, target_id=target, label=label, options=options)
        try:
            if blocked: raise ValueError(blocked)
            item.update(quote(deps,game,row,action,options), enabled=True)
        except ValueError as exc: item.update(enabled=False, reason=str(exc))
        result['actions'].append(item)
    if local:
        for rival in result['rivals']:
            candidates = []
            options = dict(rival_id=rival['id'], person_id=result['workers'][0]['id'] if result['workers'] else '')
            control = dict(action='outpost_war_start', target_id=target, label=LABELS['outpost_war_start'], options=options)
            for person in result['workers']:
                try:
                    if blocked: raise ValueError(blocked)
                    quote(deps, game, row, 'outpost_war_start', {**options, 'person_id': person['id']})
                    candidates.append(person)
                except ValueError:
                    continue
            if candidates:
                control['options'] = {**options, 'person_id': candidates[0]['id']}
            try:
                if blocked: raise ValueError(blocked)
                control.update(quote(deps, game, row, 'outpost_war_start', control['options']), enabled=True)
            except ValueError as exc: control.update(enabled=False, reason=str(exc))
            rival.update(command=control, people=candidates)
    return result
