"""Real packaged soul commands, with and without optional DLC."""
import json
import runpy
import urllib.request
from pathlib import Path


def verify_soul(base, with_dlc, folder):
    from cultivation_life.engine import GameEngine
    root=Path(__file__).resolve().parents[1]
    def request(path,data=None):
        req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=90) as response:return json.load(response)
    for asset in ('soul.js','soul.css'):
        with urllib.request.urlopen(base+'/'+asset) as response:assert response.status==200
    made=request('/api/games',dict(name='身魂成品验收',spirit_root='supreme_metal',path='dao',seed=320,preset_id='core'))
    engine=GameEngine(root,folder/'data/saves')
    runpy.run_path(str(root/'tests/fixtures/soul_release.py'))['prepare_soul'](engine,made['id'])
    path='/api/games/'+made['id']
    view=request(path)
    def act(action,**kw):
        nonlocal view
        view=request(path+'/soul',dict(action=action,revision=view['soul']['revision'],**kw))
        return view
    assert view['soul']['body']['maximum']==300
    act('leave');assert view['soul']['mode']=='神游'
    act('return');assert view['soul']['mode']=='普通'
    act('study',id='second_nascent')
    for _ in range(3):act('refine',id='release-nascent')
    assert view['soul']['second']['id']=='release-nascent'
    act('equip',id='release-soul-sword')
    assert view['soul']['second']['equipment'][0]['id']=='release-soul-sword'
    assert request(path)['soul']['second']==view['soul']['second']
    # Death settlement belongs to the actual packaged command, triggered through a real lethal battle elsewhere in regression.
    act('dismiss');assert view['soul']['second'] is None
    print(f'EXE soul verified: DLC={with_dlc}; real energy/leave/return/study/refine/equip/reload/dismiss',flush=True)
