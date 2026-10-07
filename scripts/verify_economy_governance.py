"""Packaged HTTP governance checks against a disposable save."""
import json
import urllib.request


def verify_economy_governance(base, folder):
    def request(path, payload=None):
        req=urllib.request.Request(base+'/api/'+path,data=json.dumps(payload).encode() if payload is not None else None,
                                  headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=60) as response:return json.load(response)
    result=request('games',dict(name='市政成品验收',preset_id='core',seed=419));identity=result['id']
    path=folder/'data/saves'/f'{identity}.json'
    data=json.loads(path.read_bytes());data['pending_event']=None
    data['player'].update(realm_index=4,next_tribulation_age=None)
    data['player']['inventory'].append(dict(id='spirit_stone',name='灵石',quantity=10**7))
    path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    result=request(f'games/{identity}');market=result['map']['economy']
    old=market['operator_balance']
    result=request(f'games/{identity}/fleet-action',dict(action='market_relief',market_id=market['market_id'],revision=market['revision'],amount=10000))
    assert result['map']['economy']['operator_balance']==old+10000
    market=result['map']['economy'];row=market['rows'][0]
    result=request(f'games/{identity}/local-market-trade',dict(market_id=market['market_id'],revision=market['revision'],item_id=row['id'],side='buy',quantity=1,total=row['quotes']['1']['buy']['total']))
    assert any(r['item']==row['id'] for r in result['map']['economy']['competition']['rows'])
    saved=path.read_bytes();result=request(f'games/{identity}')
    assert path.read_bytes()==saved and result['map']['economy']['competition']['rows']
    print('Packaged governance: paid local relief, actual commodity observations and read-only reload passed',flush=True)
