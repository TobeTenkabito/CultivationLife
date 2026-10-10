"""Exercise new base-game actions against the actual packaged HTTP server."""
import json
import urllib.request
import urllib.error


def verify_organizations(base,folder):
    def request(path,payload=None):
        req=urllib.request.Request(base+path,method='GET' if payload is None else 'POST',
            data=None if payload is None else json.dumps(payload).encode(),headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)
        except urllib.error.HTTPError as error:raise AssertionError(error.read().decode('utf-8')) from error
    g=request('/api/games',dict(name='成品势力验收',spirit_root='supreme_earth',path='dao',seed=290,
        custom_start=dict(world='human',realm_index=4,sect='new',sect_name='成品验收宗')))
    identity=g['id'];sid=g['faction']['id'];path=folder/'data/saves'/f'{identity}.json'
    raw=json.loads(path.read_bytes());raw['pending_event']=None
    raw['player']['inventory'].append(dict(id='spirit_stone',name='灵石',quantity=20000))
    raw['sects'][sid]['heritage']=dict(books=['TECH_HUMAN_HERITAGE_1'],revision=0,history=[])
    raw['player']['known_techniques']=[t for t in raw['player']['known_techniques'] if t['id']!='TECH_HUMAN_HERITAGE_1']
    def capital(raw,key,amount):
        kind,identity=key.split(':',1)
        raw['intrigue_state'].setdefault('factions',{}).setdefault(key,dict(kind=kind,id=identity,controller_id=None,
            positions={},guests=[],prison=[],member_contribution={},unrest=0.,fear=0.,resources=0,policy='balance'))['resources']=amount
    capital(raw,f'sect:{sid}',2000000)
    path.write_text(json.dumps(raw,ensure_ascii=False),encoding='utf-8')
    g=request(f'/api/games/{identity}')
    def post(action,payload):return request(f'/api/games/{identity}/{action}',payload)
    wallet=sum(i['quantity'] for i in g['player']['inventory'] if i['id']=='spirit_stone')
    h=g['faction']['heritage']
    g=post('fleet-action',dict(action='heritage_learn',owner_id=sid,revision=h['revision'],technique_id='TECH_HUMAN_HERITAGE_1'))
    assert g['faction']['heritage']['books'][0]['learned']
    g=post('fleet-action',dict(action='heritage_copy',owner_id=sid,revision=g['faction']['heritage']['revision'],technique_id='TECH_HUMAN_HERITAGE_1'))
    assert sum(i['quantity'] for i in g['player']['inventory'] if i['id']=='spirit_stone')==wallet-120
    assert any(i.get('technique_id')=='TECH_HUMAN_HERITAGE_1' for i in g['player']['inventory'])
    raw=json.loads(path.read_bytes());site=next(l['id'] for l in g['map']['locations'] if l['id'] not in {a['id'] for a in g['map']['teleport']['arrays']} and l.get('travel_status')!='lethal')
    raw['player']['location_id']=site;path.write_text(json.dumps(raw,ensure_ascii=False),encoding='utf-8')
    g=request(f'/api/games/{identity}');plan=next(r for r in g['map']['teleport']['construction'] if r['owner_id']==sid)
    assert plan['can_build']
    g=post('teleport-action',dict(action='build',owner_id=sid))
    assert g['map']['teleport']['origin']['owner_id']==sid
    clan=next(s for s in json.loads(path.read_bytes())['sects'].values() if s['kind']=='family' and s['world']=='human')
    raw=json.loads(path.read_bytes());raw['player']['location_id']=clan['location_id'];capital(raw,f'sect:{clan["id"]}',100000)
    path.write_text(json.dumps(raw,ensure_ascii=False),encoding='utf-8');request(f'/api/games/{identity}')
    g=post('family-action',dict(action='join',target_id=clan['id']))
    assert g['family']['player_member_type']=='外姓修士'
    raw=json.loads(path.read_bytes());assert raw['family']['id']==clan['id'] and clan['id'] not in raw['sects']
    assert raw['economy_v2']['teleport_arrays']
    print('Packaged organization actions passed: free study, paid jade slip, local array and original outsider clan')
