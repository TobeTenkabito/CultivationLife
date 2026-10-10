"""Isolated initial conditions shared by browser and signed native acceptance."""
import random
from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.rules import learn_technique
from cultivation_life.system.economy import depot, organizations
from cultivation_life.system.economy.ledger import transfer_value
from cultivation_life.system.economy.state import ensure_regional_market
from cultivation_life.system.organization_heritage import ensure
from cultivation_life.system.teleport_construction import requirements
from cultivation_life.system.family_membership import resolve_line


def prepare(engine, identity):
    g=engine._load(identity);g.pending_event=None;g.active_trial=None
    s=g.sects[g.player.faction_id]
    site=next(l['id'] for l in engine.maps.worlds['human']['locations'] if not l.get('teleport_array') and not l.get('min_realm_index'))
    s.location_id=site;g.player.location_id=site
    organizations.register(g,'sect',s.id,'human')
    transfer_value(g,'background:human',depot.treasury(g,s),2000000,'隔离验收初始府库')
    transfer_value(g,'background:human','player',20000,'隔离验收初始私款')
    g.player.faction_contribution=10
    g.player.known_techniques[:]=[t for t in g.player.known_techniques if t.id!='TECH_HUMAN_HERITAGE_1']
    learn_technique(g.player,TECHNIQUE_CATALOG['TECH_HUMAN_HERITAGE_2'])
    ensure(s)['books']=['TECH_HUMAN_HERITAGE_1']
    ensure_regional_market(g,engine.maps,'human',site)
    market=g.economy_v2['markets']['human:'+site]
    for item,qty in requirements('human').items():market['commodities'][item]['stock']=qty+10
    k=next(k for k,v in depot.catalog('human').items() if v['kind']=='item' and v['tier']==1)
    market['commodities'][depot.catalog('human')[k]['id']]['stock']=10
    depot.purchase(g,engine.maps,s,k,3)
    engine.store.save(g)


def activities(engine,identity,state):
    g=engine._load(identity);rng=random.Random(290)
    if state=='scheduled':engine._schedule_auction(g,rng);engine._schedule_exchange(g,rng)
    elif state=='open':engine._open_auction(g,rng);engine._open_exchange(g,rng)
    elif state=='closed':
        engine._advance_auction_clock(g,rng);engine._advance_auction_clock(g,rng)
        engine._advance_exchange_clock(g,rng);engine._advance_exchange_clock(g,rng)
    engine.store.save(g)


def clan(engine,identity):
    g=engine._load(identity)
    s=next(s for s in g.sects.values() if s.kind=='family' and s.world=='human')
    organizations.register(g,'sect',s.id,s.world)
    transfer_value(g,'background:human',depot.treasury(g,s),100000,'隔离验收家族供养储备')
    g.player.location_id=s.location_id
    engine.store.save(g)


def succeed(engine,identity):
    g=engine._load(identity)
    for n in g.family.npcs:n.alive=False
    resolve_line(g,g.family)
    engine.store.save(g)
