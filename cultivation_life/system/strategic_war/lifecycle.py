"""Calendar orchestration. Campaigns alone own people, money and casualties."""
from ...models import HistoryRecord
from ...race_diplomacy import relations_for
from ...world_state import race_pair
from ...npc_custody import is_free
from .rules import SIDES, WORLDS, OPEN, organizations, army, ref, site, owns, local_races
from .rules import routes as _routes
from .records import note
from .rules import representatives as eligible_representatives, committed_org


def compact(game):
    state=game.strategic_war_state
    state['wars']=[w for w in state.get('wars',[]) if w['status'] in OPEN]+[w for w in state.get('wars',[]) if w['status']=='ended'][-20:]
    for row in state['wars']:
        if row['status']=='ended':
            row['logs']=row['logs'][-6:]
    retained={w['id'] for w in state['wars']}
    retired=[w for w in game.wars if w.get('strategic_war_id') and w['strategic_war_id'] not in retained
             and w.get('status')=='ended' and w.get('logistics',{}).get('refunded')
             and not any(n>0 for s in w['logistics']['sides'].values() for n in s.get('items',{}).values())
             and not any(game.economy_v2.get('accounts',{}).get(key,{}).get('balance',0)>0
                         for key in [*[r['wallet'] for r in w.get('reinforcements',[])],
                                     *[f"war-supply:{w['id']}:{s}" for s in SIDES]])]
    for w in retired:
        for reinforcement in w.get('reinforcements',[]):
            key=reinforcement['wallet']
            if game.economy_v2.get('accounts',{}).get(key,{}).get('balance')==0:
                game.economy_v2['accounts'].pop(key)
        for side in SIDES:
            key=f"war-supply:{w['id']}:{side}"
            if game.economy_v2.get('accounts',{}).get(key,{}).get('balance')==0:
                game.economy_v2['accounts'].pop(key)
    retired_ids={w['id'] for w in retired}
    game.wars[:]=[w for w in game.wars if w['id'] not in retired_ids]


def start(deps, game, first, second):
    world = game.player.world
    state = game.strategic_war_state
    current = next((w for w in state.get('wars', []) if w['world'] == world
                    and {w['attacker'], w['defender']} == {first, second} and w['status'] in OPEN), None)
    if current:
        raise ValueError('双方已有未完结的战争，请先完成和谈与撤军')
    if world not in WORLDS or first == second or not {first, second} <= set(local_races(world)):
        raise ValueError('当前仅开放灵界、真魔界的同界种族战争')
    if any(w.get('kind') == 'race' and w.get('status') in {'active', 'peace_ready'}
           and w.get('world') == world and {first, second} & {w.get('attacker_id'), w.get('defender_id')}
           for w in game.wars):
        raise ValueError('相关旧族战尚未办理接续，请先在战争页处理原案')
    if any(':' not in k and not v.get('adopted_world') and ({first, second} & set(k.split('|')))
           for k,v in game.race_relations.items()):
        raise ValueError('存在归属待确认的旧种族关系，请先确认原约所在界面')
    if sum(w['status'] in OPEN for w in state.get('wars', [])) >= 2:
        raise ValueError('已有两场战略战争，须先完成其中一场')
    relation = relations_for(game, world).get(race_pair(first, second), {})
    if max(relation.get('truce_until_age', 0), 0) > game.player.age:
        raise ValueError('双方仍在日历停战期内')
    sequence = state.get('sequence', 0) + 1
    row = dict(id=f'strategy-{sequence}', world=world, attacker=first, defender=second,
               status='mobilizing', revision=0, start_age=game.player.age, last_age=game.player.age,
               commitments=[], objectives=[], campaigns=[], receipts={}, commanders={}, logs=[], score=0)
    state['sequence'] = sequence
    state.setdefault('wars', []).append(row)
    compact(game)
    note(game, row, '族议宣战', '征询本界宗门与家族；政治支持须经组织承诺才形成军力。')
    game.history.append(HistoryRecord('SYS_STRATEGIC_WAR', 1, game.player.age, '族议宣战', row['id'], 'mobilizing',
        '种族战争进入动员，军队由实际承诺的宗门与家族组成。', {'strategic_war_id': row['id']},
        ['system', 'war', 'diplomacy', 'world_news', f'world:{world}']))
    return row


