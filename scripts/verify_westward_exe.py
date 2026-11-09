"""Commands served by the final EXE, with and without the optional expansion."""
import json, runpy, urllib.request, urllib.error
from pathlib import Path

def verify_westward(base, with_dlc, folder):
    from cultivation_life.engine import GameEngine
    root = Path(__file__).resolve().parents[1]
    def request(path, data=None):
        req = urllib.request.Request(base + path, data=json.dumps(data).encode() if data is not None else None,
                                     headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req, timeout=90) as r: return json.load(r)
    for asset in ('institution-governance.js','institution-governance.css','westward-development.js','assets/building-portraits/land-temple-intact-361.png','assets/building-portraits/land-temple-ruin-361.png','immortal-navigation.js','immortal-navigation.css','building-affairs.js','dlc-controls.js','dlc-controls.css','westward-ventures.js','westward-finale.js','westward-finale.css'):
        with urllib.request.urlopen(base+'/'+asset) as r: assert r.status == 200
    made = request('/api/games',dict(name='西望成品验收',spirit_root='supreme_metal',path='dao',seed=360,preset_id='true_immortal'))
    engine = GameEngine(root, folder/'data/saves')
    core=request('/api/games',dict(name='本体机构验收',spirit_root='supreme_metal',path='dao',seed=370,preset_id='core'))
    runpy.run_path(str(root/'tests/fixtures/westward_release.py'))['prepare_institution'](engine,core['id'])
    cp='/api/games/'+core['id'];cv=request(cp);scope=cv['fleet_network']['institutions'][0]
    offer=next(o for o in scope['offers'] if not o['reason'])
    cv=request(cp+'/fleet-action',dict(action='institution_start',scope=scope['id'],token=scope['token'],offer=offer['key'],person=scope['people'][0]['id']))
    scope=cv['fleet_network']['institutions'][0];assert scope['job']['funded']>0
    cv=request(cp+'/fleet-action',dict(action='institution_cancel',scope=scope['id'],token=scope['token']))
    assert cv['fleet_network']['institutions'][0]['history'][-1]['refunded']>0
    runpy.run_path(str(root/'tests/fixtures/westward_release.py'))['prepare_westward'](engine, made['id'])
    path = '/api/games/' + made['id']; view = request(path)
    if not with_dlc:
        assert not view['yaochi'].get('westward',{}).get('available')
        try: request(path+'/yaochi-action',dict(action='westward_adopt'))
        except urllib.error.HTTPError as error: assert error.code == 400
        else: raise AssertionError('Missing DLC command accepted')
        assert request(path)['yaochi']['merit'] == 2000
    else:
        assert view['yaochi']['westward']['available']
        def act(action, token=''): return request(path+'/yaochi-action',dict(action=action,target_id=token))
        view = act('westward_adopt'); assert view['yaochi']['westward']['merit'] == 50
        token = next(r for r in view['yaochi']['westward']['services'] if r['id']=='trace')['token']
        view = act('westward_start_court',token)
        project = view['yaochi']['westward']['project']; assert project and view['yaochi']['westward']['merit'] == 40
        assert request(path)['yaochi']['westward']['project']['id'] == project['id']
        view = act('westward_cancel',project['token'])
        assert view['yaochi']['westward']['project'] is None and view['yaochi']['westward']['merit'] == 50
        lesson=next(r for r in view['yaochi']['westward']['services'] if r['id']=='guidance')
        assert not lesson['merit_reason'] and lesson['teacher']=='westward-release-teacher'
        view=act('westward_start_merit',lesson['token']);view=act('westward_cancel',view['yaochi']['westward']['project']['token'])
        assert view['yaochi']['identity']['primary']=='free'
        view=act('garden_lease',view['yaochi']['garden']['token']+'|')
        recipe=view['yaochi']['garden']['recipes'][0]['id'];view=act('garden_configure',view['yaochi']['garden']['token']+'|'+recipe)
        view=act('contract_open',view['yaochi']['contracts']['token']+'|garden')
        assert request(path)['yaochi']['contracts']['active']['funded']>0
        view=act('contract_cancel',view['yaochi']['contracts']['token']+'|')
        assert not view['yaochi']['contracts']['active']
        def chapter(action):return act('purple_'+action,view['yaochi']['purple_east']['token']+'|')
        view=chapter('start');assert view['yaochi']['purple_east']['state']['phase']=='survey'
        view=chapter('pause');view=request(path);assert view['yaochi']['purple_east']['state']['paused_work']['progress']==0
        view=chapter('resume');assert view['yaochi']['purple_east']['state']['work']['years']==5
        view=chapter('work')
        assert view['yaochi']['purple_east']['state']['work']['progress']>0
    print(f'EXE westward verified: DLC={with_dlc}; optional gate, escrow/reload/refund, real teacher, identity and original mainline start/pause/resume/annual work',flush=True)
