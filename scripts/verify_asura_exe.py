"""Original office and army commands served by the final packaged executable."""
import json,runpy,urllib.request,urllib.error
from pathlib import Path

def verify_asura(base,with_dlc,folder):
    from cultivation_life.engine import GameEngine
    root=Path(__file__).resolve().parents[1]
    fixture=runpy.run_path(str(root/'tests/fixtures/asura_release.py'))
    def request(path,data=None):
        req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,
                                   headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req,timeout=90) as response:return json.load(response)
    for asset in ('asura-governorship.js','asura-court-panel.css','dlc-controls.css','dlc-controls.js'):
        with urllib.request.urlopen(base+'/'+asset) as response:assert response.read()==(root/'web'/asset).read_bytes()
    made=request('/api/games',dict(name='王庭成品验收',spirit_root='supreme_metal',path='demonic',seed=373,preset_id='asura_upper'))
    engine=GameEngine(root,folder/'data/saves')
    fixture['prepare_asura'](engine,made['id'],appoint=with_dlc)
    path='/api/games/'+made['id'];view=request(path)
    def govern(action,**kwargs):
        d=view['upper_institution']['court']['governorship']
        return request(path+'/upper-institution',dict(action='governorship',target_id=json.dumps(dict(action=action,token=d['token'],**kwargs))))
    if not with_dlc:
        assert not view['upper_institution']['court'].get('governorship')
        try:request(path+'/upper-institution',dict(action='governorship',target_id=json.dumps(dict(action='request',token='forged'))))
        except urllib.error.HTTPError as error:assert error.code==400
        else:raise AssertionError('Missing DLC accepted an appointment')
        assert not engine.store.load(made['id']).economy_v2.get('administrations')
        print('EXE Asura absent: dedicated appointment rejected; original court loads',flush=True)
        return
    def office():return view['upper_institution']['court']['governorship']['offices'][0]
    identity=office()['id'];location=office()['location']
    view=govern('assume',office=identity);q=office()['quote']
    before=office()['cash'];view=govern('build',office=identity,quote=q['token'],total=q['total'])
    assert office()['building_status']=='intact' and office()['cash']==before-q['total']
    view=govern('petition',office=identity,operation='observe')
    case=next(c for c in office()['disputes']['active'] if c['kind']=='remittance')
    before=office()['cash'];view=govern('petition',office=identity,operation='resolve',case=case['id'],choice='pay')
    assert office()['cash']==before-case['evidence']['amount']
    original=office()['cash']
    view=govern('protocol',office=identity,operation='divert',amount=3000)
    c=office()['protocols']['cases'][0]
    assert office()['cash']==original-3000
    view=govern('protocol',office=identity,operation='restitute',case=c['id'],amount=1000)
    assert office()['protocols']['cases'][0]['paid']==1000
    view=govern('protocol',office=identity,operation='restitute',case=c['id'],amount=2000)
    assert not office()['protocols']['cases'] and office()['cash']==original
    person=office()['military']['candidates'][0]['id']
    view=govern('military',office=identity,operation='enlist',person=person)
    view=govern('military',office=identity,operation='provision',amount=10**8)
    fixture['issue_release_order'](engine,made['id']);view=request(path)
    for choice in ('delay','refuse','comply'):
        view=govern('military',office=identity,operation='respond',choice=choice)
    assert office()['military']['units'][0]['phase']=='outbound'
    assert engine.store.load(made['id']).player.location_id==location
    fixture['advance_release_army'](engine,made['id']);view=request(path)
    view=govern('military',office=identity,operation='recall')
    fixture['advance_release_army'](engine,made['id'],2);view=request(path)
    assert not office()['military']['units'] and office()['military']['spent']>0
    view=govern('military',office=identity,operation='enlist',person=person)
    view=govern('military',office=identity,operation='provision',amount=10**8)
    fixture['support_release_commander'](engine,made['id']);view=request(path)
    view=govern('military',office=identity,operation='rebel')
    assert office()['status']=='handover' and office()['military']['conflict']['status']=='raised'
    view=govern('military',office=identity,operation='standdown')
    assert office()['military']['conflict']['status']=='withdrawn'
    print('EXE Asura: original building, petitions, paid garrison, military orders, real road return and rising/standdown passed',flush=True)
