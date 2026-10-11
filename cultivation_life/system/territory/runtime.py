"""Endpoint geographic settlement; no yearly territorial simulation."""
from ...npc_custody import is_free
from ..economy.ledger import balance, transfer_value
from ..economy.organization_accounts import key, procure
from .rules import enabled, POLICIES, permits, DECAY_PER_YEAR
from .state import ensure, snapshot, state, refresh_bonuses

def activate(game,maps):
    """Adopt at the real clock; disabled years never become catch-up charges.

    The base geography flag detects re-enabling without writing frozen DLC data.
    The cheap membership check can be used by the existing yearly finance entry.
    """
    sites=game.economy_v2.setdefault('organization_sites',{})
    active=enabled();previous=sites.get('territory_enabled')
    sites['territory_enabled']=active
    if not active:return previous is not False
    organizations=game.economy_v2.get('organizations',{})
    addresses=[address for address,row in organizations.items()
               if row['kind']=='sect' and (entity:=game.sects.get(row['identity']))
               and not entity.extinct and entity.kind=='sect']
    clocks=game.intrigue_state.get('territory',{}).get('settlement_years',{})
    missing=[address for address in addresses if address not in clocks]
    if previous is True and not missing:return False
    prepare(game,maps)
    clocks=state(game).setdefault('settlement_years',{})
    for address in addresses if previous is not True else missing:
        clocks[address]=game.player.age
    if previous is not True:
        state(game)['fee_cursors']={m['id']:m.get('fees',0) for m in game.economy_v2.get('markets',{}).values()}
        state(game)['ai_decade']=game.player.age//10
    refresh_bonuses(game)
    return True

def settle_unit(host,game,rng):
    """One real endpoint for one action batch, including partial interrupted units.

    Several requested units are deliberately coalesced. Current workforce,
    balances and influence determine the period; no historical duels/production
    or hypothetical annual treasury paths are reconstructed.
    """
    if not enabled():return
    activate(game,host.maps)
    s=state(game);clocks=s['settlement_years']
    pending=[(address,row,game.player.age-clocks[address])
             for address,row in game.economy_v2.get('organizations',{}).items()
             if address in clocks and game.player.age>clocks[address]]
    if not pending:return
    prepare(game,host.maps)
    for address,row,years in pending:
        entity=game.sects.get(row['identity'])
        clocks[address]=game.player.age
        if not entity or entity.extinct or entity.kind!='sect':continue
        row['territory_income']=0
        row['territory_years']=years
        settle(game,host.maps,entity,row,years)
        if row.get('history') and row['history'][-1][0]==game.player.age:
            row['history'][-1][2]+=row.get('territory_paid',0)
    dividends(game)
    refresh_bonuses(game)
    npc_proposal(host,game,rng)

