"""Known local office facts only; no hidden plans or remote person inventories."""
import copy
from . import rules, actions, management
from .. import institution_authority as authority
from ..economy.ledger import balance
from ..institution_ai.rules import record
from ...relationship_records import find_person


def public(game):
    if game.player.world!='asura' or not rules.enabled() and not rules.offices(game):return None
    state=rules.court(game);king=rules.king(game)
    def name(identity):
        if identity=='player':return game.player.name
        person=find_person(game,identity) if identity else None
        return person.name if person else '待任'
    result=[]
    for row in rules.offices(game):
        local=rules.local(game,row);mine='player' in (row['holder'],row['controller'],row['nominee'])
        data={k:copy.deepcopy(row[k]) for k in ('id','name','location','city_id','building_id','status','expires','holder','nominee','controller')}
        data.update(local=local,mine=mine,holder_name=name(row['holder'] or row['nominee'] or row['controller']),
                    active=authority.effective(game,row),building_status=(rules.building(game,row) or {}).get('status','unbuilt'))
        if king or mine:
            data.update(cash=balance(game,row['wallet']),history=copy.deepcopy(row['history']),people=list(row['people']))
        if local and mine:
            data.update(candidates=rules.eligible_people(game,row),quote=actions.bill(game,row) if rules.enabled() else None,agenda=copy.deepcopy(record(game,row['id'])))
        result.append(data)
    candidates=[]
    if king:
        from ..asura_court_finance import people
        candidates=[dict(id=n.id,name=n.name) for n in people(game).values() if n.alive and n.world=='asura'
                    and n.id!=state['court']['holders'].get('5') and n.id not in state['court']['offices'].values()]
    return dict(enabled=rules.enabled(),king=king,capital=game.player.location_id=='ten_thousand_battle_city',
        token=rules.token(game),offices=result,candidates=candidates,
        qualified=state.get('joined',False) and state.get('rank',0)>=rules.config().get('required_rank',1)
            and state.get('earned',0)>=rules.config().get('required_merit',100) and state.get('regard',0)>=rules.config().get('required_regard',20),
        cities=[dict(id=c['id'],name=c['name'],location=c['address']['location_id'],eligible=rules.legal_city(game,c)) for c in rules.cities(game)],
        management=management.public(game))
