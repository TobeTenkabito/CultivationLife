"""Exercise new finance, original organizational guard authority and trust in EXE."""
import json
import urllib.request
from cultivation_life.models import SectState, SectNpc


def verify_economy_trust(base, folder):
    def request(path, payload=None):
        req=urllib.request.Request(base+'/api/'+path,data=json.dumps(payload).encode() if payload is not None else None,
                                  headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=90) as response:return json.load(response)
    game=request('games',dict(name='托管成品验收',preset_id='core',seed=419));identity=game['id']
    path=folder/'data/saves'/f'{identity}.json'
    raw=json.loads(path.read_bytes());raw['pending_event']=None
    raw['player'].update(realm_index=2,next_tribulation_age=None,lifespan=10000)
    raw['settings']['silent_events']=True
    raw['player']['inventory'].append(dict(id='spirit_stone',name='灵石',quantity=1000000))
    raw['family']=SectState('release_family','验收沈氏','human',
        [SectNpc('release_heir','沈宁','族人',4,1,100,1000,world='human')],kind='family',
        founded_by_player=True,founder_player_id=identity,location_id=raw['player']['location_id']).to_dict()
    path.write_text(json.dumps(raw,ensure_ascii=False),encoding='utf-8')
    game=request(f'games/{identity}')
    def action(name,**payload):return request(f'games/{identity}/fleet-action',dict(action=name,**payload))
    action('organization_fund',owner_kind='family',amount=20000)
    game=action('create',owner_kind='family')
    fleet=next(f for f in game['fleet_network']['fleets'] if f['owner_id']=='release_family')
    raw=json.loads(path.read_bytes());f=raw['economy_v2']['transport']['worlds']['human']['fleets'][fleet['id']]
    f.update(player_controlled=False,trade_order={'mode':'hold'})
    path.write_text(json.dumps(raw,ensure_ascii=False),encoding='utf-8')
    game=action('guard',fleet_id=fleet['id'])
    assert next(f for f in game['fleet_network']['fleets'] if f['id']==fleet['id'])['guard_power']>0
    offer=next(o for o in game['map']['economy']['enterprises']['offers'] if o['kind']=='mine')
    game=action('estate_buy',kind='mine',cost=offer['cost'])
    row=next(r for r in game['map']['economy']['enterprises']['owned'] if r['kind']=='mine');key=row['id']
    game=action('estate_fund',estate_id=key,revision=row['revision'],amount=10000)
    game=request(f'games/{identity}/settings',dict(setting='economy_trust',enabled=True))
    assert game['settings']['economy_trust']
    game=request(f'games/{identity}/advance',dict(action='rest',years=1))
    row=next(r for r in game['map']['economy']['enterprises']['owned'] if r['id']==key)
    assert row['trust_managed']
    fiscal=game['family']['finance']
    assert fiscal['annual_income']==fiscal['income']/fiscal['settlement_years']
    assert fiscal['annual_expense']==fiscal['expense']/fiscal['settlement_years']
    job=row['job']
    game=request(f'games/{identity}/settings',dict(setting='economy_trust',enabled=False))
    row=next(r for r in game['map']['economy']['enterprises']['owned'] if r['id']==key)
    assert not row['trust_managed'] and not row['enabled'] and row['job']==job
    before=path.read_bytes();request(f'games/{identity}');assert path.read_bytes()==before
    print('Packaged economy trust: annual income, original organization guard, setting persistence and plan restoration passed',flush=True)