def prepare(game,maps):
    if not enabled(): return
    s=state(game)
    for world in {r['world'] for r in game.economy_v2.get('organizations',{}).values() if r['kind']=='sect'}:
        book=ensure(game,maps,world)
        visible=snapshot(game,maps,world)
        for loc,rows in book.items():
            for identity,r in rows.items():
                projected=visible.get(loc,{}).get(identity,{})
                r['floor']=projected.get('floor',0);r['array']=projected.get('array',False)
    s.setdefault('ai_decade',game.player.age//10)
    # Adopt each fee cursor at its current total. Past trading creates no bonus.
    cursors=s.setdefault('fee_cursors',{})
    for market in game.economy_v2.get('markets',{}).values(): cursors.setdefault(market['id'],market.get('fees',0))

def settle(game,maps,entity,row,years):
    if not enabled() or row['kind']!='sect' or entity.kind!='sect' or entity.extinct or years<=0: return
    book=state(game)['holdings'].get(entity.world,{})
    own=[(loc,rows[entity.id]) for loc,rows in book.items() if entity.id in rows and loc!=entity.location_id]
    if not own: row['territory_due']=row['territory_paid']=0;return
    annual=max(10,row.get('expected_upkeep',0)*.06)
    reserve=row.get('expected_upkeep',0)*.65*3
    spare=max(0,balance(game,key('sect',entity.id))-reserve)
    modifier=row.get('territory_elder_factor',1.)
    due=0.; factors=[]
    for loc,r in own:
        policy=POLICIES.get(r.get('policy')) if permits(r.get('policy'),r['value']) else None
        if not policy: r['policy']=''
        amount=annual*(r['value']/100+.3 if r.get('outpost') else r['value']/100)*(policy['upkeep'] if policy else 1)*years
        due+=amount;factors.append((loc,r,policy,amount))
    due=int(due+.999);paid=min(due,int(spare))
    procure(game,key('sect',entity.id),entity.world,paid,'地方巡守与据点养护',partial=True)
    row['expense']+=paid;row['territory_due']=due;row['territory_paid']=paid
    coverage=paid/max(1,due)
    for loc,r,policy,amount in factors:
        # Poor factions dismantle discretionary outposts; constructed arrays
        # retain their floor until an explicit territorial peace removes them.
        if coverage<.5 and r.get('outpost'): r['outpost']=False;r['floor']=40 if r.get('array') else 0
        floor=r.get('floor',0)
        decay=DECAY_PER_YEAR*years*modifier*(policy['decay'] if policy else 1)*(1+3*(1-coverage))
        r['value']=max(floor,r['value']-decay)
        if r['value']<=0: book[loc].pop(entity.id,None)

def dividends(game):
    if not enabled(): return
    s=state(game);cursors=s.setdefault('fee_cursors',{})
    for market in game.economy_v2.get('markets',{}).values():
        actual=market.get('fees',0);previous=cursors.get(market['id'],actual)
        cursors[market['id']]=actual
        rows=s['holdings'].get(market['world'],{}).get(market['location'],{})
        weights={identity:r['value']*(POLICIES[r['policy']]['yield_factor'] if permits(r.get('policy'),r['value']) else 1)
                 for identity,r in rows.items() if key('sect',identity) in game.economy_v2.get('organizations',{})}
        total=sum(weights.values())
        if not total: continue
        pool=min(int(max(0,actual-previous)*.2),balance(game,f'operator:{market["id"]}'))
        for identity,weight in weights.items():
            paid=int(pool*weight/total)
            transfer_value(game,f'operator:{market["id"]}',key('sect',identity),paid,'当地采办与商路经营收益按相对影响力分配')
            row=game.economy_v2['organizations'][key('sect',identity)]
            row['income']+=paid;row['territory_income']=row.get('territory_income',0)+paid
            if row.get('history') and row['history'][-1][0]==game.player.age:
                row['history'][-1][1]+=paid

def npc_proposal(host,game,rng):
    if not enabled(): return
    s=state(game)
    if game.player.age//10<=s.get('ai_decade',game.player.age//10):return
    s['ai_decade']=game.player.age//10
    # At most one proposal per endpoint, with the original ten-year lower
    # spacing. A century never replays the intervening decades.
    candidates=[e for e in game.sects.values() if not e.extinct and e.kind=='sect' and not e.founded_by_player and e.id!=game.player.faction_id and key('sect',e.id) in game.economy_v2.get('organizations',{})]
    if not candidates:return
    entity=candidates[s['ai_cursor']%len(candidates)];s['ai_cursor']+=1
    row=game.economy_v2['organizations'][key('sect',entity.id)]
    from .actions import validate, construction_plan
    if row.get('shortfall') or row.get('territory_paid',0)<row.get('territory_due',0) or balance(game,key('sect',entity.id))<row.get('expected_upkeep',0)*6:return
    book=ensure(game,host.maps,entity.world)
    proposals=[]
    for loc,rows in book.items():
        if entity.id not in rows:continue
        owned=rows[entity.id]
        policy=next((p for p in POLICIES if permits(p,owned['value'])),None)
        if policy and owned.get('policy')!=policy:
            proposals.append(('territory_policy',loc,dict(policy=policy)))
        if loc!=entity.location_id and not owned.get('outpost') and construction_plan(game,host.maps,entity,loc)['can_build']:
            proposals.append(('build_outpost',loc,{}))
        for rival in rows:
            if rival==entity.id:continue
            # Sparse proposals, never all NPC pairs or repeated individual duels.
            for action in ('territory_spar','territory_harass'):
                try:validate(game,host.maps,entity,action,loc,target=rival)
                except ValueError:continue
                proposals.append((action,loc,dict(rival_id=rival)))
        for neighbor,_ in host.maps._graphs[entity.world][loc]:
            if entity.id in book.get(neighbor,{}):continue
            try:validate(game,host.maps,entity,'expand_influence',neighbor)
            except ValueError:continue
            proposals.append(('expand_influence',neighbor,{}))
    if not proposals:return
    record=host._ensure_intrigue_faction(game,'sect',entity.id)
    leader=record.get('controller_id')
    action,location,context=rng.choice(proposals)
    try:host._intrigue_resolve(game,'sect',entity.id,action,location,None,leader,rng,context=context)
    except ValueError:return
