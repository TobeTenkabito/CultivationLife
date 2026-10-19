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
