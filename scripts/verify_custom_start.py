"""Exercise the final packaged server, with and without optional DLC content."""
import json
import urllib.request


def verify_custom_start(base, with_dlc):
    def request(path, payload=None):
        req = urllib.request.Request(base + '/api/' + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.load(response)
    config = request('config')
    assert config['custom_start']['tianji_enabled'] == with_dlc
    result = request('games', dict(name='成品自定义验收', spirit_root='supreme_metal', path='dao', seed=412,
        custom_start=dict(world='human', realm_index=3, layer=1, divine_sense_rank=23, sect='new',
            sect_name='成品宗门', inventory=[dict(id='spirit_stone', quantity=1000000), dict(id='spirit_sword', quantity=1)],
            natal_artifact='spirit_sword')))
    gid = result['id']
    assert result['faction']['name'] == '成品宗门'
    assert result['player']['cultivation_ranks']['sense']['name'] == '筑基中期'
    result = request(f'games/{gid}/fleet-action', dict(action='organization_fund', owner_kind='sect', amount=100000))
    assert result['faction']['finance']['balance'] == 100000
    result = request(f'games/{gid}/fleet-action', dict(action='create', owner_kind='sect'))
    assert any(f['owner_kind'] == 'sect' and f['player_controlled'] for f in result['fleet_network']['fleets'])
    assert request(f'games/{gid}')['player']['divine_sense']['level'] == 23