def commit(deps, game, row, org):
    from ..war.logistics import cash
    if row['status'] not in {'mobilizing', 'active'} or org.world != row['world'] or org.extinct:
        raise ValueError('当前不能追加组织承诺')
    side = next((s for s in SIDES if org.allegiance_race == row[s]), None)
    if not side or any(c['org'] == ref(org) for c in row['commitments']):
        raise ValueError('组织不支持本案阵营，或已经作出承诺')
    if sum(c['side'] == side for c in row['commitments']) >= 6:
        raise ValueError('本阵营承诺组织已达六家上限')
    from ..war.occupancy import busy
    if busy(game, org):
        raise ValueError('此组织仍在原战役中，须完全闲置后才能批准新案')
    people = army(deps, game, org)
    if not people:
        raise ValueError('组织没有可合法出征的自由修士')
    budget = int(cash(game, org) * .2)
    row['commitments'].append(dict(org=ref(org), side=side, budget=budget,
                                   representative=people[0].id, approved_age=game.player.age))
    note(game, row, '组织承诺', f'{org.name}批准本案动员；军费上限 {budget} 灵石折值，原库实际支付。')


def _elect(deps, game, row):
    from .politics import player_eligible
    for side in SIDES:
        representatives = []
        for c in row['commitments']:
            org = next((o for o in organizations(game, row['world']) if ref(o) == c['org']), None)
            if c['side'] != side or not org:
                continue
            available = eligible_representatives(deps,game,row,c)
            representative = max(available, key=lambda n: (n.realm_index, deps.power(n), n.id), default=None)
            if representative:
                c['representative']=representative.id
                representatives.append(representative)
        # Distinct actual representatives each cast one vote for the strongest
        # available nominee. Shared elders cannot acquire duplicate ballots.
        unique = {n.id: n for n in representatives}
        selected = max(unique.values(), key=lambda n: (n.realm_index, deps.power(n), n.id), default=None)
        old = row['commanders'].get(side, {})
        if (old.get('person_id') == 'player' and old.get('expires',0)>game.player.age
                and player_eligible(deps,game,row,side)):
            continue
        if selected and (old.get('person_id') not in unique or old.get('expires', 0) <= game.player.age):
            row['commanders'][side] = dict(person_id=selected.id, name=selected.name,
                expires=game.player.age + 100, votes=len(unique), electorate=len(unique))
            note(game, row, '联军推举', f'{selected.name}获 {len(unique)}/{len(unique)} 位组织代表推举。')
        elif not selected:
            row['commanders'].pop(side,None)


