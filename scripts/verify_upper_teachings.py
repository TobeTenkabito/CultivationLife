"""Four-world checks through the packaged host, using only isolated test saves."""
import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def verify_upper_teachings(base, folder, with_dlc):
    def post(identity, operation, **payload):
        endpoint = f'/api/games/{identity}/{operation}' if identity else '/api/games'
        request = Request(base + endpoint, data=json.dumps(payload).encode(),
                          headers={'Content-Type': 'application/json'}, method='POST')
        with urlopen(request, timeout=45) as response:
            return json.load(response)

    for path in ('buddhist', 'confucian'):
        made = post(None, None, name='上界成品验收', spirit_root='supreme_wood', path=path, seed=2143, preset_id='core')
        identity = made['id']
        file = folder / 'data/saves' / (identity + '.json')
        for world in ('celestial', 'asura', 'nether', 'reincarnation'):
            raw = json.loads(file.read_bytes())
            raw['pending_event'] = raw['active_trial'] = None
            player = raw['player']
            player.update(path=path, world=world, location_id=None, realm_index=9, layer=1,
                          immortal_power_converted=True, immortal_conversion_stage=5,
                          immortal_veins={'9':27}, haoran_exp=1_000_000)
            if path == 'buddhist':
                raw.setdefault('buddhist_state', {}).setdefault('wish', {})['value'] = 100
                raw['buddhist_state']['dharma_karma'] = 48
            file.write_text(json.dumps(raw, ensure_ascii=False), encoding='utf-8')
            with urlopen(base + f'/api/games/{identity}', timeout=45) as response:
                shown = json.load(response)
            assert shown['player']['world'] == world
            if not with_dlc:
                system = shown['buddhist_system'] if path == 'buddhist' else shown['sage_system']
                assert not system['available']
                try:
                    post(identity, 'buddhist-action' if path == 'buddhist' else 'sage-outer-king', action='nirvana' if path == 'buddhist' else 'advance')
                except HTTPError as error:
                    assert error.code == 400
                else:
                    raise AssertionError('Disabled DLC command accepted')
                continue
            if path == 'buddhist':
                assert shown['buddhist_system']['wish']['blocked']
                assert shown['buddhist_system']['wish']['value'] == 100
                shown = post(identity, 'buddhist-action', action='blessing', blessing=shown['buddhist_system']['blessings'][0]['id'])
                assert shown['buddhist_system']['blessings'][0]['selected']
            else:
                assert shown['sage_system']['teaching_available']
                if not shown['sage_system']['membership_id']:
                    post(identity, 'sage-doctrine', action='join', doctrine_id=shown['sage_system']['doctrines'][0]['id'])
                assert not shown['sage_system']['inner_outer']['outer_actions'][0]['can_use']
                before = shown['player']['opportunity']
                shown = post(identity, 'sage-outer-king', action='opportunity')
                assert shown['player']['opportunity'] > before
            try:
                post(identity, 'buddhist-action' if path == 'buddhist' else 'sage-outer-king', action='nirvana' if path == 'buddhist' else 'advance')
            except HTTPError as error:
                assert error.code == 400
            else:
                raise AssertionError('Upper DLC direct advancement accepted')
            assert shown['player']['layer'] == 1
