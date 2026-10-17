"""Run the actual secret-art endpoints against a disposable built host."""
import json
from urllib.request import Request, urlopen
from urllib.error import HTTPError


def verify_secret_arts(base, folder):
    def post(identity, **payload):
        endpoint = '/api/games' if identity is None else f'/api/games/{identity}/secret-art'
        request = Request(base + endpoint, data=json.dumps(payload).encode(),
                          headers={'Content-Type': 'application/json'}, method='POST')
        with urlopen(request, timeout=60) as response:
            return json.load(response)
    made = post(None, name='秘术成品验收', spirit_root='supreme_metal', path='dao', seed=2150)
    identity = made['id']
    path = folder / 'data/saves' / f'{identity}.json'
    raw = json.loads(path.read_bytes())
    p = raw['player']
    raw['pending_event'] = None
    raw['settings'].update(silent_events=True, guixu_event_popup=False)
    p.update(realm_index=1, layer=1, age=18, lifespan=200, additional_roots=[], secret_art_state={})
    p['inventory'].extend([dict(id='secret_manual_water', name='秘术传承', quantity=1),
                           dict(id='secret_core_water_4', name='水属内丹', quantity=1),
                           dict(id='spirit_stone', name='灵石', quantity=50000)])
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding='utf-8')
    learned = post(identity, art='root_water', action='study', revision=0, years=5)
    if not next(a for a in learned['secret_arts']['library'] if a['id'] == 'root_water')['learned']:
        raise RuntimeError('Built host did not complete actual secret-art learning')
    finished = post(identity, art='root_water', action='practice', revision=1, years=10,
                    material_id='item:secret_core_water_4')
    if finished['player']['additional_roots'] != ['water'] or finished['player']['age'] != 33:
        raise RuntimeError('Built host failed root grafting/time settlement')
    if finished['player']['spirit_root'] != 'supreme_metal':
        raise RuntimeError('Root grafting changed innate quality')
    try:
        post(identity, art='root_water', action='practice', revision=1, years=10)
    except HTTPError as error:
        if error.code != 400:
            raise
    else:
        raise RuntimeError('Built host accepted a replayed secret-art page')
    print('Secret arts EXE scope passed: real low-rank learning, timed grafting, exact source and replay rejection')
