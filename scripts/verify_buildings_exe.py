"""Exercise compiled building commands using HTTP and an isolated test save."""
import json
import urllib.request


def verify(base,folder):
    from cultivation_life.models import GameState
    from cultivation_life.rules import add_item
    from cultivation_life.system.building_projects import quote
    def call(path,payload=None):
        request=urllib.request.Request(base+path,data=json.dumps(payload).encode() if payload is not None else None,
            headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(request,timeout=40) as response:return json.load(response)
    game=call('/api/games',dict(name='城郭成品验收',spirit_root='supreme_metal',path='dao',preset_id='core',seed=2170))
    identity=game['id'];path=f'/api/games/{identity}'
    save=folder/'data/saves'/f'{identity}.json'
    raw=GameState.from_dict(json.loads(save.read_text(encoding='utf-8')))
    raw.pending_event=None
    add_item(raw.player,'spirit_stone',10**14)
    for key in quote(raw,'city')['materials']:add_item(raw.player,key,100000)
    save.write_text(json.dumps(raw.to_dict(),ensure_ascii=False),encoding='utf-8')
    before_age=raw.player.age
    def choose(choice):
        nonlocal game
        offered=game['pending_event']
        if choice.endswith(':'):
            choice=next(c['id'] for c in offered['choices'] if c['id'].startswith(choice))
        game=call(path+'/choice',dict(choice_id=choice,event_id=offered['id']))
    game=call(path)
    assert len([r for p in game['map']['locations'] for r in p['buildings'] if r['type']=='city'])==2
    assert len([r for p in game['map']['locations'] for r in p['buildings'] if r['type']=='scenery'])==1
    game=call(path+'/building-action',dict(action='city-plan'))
    choose('city:military');choose('city:military:mixed');choose('city:build:')
    city=next(r for r in game['buildings']['rows'] if r['owner']==dict(kind='player',id=identity) and r['type']=='city')
    assert city['level']==1
    choose('city:story');choose('city:resolve:0');choose('back')
    choose('management');choose('destroy');choose('destroy:')
    assert any(r['id']==city['id'] and r['name'].endswith('遗址') and not r['can_enter'] for r in game['buildings']['rows'])
    choose('rebuild');choose('rebuild:');choose('back');choose('city:story')
    assert not game['pending_event']['choices'][0]['enabled']
    choose('leave')
    assert game['player']['age']==before_age and not game['pending_event']
    assert json.loads(save.read_text(encoding='utf-8'))['building_state']['city_usage'][city['id']]['story']==1
    for asset in ('building-panel.js','building-panel.css'):
        with urllib.request.urlopen(base+'/'+asset,timeout=10) as response:assert response.read()
    return True