def _launch(deps, game, row):
    from ..war.logistics import initialize
    pool = {o.id: o for o in organizations(game, row['world'])}
    from ..war.occupancy import busy
    sides = {s: [c for c in row['commitments'] if c['side'] == s
                 and (org:=committed_org(game,row,c)) and not busy(game,org) and army(deps,game,org)] for s in SIDES}
    # Two genuine organization objectives, at most two simultaneous campaigns.
    if min(map(len, sides.values())) < 2:
        return
    plans=[]
    reserved=set()
    reserved_members=set()
    for index in range(2):
        a, d = (pool[sides[s][index]['org']['id']] for s in SIDES)
        from ..war.occupancy import busy
        if busy(game, a) or busy(game, d):
            continue
        members={n.id for org in (a,d) for n in org.npcs}
        if members & reserved_members:
            continue
        people = {s: army(deps, game, org) for s, org in [('attacker', a), ('defender', d)]}
        if not all(people.values()):
            continue
        relation=game.sect_relations.get(race_pair(a.id,d.id),{})
        if game.diplomacy_unit < max(relation.get('truce_until_unit',0),relation.get('war_truce_until_unit',0)):
            continue
        target = site(d)
        if deps.maps.location(row['world'],target).get('min_realm_index',0):
            continue
        try:
            journeys = {s: _routes(deps, game, people[s], target, site(org))
                        for s, org in [('attacker', a), ('defender', d)]}
        except ValueError:
            continue
        # The local expedition uses the ready vanguard; slower members remain
        # at their actual homes instead of freezing a whole organization for
        # the slowest recruit's centuries-long walk.
        for s in SIDES:
            ceiling = min(j['years'] for j in journeys[s]) + 10
            journeys[s] = [j for j in journeys[s] if j['years'] <= ceiling]
            chosen = {j['person_id'] for j in journeys[s]}
            people[s] = [n for n in people[s] if n.id in chosen]
        selected={n.id for ns in people.values() for n in ns}
        if selected & reserved or len(selected)!=sum(len(ns) for ns in people.values()):
            continue
        cargo={}
        for s,org in [('attacker',a),('defender',d)]:
            origin=site(org)
            plan=deps.maps.travel_plan(row['world'],origin,target,min(n.realm_index for n in people[s])) if origin!=target else None
            years=plan.years if plan else 0
            cargo[s]=dict(origin=origin,destination=target,route=list(plan.route) if plan else [origin],
                          years=years,remaining=years,phase='outbound' if years else 'stationed')
        reserved.update(selected)
        reserved_members.update(members)
        plans.append((index,a,d,people,journeys,cargo,target))
    if len(plans)!=2:
        return
    deps.prepare_formations(game)
    for index,a,d,people,journeys,cargo,target in plans:
        child = deps.start_campaign(game, 'sect', a.id, d.id, initiated_by_player=True, prepare_supplies=False)
        objective = dict(id=f"{row['id']}-objective-{index}", name=f'牵制{d.name}', location_id=target,
                         status='active', campaign_id=child['id'], result=0)
        child.update(strategic_war_id=row['id'], objective_id=objective['id'], scheduler='calendar',
                     location_id=target, journeys=journeys, campaign_phase='marching',
                     deployment_age=game.player.age,
                     cargo_journeys=cargo,
                     next_battle_age=game.player.age + max([j['years'] for js in journeys.values() for j in js]+[c['years'] for c in cargo.values()]) + 10,
                     budget_caps={s: sides[s][index]['budget'] for s in SIDES}, controller='ai',
                      org_budget_caps={org.id: sides[s][index]['budget'] for s,org in [('attacker',a),('defender',d)]},
                     roster={s: [n.id for n in people[s]] for s in SIDES}, player_side=None)
        child['roster_owner'] = {n.id: org.id for s, org in [('attacker', a), ('defender', d)] for n in people[s]}
        row['objectives'].append(objective)
        row['campaigns'].append(child['id'])
        game.sect_relations.setdefault(race_pair(a.id,d.id),{}).update(
            status='war',affinity=-75.,since_age=game.player.age,strategic_war_id=row['id'])
        # Procurement remains at real original supply addresses. No transport
        # or battle is performed by this parent layer.
        initialize(game, deps.maps, child)
        child['logistics_initialized']=True
    if row['campaigns']:
        row['status'] = 'active'
        row['deadline_age'] = max(w['next_battle_age'] for w in game.wars if w.get('strategic_war_id') == row['id']) + 120
        note(game, row, '联军开拔', f"已建立 {len(row['campaigns'])} 场组织战役，沿原地图道路行军。")


