"""Run repaired flows through the built executable's actual HTTP server."""
import importlib.util
import json
from pathlib import Path
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from cultivation_life.storage import SaveStore

ROOT=Path(__file__).resolve().parents[1]

def verify_bugfix(base,folder):
    spec=importlib.util.spec_from_file_location('release_bugfix_fixture',ROOT/'tests/fixtures/audit_fixes_release.py')
    fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
    class FixtureEngine:
        store=SaveStore(folder/'data/saves')
        def _load(self,identity):return self.store.load(identity)
    isolated=FixtureEngine()
    def post(path,payload,status=200):
        request=Request(base+'/api/'+path,method='POST',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        try:
            with urlopen(request,timeout=120) as response:code,body=response.status,json.load(response)
        except HTTPError as error:code,body=error.code,json.load(error)
        if code==500:
            diagnostics=folder/'data/logs/server-errors.log'
            if diagnostics.is_file():print(diagnostics.read_text(encoding='utf-8')[-5000:],flush=True)
        assert code==status,(path,code,body.get('error','Unexpected status'))
        return body
    for case in ['return','training','work']:
        world,realm=('nether',9) if case=='work' else ('spirit',8)
        game=post('games',dict(name='成品修复验收',spirit_root='supreme_metal',path='dao',seed=8712,custom_start=dict(world=world,realm_index=realm,layer=1)),201)
        identity=game['id'];fixture.prepare_audit_fixes(isolated,identity,case)
        def act(operation,**payload):return post(f'games/{identity}/{operation}',payload)
        if case=='return':
            act('secret-art',art='suppress',action='activate',realm_index=1,layer=1)
            act('cross-world',destination='human')
            post(f'games/{identity}/secret-art',dict(art='suppress',action='cancel'),400)
            act('cross-world',destination='spirit')
            act('secret-art',art='suppress',action='cancel')
            fixture.inspect_audit_fixes(isolated,identity,case)
        elif case=='training':
            act('owned-training',target_id='release-trained',kind='prisoner',axis='cultivation',batches=1)
            act('captive-action',target_id='release-trained',action='release')
            fixture.inspect_audit_fixes(isolated,identity,case)
        else:
            before=isolated._load(identity).player.age
            result=act('upper-institution',action='work')
            assert result['player']['age']-before==60
            assert result['upper_institution']['job']['progress']==100
    print('EXE bugfix scope passed: original return/ties, infinite captive lifespan and remaining work',flush=True)
