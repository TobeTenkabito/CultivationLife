"""Final compiled HTTP visit actions, with optional Buddhist content truly absent."""
import copy
import json
import urllib.error
import urllib.request


def verify(base,folder,with_dlc):
    from cultivation_life.models import GameState
    from cultivation_life.rules import add_item
    def call(path,payload=None):
        request=urllib.request.Request(base+path,data=json.dumps(payload).encode() if payload is not None else None,
            headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=45) as response:return json.load(response)
    game=call('/api/games',dict(name='建筑游历成品验收',spirit_root='heavenly',path='dao',preset_id='core',seed=2171))
    path='/api/games/'+game['id'];save=folder/'data/saves'/f"{game['id']}.json"
    raw=GameState.from_dict(json.loads(save.read_text(encoding='utf-8')))
    raw.pending_event=None
    if with_dlc:raw.player.path='buddhist'
    add_item(raw.player,'spirit_stone',10**8)
    save.write_text(json.dumps(raw.to_dict(),ensure_ascii=False),encoding='utf-8')
    age=raw.player.age;game=call(path)
    def choose(identity):
        nonlocal game
        game=call(path+'/choice',dict(choice_id=identity,event_id=game['pending_event']['id']))
    offer=next(o for o in game['map']['economy']['enterprises']['offers'] if o['kind']=='mine')
    game=call(path+'/fleet-action',dict(action='estate_buy',kind='mine',cost=offer['cost']))
    row=next(r for r in game['buildings']['rows'] if r['type']=='industry')
    books=copy.deepcopy(json.loads(save.read_text(encoding='utf-8'))['economy_v2'])
    game=call(path+'/building-action',dict(action='enter',building_id=row['id']))
    choose('visit:ledger');choose('back');choose('visit:work');choose('visit:resolve:work:0');choose('back')
    choose('visit:lesson');stale=game['pending_event']['id'];choose('visit:resolve:lesson:1');choose('back');choose('visit:lesson')
    assert not game['pending_event']['choices'][0]['enabled']
    try:call(path+'/choice',dict(choice_id='visit:resolve:lesson:0',event_id=stale))
    except urllib.error.HTTPError as error:assert error.code==400
    else:raise AssertionError('Stale visit choice was accepted')
    choose('leave')
    assert json.loads(save.read_text(encoding='utf-8'))['economy_v2']==books
    if with_dlc:
        game=call(path+'/building-action',dict(action='temple-plan'));choose('confirm')
        for activity in ('bell','pilgrims','lesson'):
            choose('visit:'+activity);choose('visit:resolve:'+activity+':0');choose('back')
        choose('visit:lesson');assert not game['pending_event']['choices'][0]['enabled'];choose('leave')
    else:
        assert not any(r.get('subtype')=='temple' for r in game['buildings']['rows'])
        try:call(path+'/building-action',dict(action='temple-plan'))
        except urllib.error.HTTPError as error:assert error.code==400
        else:raise AssertionError('Absent DLC allowed temple construction')
    raw=GameState.from_dict(json.loads(save.read_text(encoding='utf-8')))
    scenery=next((p,r) for p in game['map']['locations'] for r in p['buildings'] if r['type']=='scenery')
    raw.player.location_id=scenery[0]['id']
    save.write_text(json.dumps(raw.to_dict(),ensure_ascii=False),encoding='utf-8')
    game=call(path);before=GameState.from_dict(json.loads(save.read_text(encoding='utf-8'))).player.to_dict()
    game=call(path+'/building-action',dict(action='enter',building_id=scenery[1]['id']))
    for activity in ('trail','weather','traces'):
        choose('visit:'+activity);choose('visit:resolve:'+activity+':1');choose('back')
    choose('leave')
    raw=GameState.from_dict(json.loads(save.read_text(encoding='utf-8')))
    assert raw.player.to_dict()==before and raw.player.age==age
    assert len(raw.building_state['visit_usage'])==(2 if with_dlc else 1)
    for asset in ('assets/building-gazetteer-2171.png','assets/building-icons/log-in.svg'):
        with urllib.request.urlopen(base+'/'+asset,timeout=15) as response:assert response.read()
    print(f'Building visits EXE passed: DLC={with_dlc}, real branches, bounded insight, unchanged stock and scenery')
    return True


def verify_management(base,folder):
    from cultivation_life.models import GameState
    from cultivation_life.rules import add_item
    from cultivation_life.system.building_projects import quote
    from cultivation_life.building_rules import config
    def call(path,payload=None):
        request=urllib.request.Request(base+path,data=json.dumps(payload).encode() if payload is not None else None,headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=45) as response:return json.load(response)
    game=call('/api/games',dict(name='城务山河成品验收',spirit_root='heavenly',path='dao',preset_id='core',seed=2172))
    path='/api/games/'+game['id'];save=folder/'data/saves'/f"{game['id']}.json"
    raw=GameState.from_dict(json.loads(save.read_text(encoding='utf-8')));raw.pending_event=None
    raw.settings.update(silent_events=True,guixu_event_popup=False,combat_popup=False);raw.player.next_tribulation_age=None
    add_item(raw.player,'spirit_stone',10**12)
    for key in quote(raw,'city')['materials']:add_item(raw.player,key,100000)
    save.write_text(json.dumps(raw.to_dict(),ensure_ascii=False),encoding='utf-8')
    def choose(prefix):
        nonlocal game
        selected=next(c['id'] for c in game['pending_event']['choices'] if c['id']==prefix or c['id'].startswith(prefix))
        game=call(path+'/choice',dict(choice_id=selected,event_id=game['pending_event']['id']))
    game=call(path+'/building-action',dict(action='city-plan'));choose('city:economic');choose('city:economic:mixed');choose('city:build:')
    city=next(r['id'] for r in game['buildings']['rows'] if r['id'].startswith('city:player:'))
    choose('civic:main');choose('civic:facilities');choose('civic:exchange');choose('civic:commit:');choose('civic:settle')
    assert not game['pending_event']['choices'][0]['enabled'];choose('leave')
    age=game['player']['age'];game=call(path+'/advance',dict(action='rest',years=1));assert game['player']['age']==age+1
    game=call(path+'/building-action',dict(action='enter',building_id=city));choose('civic:main');choose('civic:settle');choose('civic:commit:')
    choose('civic:settle');assert not game['pending_event']['choices'][0]['enabled'];choose('leave')
    raw=GameState.from_dict(json.loads(save.read_text(encoding='utf-8')))
    book=raw.building_state['city_business'][city];assert book['income']==2000 and book['expense']==13200
    raw.player.location_id=config()['scenery']['human'][1]['location_id'];save.write_text(json.dumps(raw.to_dict(),ensure_ascii=False),encoding='utf-8')
    game=call(path+'/building-action',dict(action='enter',building_id='scenery:human:reed_letter'))
    choose('explore:main');choose('explore:route:0');choose('explore:finish:0:1');choose('explore:main');choose('explore:route:1');choose('explore:finish:1:1');choose('leave')
    raw=GameState.from_dict(json.loads(save.read_text(encoding='utf-8')))
    assert sum(i.quantity for i in raw.player.inventory if i.id=='landscape_reed_letter')==1
    assert raw.building_state['landscape_usage']['scenery:human:reed_letter']==dict(ending='0:1')
    print('City management EXE passed: real facilities, annual cash, no repeat payout and authored two-stage landscape relic')
    return True
