"""Packaged HTTP acceptance for actual deeds, production and manual dispatch."""
import json
import urllib.request


def verify_economy_enterprises(base, folder):
    def request(path, payload=None):
        req=urllib.request.Request(base+'/api/'+path,data=json.dumps(payload).encode() if payload is not None else None,
                                   headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=60) as response:return json.load(response)
    result=request('games',dict(name='产业打包验收',preset_id='core',seed=419));identity=result['id']
    path=folder/'data/saves'/f'{identity}.json'
    data=json.loads(path.read_bytes());data['pending_event']=None
    data['player'].update(realm_index=2,next_tribulation_age=None)
    data['player']['inventory'].append(dict(id='spirit_stone',name='灵石',quantity=10**8))
    path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    result=request(f'games/{identity}')
    def action(name,**payload):return request(f'games/{identity}/fleet-action',dict(action=name,**payload))
    offer=next(o for o in result['map']['economy']['enterprises']['offers'] if o['kind']=='mine')
    result=action('estate_buy',kind='mine',cost=offer['cost'])
    row=result['map']['economy']['enterprises']['owned'][0];key=row['id']
    result=action('estate_fund',estate_id=key,revision=row['revision'],amount=10000)
    row=result['map']['economy']['enterprises']['owned'][0]
    result=action('estate_start',estate_id=key,revision=row['revision'])
    assert result['map']['economy']['enterprises']['owned'][0]['job']['quantity']==4
    result=request(f'games/{identity}/advance',dict(action='rest',years=2))
    assert result['map']['economy']['enterprises']['owned'][0]['produced']==4
    data=json.loads(path.read_bytes());data['pending_event']=None
    path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    result=action('create');fleet=next(f for f in result['fleet_network']['fleets'] if f['player_controlled'])
    dest=next(s['id'] for s in result['fleet_network']['order_sites'] if s['id']!=fleet['location_id'])
    result=action('order_configure',fleet_id=fleet['id'],mode='repeat',kind='local',destination=dest,
        item='dew_grass_seed',quantity=1,buy_limit=10000,sell_limit=0)
    result=action('order_dispatch',fleet_id=fleet['id'])
    assert next(f for f in result['fleet_network']['fleets'] if f['id']==fleet['id'])['status']=='travelling'
    result=request(f'games/{identity}')
    assert next(f for f in result['fleet_network']['fleets'] if f['id']==fleet['id'])['trade_order']['mode']=='repeat'
    print('Packaged enterprises: actual title, funding, production year and standing dispatch passed',flush=True)
