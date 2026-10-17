"""Use actual common-goods endpoints in a disposable built Windows host."""
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def verify_common_goods(base, folder):
    def post(identity, endpoint, **payload):
        url = '/api/games' if identity is None else f'/api/games/{identity}/{endpoint}'
        with urlopen(Request(base+url,data=json.dumps(payload).encode(),
            headers={'Content-Type':'application/json'},method='POST'),timeout=60) as response:
            return json.load(response)
    made = post(None,'',name='商品成品验收',spirit_root='supreme_metal',path='dao',seed=2151,preset_id='nascent')
    assert made['player']['combat_power'] >= 43690
    identity = made['id']
    path = folder/'data/saves'/f'{identity}.json'
    raw = json.loads(path.read_bytes())
    p = raw['player']
    raw['pending_event'] = None
    raw['settings'].update(silent_events=True,guixu_event_popup=False)
    p['inventory'].extend([dict(id='econ_human_4_talisman_protection',name='通用护身符',quantity=1),
        dict(id='econ_human_4_core_energy',name='元能内丹',quantity=1),dict(id='spirit_stone',name='灵石',quantity=100000)])
    p['opportunity'] = 0
    raw['auction_state'] = dict(id='common-goods-host',status='open',world=p['world'],location_id=p['location_id'],
        location_name='成品会场',auction_class=3,class_name='高级',rank_band=[5],entry_fee=500,entry_paid=False,
        round=0,lots=[],consignments=[],attendees=[],black_market_results=[])
    path.write_text(json.dumps(raw,ensure_ascii=False),encoding='utf-8')
    with urlopen(base+'/api/config',timeout=60) as response:
        configured = json.load(response)['common_goods']['core_effects']['opportunity'][3]
    fixed = post(identity,'use-item',item_id='econ_human_4_core_energy')
    assert fixed['player']['opportunity'] == configured
    entered = post(identity,'auction-identity',alias='青龙公子')
    funds = entered['auction_system']['spirit_stones']
    assert entered['auction_system']['entry_paid'] and entered['auction_system']['entry_due'] == 0
    assert post(identity,'auction-identity',alias='朱雀公主')['auction_system']['spirit_stones'] == funds
    received = post(identity,'use-item',item_id='econ_human_4_talisman_protection')
    row = next(r for r in received['talismans']['rows'] if r['method_id'] == 'econ_human_4_talisman_protection')
    assert row['uses'] == 3 and row['protection'] == 16 and not row['enabled']
    enabled = post(identity,'talisman-action',action='toggle',talisman_id=row['id'])
    assert next(r for r in enabled['talismans']['rows'] if r['id'] == row['id'])['enabled']
    try: post(identity,'use-item',item_id='econ_human_4_talisman_protection')
    except HTTPError as error: assert error.code == 400
    else: raise AssertionError('Built EXE unpacked an absent second unit')
    post(identity,'auction-advance')
    post(identity,'auction-advance')
    post(identity,'auction-advance')
    found = post(identity,'black-market-search',pattern='^水属')
    row = next(r for r in found['auction_system']['black_market_results'] if r['content_id'] == 'secret_core_water_4')
    bought = post(identity,'black-market-buy',result_id=row['id'])
    assert any(i['id'] == row['content_id'] for i in bought['player']['inventory'])
    print('Common goods EXE scope passed: fixed entry once, real finite talisman, duplicate rejection and restricted black-market purchase')
