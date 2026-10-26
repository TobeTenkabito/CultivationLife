"""Focused actual EXE HTTP acceptance for the 3.0.1 release."""
import hashlib
import json
import urllib.request
import urllib.error


def verify_update301(base, with_dlc):
    def request(path, data=None):
        req = urllib.request.Request(base + path, data=json.dumps(data).encode() if data is not None else None,
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=40) as response:
            return json.load(response)
    assets = request('/api/visual-assets')['assets']
    entry = assets['base.character_manifest']
    assert len(entry['character_forms']) == 8
    for form in entry['character_forms'] + entry['skin_forms']:
        for kind in ['portrait', 'figure', 'thumbnail']:
            asset = assets[form['static'] + '.' + kind]
            with urllib.request.urlopen(base + asset['file'], timeout=10) as response:
                assert hashlib.sha256(response.read()).hexdigest() == asset['sha256']
    manifest = request(entry['file'])
    assert len(manifest['actors']) == 8
    made = request('/api/games', dict(name='成品换装验收', spirit_root='supreme_metal', path='dao', gender='female', seed=301,
                                    custom_start=dict(world='spirit', realm_index=7)))
    endpoint = '/api/games/' + made['id']
    before = request(endpoint)
    key = 'actor.path.dao-nascent-hero-female'
    chosen = request(endpoint + '/character-skin', dict(skin_id=key))
    assert chosen['player']['visual_actor'] == key
    assert request(endpoint)['player']['character_skins']['selected'] == key
    for field in ['realm_index', 'layer', 'world', 'age', 'opportunity', 'hp', 'mp', 'combat_power', 'inventory']:
        assert chosen['player'][field] == before['player'][field]
    try:
        request(endpoint + '/character-skin', dict(skin_id='locked'))
        raise AssertionError('Locked skin accepted')
    except urllib.error.HTTPError as error:
        assert error.code == 400
    assert request(endpoint + '/character-skin', dict(skin_id=''))['player']['visual_actor'] == 'actor.path.dao-integration-hero-female'
    assert any(key.startswith('actor.monster.') for key in assets) == with_dlc
    print(f'EXE 3.0.1 verified: DLC={with_dlc}; 8 forms, 36 static hashes, real skin save/reload/rejection, unchanged gameplay', flush=True)
