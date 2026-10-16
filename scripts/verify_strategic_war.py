"""Exercise the new campaign commands against the exact executable's HTTP server."""
import importlib.util
import json
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

ROOT=Path(__file__).resolve().parents[1]


def verify_strategic_war(base,folder,with_dlc):
    def request(path,payload=None,status=200):
        req=Request(base+'/api/'+path,method='GET' if payload is None else 'POST',
                    data=None if payload is None else json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        try:
            with urlopen(req,timeout=120) as response:code,body=response.status,json.load(response)
        except HTTPError as error:code,body=error.code,json.load(error)
        assert code==status,(path,code,body.get('error'))
        return body
    shown=request('games',dict(name='联军成品验收',spirit_root='supreme_metal',path='dao',seed=641,
                  custom_start=dict(world='spirit',realm_index=8,layer=1)),201)
    assert shown['war_system']['strategic']['available']
    if not with_dlc:
        print('Packaged base strategic war entry and assets available without optional DLC',flush=True)
        return
    from cultivation_life.engine import GameEngine
    spec=importlib.util.spec_from_file_location('strategic_release_fixture',ROOT/'tests/fixtures/strategic_war_release.py')
    fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
    engine=GameEngine(ROOT,folder/'data/saves')
    fixture.prepare_strategic_release(engine,shown['id'])
    shown=request('games/'+shown['id']);system=shown['war_system']['strategic'];row=system['wars'][0]
    child=next(c for c in row['campaigns'] if c['org'] and c['org']['id']=='taixuan' and c['dispatch_choices'])
    choice=child['dispatch_choices'][0]
    payload=dict(action='dispatch',war_id=row['id'],campaign_id=child['id'],org_id=choice['id'],org_kind=choice['kind'],
                 expected_cost=choice['cost'],expected_revision=row['revision'],command_id='exe-strategic-dispatch',command_seq=system['command_seq'])
    result=request('games/'+shown['id']+'/strategic-war',payload)
    fixture.inspect_strategic_release(engine,shown['id'])
    path=folder/'data/saves'/f"{shown['id']}.json";before=path.read_bytes()
    request('games/'+shown['id']+'/strategic-war',payload,400)
    assert path.read_bytes()==before
    system=result['war_system']['strategic'];row=system['wars'][0]
    result=request('games/'+shown['id']+'/strategic-war',dict(action='withdraw',war_id=row['id'],campaign_id=child['id'],
        org_id='taixuan',org_kind='sect',expected_revision=row['revision'],command_id='exe-local-recall',command_seq=system['command_seq']))
    raw=json.loads(path.read_bytes());campaign=next(w for w in raw['wars'] if w['id']==child['id'])
    assert campaign['status']=='active' and 'taixuan' in campaign['withdrawn_orgs']
    print('Packaged strategic war passed: actual idle dispatch, original escrow, replay rejection and local recall with allies continuing',flush=True)
