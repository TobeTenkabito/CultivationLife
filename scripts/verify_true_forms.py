"""Exercise optional true forms in the actual Windows release executable."""
import json
import urllib.request


def verify_true_forms(base, folder, with_dlc):
    def post(route, payload):
        request = urllib.request.Request(base+'/api/'+route, method='POST', data=json.dumps(payload).encode(),
                                         headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    g = post('games',dict(name='本相成品',preset_id='nether_upper',monster_species_id='insect',seed=251))
    p = json.loads((folder/'data/saves'/f"{g['id']}.json").read_bytes())['player']
    if not with_dlc:
        assert not g['upper_voisinages']['true_form']
        assert len(g['upper_voisinages']['rows']) == 2
        assert not p['monster_generated_bloodline_traits']
        return
    assert p['monster_evolution_id'] == 'INSECT_NETHER_TRUE_1'
    assert len(p['monster_generated_bloodline_traits']) == 9
    energy = g['aperture']['current']
    route = f"games/{g['id']}/upper-voisinage"
    g = post(route,dict(action='true_form_confirm',voisinage_id='suppress'))
    assert g['aperture']['current'] == energy
    key = g['upper_voisinages']['true_form']['blueprint']['blueprint_id']
    g = post(route,dict(action='train',voisinage_id=key))
    assert g['upper_voisinages']['true_form']['level'] == 1
    g = post(route,dict(action='select',voisinage_id=key))
    assert g['upper_voisinages']['rows'][-1]['active']
    ghost = post('games',dict(name='魂契成品',preset_id='ghost_void',seed=251))
    raw = json.loads((folder/'data/saves'/f"{ghost['id']}.json").read_bytes())['player']
    assert raw['ghost_bound_souls'] and raw['ghost_soul_slots'] and raw['ghost_wangsheng_energy'] > 0