def _journey(deps, game, child):
    ready = True
    for journeys in child.get('journeys', {}).values():
        for j in journeys:
            tick=int(game.player.age>j.get('last_age',j.get('departed_age',child['deployment_age'])))
            j['last_age']=game.player.age
            n = deps.find_person(game, j['person_id'])
            from ...spatial_people import instance_of
            if not n or not is_free(n) or n.world != child['world'] or deps.imprisoned(game,j['person_id']) or instance_of(game,j['person_id']):
                j['phase'] = 'lost'
                continue
            if j['phase']=='stationed' and n.location_id is None:
                n.location_id=j['destination']
            if j['phase'] in {'outbound', 'returning'}:
                j['remaining'] = max(0, j['remaining'] - tick)
                if not j['remaining']:
                    n.location_id = j['destination']
                    j['phase'] = 'home' if j['phase']=='returning' else 'stationed'
                elif child['campaign_phase']=='returning' or (not j.get('reinforcement') and j['phase']=='outbound'):
                    ready = False
    for cargo in child.get('cargo_journeys',{}).values():
        if cargo['phase'] in {'outbound','returning'}:
            cargo['remaining']=max(0,cargo['remaining']-int(game.player.age>cargo.get('last_age',child['deployment_age'])))
            cargo['last_age']=game.player.age
            if not cargo['remaining']:
                cargo['phase']='home' if cargo['phase']=='returning' else 'stationed'
            elif child['campaign_phase']=='returning' or cargo['phase']=='outbound':
                ready=False
    from .dispatch import advance_cargo
    advance_cargo(game, child)
    if child['campaign_phase']=='returning' and any(r['cargo']['phase']!='home' for r in child.get('reinforcements', [])):
        ready=False
    return ready


def withdraw(game, child):
    if child.get('campaign_phase') == 'returning':
        return
    for side in SIDES:
        carriers=[(child[f'{side}_id'],child['cargo_journeys'][side])]+[
            (r['org']['id'],r['cargo']) for r in child.get('reinforcements',[]) if r['side']==side and r['delivered']]
        carrier=next((cargo for identity,cargo in carriers if identity not in child.get('withdrawn_orgs',[])
                      and cargo['phase'] in {'stationed','outbound'}),None)
        if carrier:
            child['logistics']['sides'][side]['return_location']=carrier['origin']
    child.update(status='withdrawing', campaign_phase='returning')
    for journeys in child.get('journeys', {}).values():
        for j in journeys:
            if j['phase'] in {'home', 'lost', 'returning'}:
                continue
            elapsed = j['years'] - j['remaining'] if j['phase'] == 'outbound' else j['years']
            j.update(destination=j['origin'], remaining=elapsed, phase='returning')
    for cargo in list(child.get('cargo_journeys',{}).values())+[r['cargo'] for r in child.get('reinforcements',[])]:
        if cargo['phase'] not in {'home','lost','returning'}:
            elapsed=cargo['years']-cargo['remaining'] if cargo['phase']=='outbound' else cargo['years']
            cargo.update(destination=cargo['origin'],remaining=elapsed,phase='returning')


def receipt(game, row, child):
    # Monotonic cumulative receipts: duplicate reads/callbacks cannot farm score.
    revision = int(child.get('battles', 0))
    previous = row['receipts'].get(child['id'], {})
    terminal = child.get('status') in {'peace_ready', 'ended', 'withdrawing'}
    if revision <= previous.get('revision', -1) and (not terminal or previous.get('terminal')):
        return
    row['receipts'][child['id']] = dict(revision=revision, terminal=terminal)
    objective = next(o for o in row['objectives'] if o['campaign_id'] == child['id'])
    if terminal and objective['status'] != 'completed':
        objective.update(status='completed', result={'attacker': 1, 'defender': -1}.get(child.get('winner'), 0))
        note(game, row, '战役结算', f"{objective['name']}结束，共 {revision} 次交锋；伤亡与军需已由原战役结算。")
        withdraw(game, child)
    row['score'] = round(sum(o['result'] for o in row['objectives']) * 50)


def armistice(game, row, reason):
    if row['status'] in {'armistice', 'settling', 'ended'}:
        return
    row['status'] = 'armistice'
    row['outcome'] = 'attacker' if row['score'] > 0 else 'defender' if row['score'] < 0 else 'draw'
    for child in game.wars:
        if child.get('strategic_war_id') == row['id'] and child.get('status') != 'ended':
            withdraw(game, child)
    for objective in row['objectives']:
        if objective['status']=='active':
            objective['status']='cancelled'
    relation = relations_for(game, row['world']).setdefault(race_pair(row['attacker'], row['defender']), {})
    relation.update(status='truce', affinity=-10, since_age=game.player.age, truce_until_age=game.player.age + 50)
    note(game, row, '总停战', reason)


