"""Exercise v2.13.6 fixes through the actual packaged server, not source actions."""
import importlib.util
import json
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from cultivation_life.storage import SaveStore

ROOT=Path(__file__).resolve().parents[1]


def verify_followup(base,folder,with_dlc):
    spec=importlib.util.spec_from_file_location('followup_fixture',ROOT/'tests/fixtures/followup_fixes_release.py')
    fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
    class FixtureEngine:
        store=SaveStore(folder/'data/saves')
        def _load(self,identity):return self.store.load(identity)
    isolated=FixtureEngine()
    def request(path,payload=None,status=200):
        req=Request(base+'/api/'+path,method='GET' if payload is None else 'POST',
            data=None if payload is None else json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        try:
            with urlopen(req,timeout=120) as response:code,body=response.status,json.load(response)
        except HTTPError as error:code,body=error.code,json.load(error)
        assert code==status,(path,code,body.get('error'))
        return body
    def create(world='human',path='dao',rank=4):
        return request('games',dict(name='成品后续修复验收',spirit_root='mutated_yin' if path=='ghost' else 'supreme_metal',
            path=path,seed=888,monster_species_id='serpent' if path=='monster' else None,
            custom_start=dict(world=world,realm_index=rank,layer=1)),201)['id']
    identity=create();fixture.prepare_followup(isolated,identity,'guard')
    def act(operation,**payload):return request(f'games/{identity}/{operation}',payload)
    shown=request('games/'+identity)
    slots=[r['id'] for r in shown['formation_system']['materials'] if r['source_kind']=='formation_material'][:3]
    act('formation-save',name='成品护山',slots=slots+[None]*6,activate=True)
    act('formation-ground-deploy',owner_kind='sect')
    shown=request('games/'+identity)
    destination=next(r for r in shown['map']['organization_relocation'] if r['kind']=='sect')['destinations'][0]['id']
    act('organization-action',kind='sect',owner_id='followup_org',action='relocate',location_id=destination)
    act('map-travel',destination=destination)
    fixture.prepare_guard_defense(isolated,identity)
    shown=request('games/'+identity)
    act('choice',event_id=shown['pending_event']['id'],choice_id='formation')
    fixture.inspect_followup(isolated,identity,'guard')
    if with_dlc:
        for case in ['production','supply']:
            identity=create();fixture.prepare_followup(isolated,identity,case)
            if case=='supply':
                act('intrigue-resolution',kind='sect',resolution_type='declare_war',target_id='tianjian')
            act('intrigue-resolution',kind='sect',resolution_type='imprison_member',target_id='followup_member',years=500)
            if case=='production':act('advance',action='rest',years=1)
            else:
                war=next(w for w in isolated._load(identity).wars if w['attacker_id']=='followup_org')
                act('war-action',war_id=war['id'],action='round')
            fixture.inspect_followup(isolated,identity,case)
    branches=[('celestial','dao'),('asura','dao'),('nether','dao'),('reincarnation','dao')]
    if with_dlc:branches += [('asura','demonic'),('nether','monster'),('reincarnation','ghost')]
    for world,path in branches:
        identity=create(world,path,9)
        book=fixture.prepare_followup(isolated,identity,'inheritance')
        act('aperture-action',action='inherit',manual_id=book)
        fixture.inspect_followup(isolated,identity,'inheritance')
        request(f'games/{identity}/aperture-action',dict(action='inherit',manual_id=book),400)
    custody=', prisoner production/supply' if with_dlc else ''
    print(f'EXE v2.13.6 passed: DLC={with_dlc}, fixed-site guard{custody} and {len(branches)} inheritance branches',flush=True)
