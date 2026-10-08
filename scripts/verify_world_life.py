"""Exercise the new release features through a running packaged server."""
import json
import urllib.request


def verify_world_life(base, folder):
    def post(route,payload):
        request=urllib.request.Request(base+'/api/'+route,method='POST',
            data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=30) as response:
            return json.load(response)
    life=post('games',dict(name='仙脉成品',spirit_root='supreme_metal',path='dao',seed=250,
                          custom_start=dict(world='celestial',realm_index=11,layer=9)))
    raw=json.loads((folder/'data/saves'/f"{life['id']}.json").read_bytes())
    assert raw['player']['immortal_veins']=={'9':27,'10':27,'11':24}
    life=post('games',dict(name='失落成品',spirit_root='supreme_metal',path='dao',seed=250,preset_id='lost_world'))
    route=f"games/{life['id']}/"
    assert {'faction','family'}<=set(life['spatial']['panels'])
    sect=life['spatial']['scene']['society']['sects'][0]
    life=post(route+'spatial-action',dict(action='join_sect',target_id=sect['id']))
    assert life['spatial']['scene']['joined_sect']==sect['id']
    life=post(route+'advance',dict(action='rest',years=1))
    assert life['pending_event']['id'].startswith('EVT_WANDER_SHARED_')
    life=post(route+'choice',dict(choice_id='leave',event_id=life['pending_event']['id']))
    assert life['pending_event'] is None
