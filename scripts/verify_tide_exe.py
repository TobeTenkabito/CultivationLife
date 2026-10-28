"""Validate the exact compiled UI, global achievement gate and cross-save skins."""
import json
import runpy
import urllib.request
import urllib.error
from pathlib import Path


def verify_tide(base,folder):
    from cultivation_life.engine import GameEngine
    root=Path(__file__).resolve().parents[1]
    def request(path,data=None):
        req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=90) as r:return json.load(r)
    catalog=json.loads((root/'content/visual_assets.json').read_text(encoding='utf-8'))
    paths=['/tide-effects.js','/pixel-dark.css','/desktop-labels.js','/theme-manager.js','/secret-art-panel.js']
    paths += [r['file'] for r in catalog['assets'].values() if r['file'].startswith('/assets/pixel/tide/')]
    for path in paths:
        with urllib.request.urlopen(base+path) as r:assert r.read()==(root/'web'/path.lstrip('/')).read_bytes()
    request('/api/ui-preferences',dict(pixel_art=True,pixel_theme='dark',compact_docks=False))
    prefs=request('/api/ui-preferences');assert prefs['pixel_theme']=='dark' and not prefs['compact_docks']
    games=[]
    for gender in ['female','male']:
        made=request('/api/games',dict(name='潮汐成品',spirit_root='supreme_metal',path='dao',gender=gender,seed=323,custom_start=dict(world='human',realm_index=1)))
        path='/api/games/'+made['id'];key=f'actor.cosmetic.swim-tide-{gender}'
        try:request(path+'/character-skin',dict(skin_id=key))
        except urllib.error.HTTPError as e:assert e.code==400
        else:raise AssertionError('Achievement gate bypassed')
        games.append((made['id'],path,key))
    engine=GameEngine(root,folder/'data/saves')
    runpy.run_path(str(root/'tests/fixtures/tide_release.py'))['earn_legend'](engine,games[0][0])
    for identity,path,key in games:
        assert request(path+'/character-skin',dict(skin_id=key))['player']['visual_actor']==key
        view=request(path)['player'];assert view['realm_index']==1 and view['character_skins']['selected']==key
    print('EXE tide verified: exact artwork/FX/theme bytes, persisted preferences, achievement gate and both low-realm genders',flush=True)
