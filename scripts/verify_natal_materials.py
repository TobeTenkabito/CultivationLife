"""Exercise new base materials through a packaged server, in its isolated saves."""
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def verify_natal_materials(base, folder):
    def post(identity, operation, **payload):
        endpoint = f'/api/games/{identity}/{operation}' if identity else '/api/games'
        request = Request(base + endpoint, data=json.dumps(payload).encode(),
                          headers={'Content-Type': 'application/json'}, method='POST')
        with urlopen(request, timeout=30) as response:
            return json.load(response)
    game = post(None, None, name='镶材成品验收', spirit_root='supreme_metal', path='dao', seed=2142, preset_id='core')
    identity = game['id']
    path = folder / 'data/saves' / f'{identity}.json'
    raw = json.loads(path.read_bytes())
    raw['pending_event'] = None
    raw['player']['inventory'].append(dict(id='natal_human_pine_metal', name='松纹青铜', quantity=2))
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding='utf-8')
    post(identity, 'natal-artifact', action='bind', item_id='starfall_blade')
    raw = json.loads(path.read_bytes())
    raw['natal_artifact'].update(level=30, slots=[None] * 3)
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding='utf-8')
    with urlopen(base + f'/api/games/{identity}', timeout=30) as response:
        shown = json.load(response)
    materials = [r for r in shown['natal_artifact']['materials'] if r['item_id'].startswith('natal_')]
    assert len(materials) == 111 and len({r['world'] for r in materials}) == 11
    assert len({(r['world'], r['minimum_realm']) for r in materials}) == 37
    before = shown['natal_artifact']['bonuses']['combat_bonus']
    shown = post(identity, 'natal-artifact', action='socket', item_id='natal_human_pine_metal', slot_index=0)
    assert shown['natal_artifact']['bonuses']['combat_bonus'] == before + 300
    assert shown['natal_artifact']['slots'][0]['name'] == '松纹青铜'
    try:
        post(identity, 'natal-artifact', action='socket', item_id='natal_human_pine_metal', slot_index=1)
    except HTTPError as error:
        assert error.code == 400
    else:
        raise AssertionError('Duplicate material accepted by packaged server')
    shown = post(identity, 'natal-artifact', action='unsocket', slot_index=0)
    assert shown['natal_artifact']['bonuses']['combat_bonus'] == before
    assert next(r['quantity'] for r in shown['player']['inventory'] if r['id'] == 'natal_human_pine_metal') == 2
