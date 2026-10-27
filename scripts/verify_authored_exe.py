"""Actual packaged server commands with and without the authoring DLC."""
import json
import urllib.request
import urllib.error


def verify_authored(base,with_dlc):
    def request(path,data=None):
        req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=60) as response:return json.load(response)
    for asset in ('authored-techniques.js','authored-techniques.css','npc-contacts.css'):
        with urllib.request.urlopen(base+'/'+asset) as response:assert response.status==200
    made=request('/api/games',dict(name='成品创法验收',spirit_root='supreme_metal',path='dao',seed=310,custom_start=dict(world='human',realm_index=3)))
    path='/api/games/'+made['id']
    assert made['authored_techniques']['available']==with_dlc
    design=dict(name='成品流云真经',grade=1,category='support',allocations=dict(opportunity_bonus=1,hp_bonus=1,mp_bonus=1,combat_bonus=1),buffs=[])
    if not with_dlc:
        try:request(path+'/authored-technique',dict(action='create',design=design,revision=0));raise AssertionError('Disabled DLC accepted creation')
        except urllib.error.HTTPError as error:assert error.code==400
        assert request('/api/authored-lineages')==dict(available=False,lineages=[])
    else:
        created=request(path+'/authored-technique',dict(action='create',design=design,revision=0))
        key=created['authored_techniques']['books'][0]['id']
        request(path+'/authored-technique',dict(action='manual',id=key,level=1,revision=1))
        request(path+'/technique-upgrade',dict(technique_id=key))
        assert request(path)['authored_techniques']['books'][0]['level']==2
        successor=request('/api/games',dict(name='传承成品验收',spirit_root='supreme_metal',path='dao',seed=311,inherit_from=made['id']))
        assert successor['authored_techniques']['books'][0]['id']==key
        assert successor['authored_techniques']['books'][0]['level']==0
        assert successor['authored_techniques']['books'][0]['own'] is False
    print(f'EXE authored verified: DLC={with_dlc}; real create/manual/upgrade/reload/inherit or disabled rejection',flush=True)
