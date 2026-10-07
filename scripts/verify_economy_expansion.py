"""Exercise the packaged HTTP command boundary using a disposable save."""
import json
import urllib.request


def verify_economy_expansion(base, folder):
    def request(path, payload=None):
        req = urllib.request.Request(base + '/api/' + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.load(response)
    game = request('games', dict(name='迁盟打包验收', preset_id='core', seed=419))
    identity = game['id']
    path = folder / 'data/saves' / f'{identity}.json'
    def raw():
        return json.loads(path.read_bytes())
    def save(data):
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
    def action(name, **payload):
        return request(f'games/{identity}/fleet-action', dict(action=name, **payload))
    def visit(world, location, realm=None):
        data = raw()
        data['player'].update(world=world, location_id=location)
        if realm is not None:
            data['player']['realm_index'] = realm
        save(data)
        return request(f'games/{identity}')
    data = raw()
    data['pending_event'] = None
    data['player'].update(realm_index=2, next_tribulation_age=None)
    data['player']['inventory'].append(dict(id='spirit_stone', name='灵石', quantity=10**9))
    save(data)
    action('create')
    free = [f for f in raw()['economy_v2']['transport']['worlds']['human']['fleets'].values()
            if f['owner_kind'] == 'independent' and not f['player_controlled']]
    for fleet in free[:2]:
        visit('human', fleet['location'])
        action('pledge', fleet_id=fleet['id'])
    action('found')
    visit('spirit', raw()['merchant_state']['worlds']['spirit'][0]['hq'], 8)
    free = [f for f in raw()['economy_v2']['transport']['worlds']['spirit']['fleets'].values() if f['owner_kind'] == 'independent']
    for fleet in free[:3]:
        visit('spirit', fleet['location'])
        action('pledge', fleet_id=fleet['id'])
    assert action('relocate')['fleet_network']['main_hq']
    result = action('build_passage')
    assert any(d['world'] == 'human' and d['open'] for d in result['fleet_network']['destinations'])
    data = raw()
    home = next(a for a in data['merchant_state']['worlds']['spirit'] if a.get('player_owned'))
    fleet = next(f for f in data['economy_v2']['transport']['worlds']['spirit']['fleets'].values() if f['alliance_id'] == home['id'])
    fleet.update(location=home['hq'], investment=10**7)
    data['economy_v2']['accounts'][f'caravan:{fleet["id"]}']['balance'] = 10**7
    for row in data['economy_v2']['markets'][f'spirit:{home["hq"]}']['commodities'].values():
        row['stock'] = row['target'] * 3
    save(data)
    result = action('cross_dispatch', fleet_id=fleet['id'], destination='human', remittance_percent=50)
    assert any(f['cross_trip'] for f in result['fleet_network']['fleets'])
    data = raw()
    trip = data['economy_v2']['transport']['worlds']['spirit']['fleets'][fleet['id']]['cross_trip']
    data['player']['age'] = trip['arrival']
    for route in data['economy_v2']['network']['routes'].values():
        if route['alliance_id'] == home.get('network_id', home['id']):
            route['open'] = False
    save(data)
    result = action('cross_recall', fleet_id=fleet['id'])
    assert any(f['cross_trip'] and f['cross_trip']['phase'] == 'return' for f in result['fleet_network']['fleets'])
    result = action('reopen')
    assert any(d['world'] == 'human' and d['open'] for d in result['fleet_network']['destinations'])
    request(f'games/{identity}')
    print('Packaged economy expansion: actual relocation, construction, dispatch, recall and repair passed', flush=True)
