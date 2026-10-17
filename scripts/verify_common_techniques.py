"""Check common arts through the built host in disposable release saves."""
import json
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def verify_common_techniques(base, folder):
    def post(identity, operation, **payload):
        endpoint=f'/api/games/{identity}/{operation}' if identity else '/api/games'
        request=Request(base+endpoint,data=json.dumps(payload).encode(),
                        headers={'Content-Type':'application/json'},method='POST')
        with urlopen(request,timeout=40) as response:return json.load(response)
    def get(identity):
        with urlopen(base+f'/api/games/{identity}',timeout=40) as response:return json.load(response)
    made=post(None,None,name='功法成品验收',spirit_root='supreme_metal',path='dao',seed=2144,preset_id='core')
    identity=made['id'];path=folder/'data/saves'/f'{identity}.json'
    catalog=json.loads((Path(__file__).resolve().parents[1]/'content/techniques.json').read_text(encoding='utf-8'))['techniques']
    book=next(t for t in catalog if t['id']=='TECH_OPEN_SONGCHUANG_METAL_WATER_MAIN')
    raw=json.loads(path.read_bytes());raw['pending_event']=None;p=raw['player']
    p.update(realm_index=4,layer=1,additional_roots=[],technique=None,support_technique=None,
             combat_techniques=[],known_techniques=[book])
    p['inventory'].extend([dict(id='jinque_water',name='金阙残书',quantity=1),
        dict(id=f"technique_manual::{book['id']}::lv1",name='传承玉简',quantity=1,
             technique_id=book['id'],technique_level=1,technique_origin_realm_index=1)])
    path.write_text(json.dumps(raw,ensure_ascii=False),encoding='utf-8')
    shown=get(identity)
    assert not next(t for t in shown['player']['known_techniques'] if t['id']==book['id'])['compatible']
    try:post(identity,'equip-technique',technique_id=book['id'],slot='main')
    except HTTPError as error:assert error.code==400
    else:raise AssertionError('Built host accepted an art missing its second root')
    post(identity,'use-item',item_id='jinque_water')
    post(identity,'equip-technique',technique_id=book['id'],slot='main')
    shown=post(identity,'technique-upgrade',technique_id=book['id'])
    assert shown['player']['technique']['level']==2
    assert shown['player']['technique']['required_affinities']==['metal','water']
    raw=json.loads(path.read_bytes());raw['player']['additional_roots']=[]
    path.write_text(json.dumps(raw,ensure_ascii=False),encoding='utf-8')
    assert not get(identity)['player']['technique_slots']['main']['root_requirement_met']
    print('Common technique EXE scope passed: actual root, equip, upgrade and root-loss guards')