def advance(deps, game, rng):
    state = game.strategic_war_state
    if not state:
        return
    for row in state.get('wars', []):
        if row['status'] not in OPEN or row['last_age'] >= game.player.age:
            continue
        row['last_age'] = game.player.age
        row['revision'] += 1
        _elect(deps, game, row)
        if row['status'] in {'mobilizing','active'} and {row['attacker'],row['defender']} <= set(local_races(row['world'])):
            from .materialization import materialize
            if row['status']=='mobilizing':
                from ..war.logistics import cash
                for race in (row['attacker'],row['defender']):
                    candidates=[o for o in organizations(game,row['world']) if o.allegiance_race==race and army(deps,game,o)
                                and (not owns(deps,game,o) or any(c['org']==ref(o) for c in row['commitments']))]
                    needed=max(0,2-len(candidates)) + int(not any(cash(game,o)>0 for o in candidates[2:]))
                    for _ in range(needed):
                        materialize(deps, game, row['world'], race, rng)
            for org in organizations(game, row['world']):
                if org.allegiance_race not in {row['attacker'], row['defender']} or owns(deps, game, org):
                    continue
                if any(c['org'] == ref(org) for c in row['commitments']):
                    continue
                try:
                    commit(deps, game, row, org)
                except ValueError:
                    pass
            if row['status']=='mobilizing':
                _launch(deps, game, row)
            _elect(deps, game, row)
            from .dispatch import auto_dispatch
            auto_dispatch(deps, game, row)
        for child in [w for w in game.wars if w.get('strategic_war_id') == row['id'] and w.get('status') != 'ended']:
            ready = _journey(deps, game, child)
            if child['campaign_phase'] == 'returning':
                if ready:
                    from ..war.logistics import refund
                    refund(game, child)
                    child.update(status='ended', end_age=game.player.age, campaign_phase='home')
                    for a in child['coalitions']['attacker']:
                        for d in child['coalitions']['defender']:
                            relation=game.sect_relations.get(race_pair(a['id'],d['id']),{})
                            if relation.get('strategic_war_id')==row['id']:
                                relation.update(status='truce',affinity=-10.,since_age=game.player.age,truce_until_unit=game.diplomacy_unit+5)
                                relation.pop('strategic_war_id',None)
                continue
            if ready:
                child['campaign_phase'] = 'engaged'
                for supply_side in child.get('logistics',{}).get('sides',{}).values():
                    supply_side['location'] = child['location_id']
                from ..economy.state import ensure_regional_market
                ensure_regional_market(game, deps.maps, child['world'], child['location_id'])
            if row['status'] == 'active' and ready and game.player.age >= child['next_battle_age']:
                # Missing optional race content blocks new attacks but never returns.
                if {row['attacker'], row['defender']} <= set(local_races(row['world'])):
                    deps.advance_campaigns(game, rng, [child])
                    child['next_battle_age'] = game.player.age + 10
                    receipt(game, row, child)
        if row['status'] == 'active' and row['objectives'] and all(o['status'] == 'completed' for o in row['objectives']):
            armistice(game, row, '既定战役均已完成，双方确认本案战果并撤回原部众。')
        if ((row['status'] == 'mobilizing' and game.player.age-row['start_age'] >= 30)
                or (row['status'] == 'active' and game.player.age >= row['deadline_age'])):
            armistice(game, row, '动员或战事旷日持久，双方接受无新增赔付的安全停战。')
        if row['status'] in {'armistice', 'settling'}:
            row['status'] = 'settling'
            if all(w.get('status') == 'ended' for w in game.wars if w.get('strategic_war_id') == row['id']):
                row.update(status='ended', end_age=game.player.age)
                note(game, row, '撤军完成', '原部众归返；未消耗军需依原贡献账退回，无重复奖励。')
                game.history.append(HistoryRecord('SYS_STRATEGIC_END',1,game.player.age,'战争收束',row['id'],'ended',
                    f"战争战果 {row['score']}，全部战役已撤回并结清。",{'strategic_war_id':row['id'],'campaigns':list(row['campaigns'])},
                    ['system','war','world_news',f"world:{row['world']}"]))
    compact(game)
