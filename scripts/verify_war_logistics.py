"""Real packaged HTTP commands against disposable organization/conversion saves."""
import json
import urllib.request
import urllib.error


def verify_war_logistics(base, folder):
    def request(path, payload=None):
        req=urllib.request.Request(base+'/api/'+path, data=json.dumps(payload).encode() if payload is not None else None,
                                   headers={'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=60) as response:return json.load(response)
        except urllib.error.HTTPError as exc:
            log=folder/'data/logs/server-errors.log'
            if log.exists():print(log.read_text(encoding='utf-8')[-6000:])
            raise AssertionError(exc.read().decode('utf-8')) from exc
    result=request('games',dict(name='府库成品验收',preset_id='core',seed=419));identity=result['id']
    path=folder/'data/saves'/f'{identity}.json'
    data=json.loads(path.read_bytes());data['pending_event']=None
    data['player'].update(faction_id='tianjian',realm_index=4,location_id=data['sects']['tianjian']['location_id'])
    data['sects']['tianjian']['founded_by_player']=True
    data['intrigue_state'].setdefault('factions',{}).setdefault('sect:tianjian',dict(
        kind='sect',id='tianjian',controller_id=None,positions={},guests=[],prison=[],
        member_contribution={},unrest=0.,fear=0.,resources=0,policy='balance'))['resources']=1000000
    path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    result=request(f'games/{identity}');view=result['faction']['depot']
    data=json.loads(path.read_bytes());data['player']['location_id']=view['location']
    path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    result=request(f'games/{identity}');view=result['faction']['depot']
    stocked={r['id'] for r in result['map']['economy']['rows'] if r['stock']>=2}
    item=next(r for r in view['offers'] if r['kind']=='item' and r['tier']==1 and r['id'] in stocked)
    def command(action, **payload):
        nonlocal result,view
        result=request(f'games/{identity}/fleet-action',dict(action=action,owner_id='tianjian',revision=view['revision'],**payload))
        view=result['faction']['depot']
    command('depot_purchase',item=item['key'],quantity=2)
    command('depot_request',item=item['key'],quantity=1)
    rid=view['requests'][-1]['id']
    data=json.loads(path.read_bytes());data['diplomacy_unit']+=1
    path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    command('depot_approve',request_id=rid);command('depot_collect',request_id=rid)
    assert view['requests'][-1]['status']=='collected' and view['requests'][-1]['reserved']==0
    result=request('games',dict(name='仙元成品验收',preset_id='true_immortal',seed=9921));identity=result['id']
    path=folder/'data/saves'/f'{identity}.json'
    data=json.loads(path.read_bytes());data['pending_event']=None;data['heavenly_court']['open_election']=None
    data['player'].update(immortal_conversion_stage=0,immortal_power_converted=False,opportunity=100)
    path.write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
    result=request(f'games/{identity}/doctrine-action',dict(action='convert'))
    assert result['player']['immortal_conversion_stage']==1
    assert json.loads(path.read_bytes())['player']['opportunity']==0 and result['pending_event'] is None
    print('Packaged logistics: actual paid depot purchase, delayed approval/collection and opportunity conversion passed',flush=True)
