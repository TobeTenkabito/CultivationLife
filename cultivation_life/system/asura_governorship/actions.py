"""Local Asura appointments and original building/fund transactions."""
import copy
from . import rules, management
from .. import institution_authority as authority, building_projects
from ..building_destruction import rebuild
from ..institution_ai import procurement
from ..institution_ai.rules import record as agenda
from ..economy.ledger import balance
from ..asura_court_finance import COURT
from ...building_rules import ensure_state


def bill(game,row):
    target=rules.building(game,row) or rules.shell(row)
    market=game.economy_v2.get('markets',{}).get(row['world']+':'+row['location'])
    quoted=building_projects.quote(game,'rebuild',target,payer=row['wallet'],stock={})
    reason=quoted['reason'] if quoted['reason']!='灵石或筑城材料不足' else ''
    try:
        purchase=procurement.cost(market,quoted['materials'])
    except ValueError as error:
        purchase=0;reason=str(error)
    total=quoted['coins']+purchase
    if not reason and balance(game,row['wallet'])<total:reason='本府公款不足，须先拨款或资助'
    return dict(quoted,purchase=purchase,total=total,reason=reason)


def require_place(game,row):
    if not rules.local(game,row):raise ValueError('须亲赴原总督府所在地办理')


def settle(game,payload):
    if not isinstance(payload,dict) or payload.get('token')!=rules.token(game):
        raise ValueError('任职、地点或公款已变化，请刷新后办理')
    action=payload.get('action')
    if not isinstance(action,str) or any(payload.get(k) is not None and not isinstance(payload[k],str)
            for k in ('office','city','person')):
        raise ValueError('总督府请求字段无效')
    if action=='management' and not isinstance(payload.get('payload'),dict):
        raise ValueError('机构履约请求格式无效')
    if not rules.enabled() and action not in {'resign','return','management'}:
        raise ValueError('修罗DLC停用，仅开放交接原责任')
    state=rules.court(game)
    if not state.get('joined'):raise ValueError('须先登记王庭身份')
    if state.get('court',{}).get('challenge'):raise ValueError('须先处理现有换位战书')
    if game.player.world!='asura' or game.map_journey or game.trial_site_state.get('active') or game.guixu_state.get('player_session'):
        raise ValueError('须在修罗界普通地图结束行程后办理')
    capital=game.player.location_id=='ten_thousand_battle_city'
    row=authority.records(game).get(payload.get('office'))
    if action in {'request','appoint'}:
        if not capital:raise ValueError('须亲临王庭取得任命')
        city=next((c for c in rules.cities(game) if c['id']==payload.get('city')),None)
        if not city or not rules.legal_city(game,city):raise ValueError('原城市没有有效王庭设府许可')
        person='player' if action=='request' else payload.get('person')
        if action=='appoint' and not rules.king(game):raise ValueError('只有修罗王可以任命他人')
        if person=='player':
            if rules.king(game):raise ValueError('在位修罗王须任命地方总督，不能兼任')
            from ..asura_court_finance import people, present
            from ...npc_custody import is_free
            sovereign=people(game).get(state['court']['holders'].get('5'))
            if not present(sovereign) or not is_free(sovereign):
                raise ValueError('现任修罗王缺席或受拘束，不能签发新的地方任命')
            cfg=rules.config()
            if state['rank']<cfg['required_rank'] or state['earned']<cfg['required_merit'] or state['regard']<cfg['required_regard']:
                raise ValueError('外任须战将以上、累计功绩100及恩宠20')
        else:
            from ...relationship_records import find_person
            from ...npc_custody import is_free
            npc=find_person(game,person) if isinstance(person,str) else None
            if (not npc or not is_free(npc) or npc.world!='asura' or npc.faction_id not in (None,COURT)
                    or npc.realm_index<9 or person in state['court']['offices'].values()
                    or person==state['court']['holders'].get('5')):
                raise ValueError('须选择自由在世且未兼任中枢官职的修罗廷臣')
            from ...person_assignments import research_assignment
            from ...spatial_people import instance_of
            if research_assignment(game,person) or instance_of(game,person):raise ValueError('此人已有任务或身处独立空间')
        identity='asura-prefecture:'+city['id']
        row=authority.records(game).get(identity)
        if row is None:
            row=authority.create(game,identity=identity,provider=rules.ID,name=city['name']+'总督府',world='asura',
                location=city['address']['location_id'],owner=dict(kind='sect',id=COURT),source=rules.SOURCE,
                building_id='office:'+identity,city_id=city['id'])
        authority.nominate(game,row,person,rules.config()['term_years'])
        return '外任已获准，须沿原地图赴任；没有移动人物、发放公款或建立建筑。'
    if not row or row['provider']!=rules.ID:raise ValueError('原总督府不存在')
    if action=='fund':
        if not rules.king(game) or not capital:raise ValueError('须由修罗王在王庭拨付原府库款')
        authority.fund(game,row,rules.SOURCE,payload.get('amount'))
    elif action=='revoke':
        if not rules.king(game) or not capital:raise ValueError('须由修罗王在王庭撤任')
        authority.revoke(game,row)
    else:
        require_place(game,row)
        if action=='assume':
            if not any(c['id']==row['city_id'] and rules.legal_city(game,c) for c in rules.cities(game)):
                raise ValueError('原城市或设府许可失效')
            authority.assume(game,row,'player',game.player.world,game.player.location_id)
        elif action=='resign':
            authority.relinquish(game,row,'player')
        elif action=='return':
            if not (authority.effective(game,row) or row['controller']=='player' or rules.king(game)):
                raise ValueError('只有原任交接人或君主可以上缴公款')
            authority.return_funds(game,row)
        else:
            if not authority.effective(game,row):raise ValueError('总督任职授权已失效，须先赴任或办理交接')
            if action=='donate':
                authority.fund(game,row,'player',payload.get('amount'))
            elif action=='build':
                if not any(c['id']==row['city_id'] and rules.legal_city(game,c) for c in rules.cities(game)):
                    raise ValueError('原城市或设府许可失效')
                target=rules.building(game,row) or rules.shell(row)
                quote=bill(game,row)
                if payload.get('quote')!=quote['token'] or payload.get('total')!=quote['total']:
                    raise ValueError('工程报价已变化，请重新勘验')
                if quote['reason']:raise ValueError(quote['reason'])
                market=game.economy_v2['markets'][row['world']+':'+row['location']]
                cargo,_=procurement.buy(game,market,quote['materials'],row['wallet'],party=rules.SOURCE)
                target=ensure_state(game)['records'].setdefault(row['building_id'],copy.deepcopy(target))
                rebuild(game,target,None,payer=row['wallet'],stock=cargo)
                authority.log(game,row,'原址府署营造完成，实付原市场工料与营造费用；产权归王庭。')
            elif action=='staff':
                if agenda(game,row['id']).get('job'):raise ValueError('须先完成或交接当前项目，再调整属员')
                person=payload.get('person')
                if person and person not in {p['id'] for p in rules.eligible_people(game,row)}:
                    raise ValueError('此人不在原址、已有任务或不具备属员资格')
                authority.clear_delegation(game,row)
                row['people']=[person] if person else []
                authority.log(game,row,'属员名册已调整；实际执行任务才按预算支付劳务。')
            elif action=='management':
                data=payload.get('payload',{})
                if data.get('scope')!=row['id']:raise ValueError('机构范围已变化')
                management.command(game,data)
            else:raise ValueError('未知总督府事务')
    return row['history'][-1]['text'] if row['history'] else '总督府事务已办理。'
