"""Verify holiday selection and original packaged asset bytes over real EXE HTTP."""
import json
import urllib.request
from pathlib import Path


def verify_holiday(base):
    root = Path(__file__).resolve().parents[1]
    def request(path, data=None):
        req = urllib.request.Request(base+path, data=json.dumps(data).encode() if data is not None else None,
                                     headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req, timeout=90) as response: return json.load(response)
    catalog = json.loads((root/'content/visual_assets.json').read_text(encoding='utf8'))
    paths = ['/'+name for name in ('holiday-effects.js','spell-effects.js')]
    paths += [a['file'] for a in catalog['assets'].values() if a['file'].startswith('/assets/pixel/holiday/')]
    for path in paths:
        with urllib.request.urlopen(base+path) as response:
            assert response.read() == (root/'web'/path.lstrip('/')).read_bytes(), path
    for gender in ('male','female'):
        made = request('/api/games',dict(name='节日成品',spirit_root='supreme_metal',path='dao',gender=gender,seed=321,preset_id='core'))
        path = '/api/games/'+made['id']
        for style in ('halloween','christmas'):
            key = f'actor.cosmetic.{style}-{gender}'
            view = request(path+'/character-skin',dict(skin_id=key))
            assert view['player']['visual_actor'] == key
            assert request(path)['player']['character_skins']['selected'] == key
    print('EXE holiday verified: four unrestricted costumes, reload, all art and effect bytes',flush=True)
