"""Real final EXE rank gate, selection, reload and exact bundled gun/skin bytes."""
import json
import urllib.request
import urllib.error
from pathlib import Path


def verify_frontier(base):
    root=Path(__file__).resolve().parents[1]
    def request(path,data=None):
        req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,
            headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=90) as r:return json.load(r)
    catalog=json.loads((root/'content/visual_assets.json').read_text(encoding='utf8'))
    paths=['/frontier-effects.js','/character-skins.js','/character-skins.css','/soul.js']
    paths += [a['file'] for a in catalog['assets'].values() if a['file'].startswith('/assets/pixel/frontier/')]
    for path in paths:
        with urllib.request.urlopen(base+path) as r:
            assert r.read()==(root/'web'/path.lstrip('/')).read_bytes(),path
    for gender in ['male','female']:
        for rank in [1,7]:
            made=request('/api/games',dict(name='荒原成品',spirit_root='supreme_metal',path='dao',
                gender=gender,seed=322,custom_start=dict(world='spirit' if rank==7 else 'human',realm_index=rank)))
            path='/api/games/'+made['id']
            cowboy=f'actor.cosmetic.frontier-{gender}';swim=f'actor.cosmetic.swim-integration-{gender}'
            assert request(path+'/character-skin',dict(skin_id=cowboy))['player']['visual_actor']==cowboy
            if rank==1:
                try:request(path+'/character-skin',dict(skin_id=swim))
                except urllib.error.HTTPError as error:assert error.code==400
                else:raise AssertionError('Locked swimwear accepted')
                assert request(path)['player']['character_skins']['selected']==cowboy
            else:
                assert request(path+'/character-skin',dict(skin_id=swim))['player']['visual_actor']==swim
                assert request(path)['player']['character_skins']['selected']==swim
    print('EXE frontier verified: both genders, rank-seven gate, reload and packaged art/FX/UI',flush=True)
