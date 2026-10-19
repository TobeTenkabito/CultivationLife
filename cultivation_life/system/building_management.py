"""Local city facilities and on-demand annual operations, on original cash books."""
import hashlib
import json

from ..building_rules import config, ensure_state
from ..building_schema import address
from ..economy_content import BASE_PRICES, material_id
from ..models import HistoryRecord
from . import building_projects as projects
from .economy.ledger import balance, transfer_value


def usage(game,row):
    return game.building_state.get('city_business',{}).get(row['id'],{})


def facilities(row):
    return row.get('facilities',[])


def account_key(row):
    place=row['address']
    return f"operator:{place['world']}:{place['location_id']}"


def local_cash(game,row):
    return int(game.economy_v2.get('accounts',{}).get(account_key(row),{}).get('balance',0))


def quote(game,row,kind):
    cfg=config();grade=projects.grade(row['address']['world']);unit=BASE_PRICES[grade-1]
    reason=''
    materials={};receipt=0
    if kind in cfg['city_facilities']:
        spec=cfg['city_facilities'][kind]
        coins=unit*spec['labor_units']
        materials={material_id(row['address']['world'],grade,role):n for role,n in
            zip(('ore_structure','ore_conduct','ore_store'),spec['materials'])}
        if kind in facilities(row):reason='本城已经建有此设施'
        elif len(facilities(row))>=row['level']:reason='设施位已满；一级一处、二级两处、三级三处，扩建可解锁新位置'
    else:
        costs=cfg['city_operation'];coins=unit*row['level']*costs['cost_units' if kind=='settle' else 'aid_units']
        if kind=='settle':
            receipt=unit*row['level']*costs['receipt_units'][row['subtype']]
            if 'exchange' not in facilities(row):reason='须先建成市舶会馆'
            elif local_cash(game,row)<receipt:reason='当地原经营账户实款不足，不能垫付或凭空生息'
        elif kind=='aid':
            if row['level']>=3:reason='本城已达三级，无需再积累治理进度'
            elif row.get('development',0)>=cfg['city_development'][row['level']-1]:reason='治理进度已足，请先扩建'
            elif game.building_state.get('city_usage',{}).get(row['id'],{}).get('govern_year')==game.player.age:reason='本年已办理城务'
        else:raise ValueError('未知城务')
        used=usage(game,row)
        if 'last_year' not in used or game.player.age<=used['last_year']:reason='须先在城外度过一个真实年份；不补领离城期间的历年收益'
    if not projects.owns(game,row):reason='只有城主可以经营此城'
    elif row['status']!='intact' or row['address']!=address(game):reason='须亲临完好的原城办理'
    if not reason and (balance(game,'player')<coins or any(sum(i.quantity for i in game.player.inventory if i.id==key)<n for key,n in materials.items())):reason='灵石或设施工料不足'
    snapshot=dict(city=row,kind=kind,coins=coins,materials=materials,receipt=receipt,
        year=game.player.age,used=usage(game,row),cash=local_cash(game,row))
    token=hashlib.sha256(json.dumps(snapshot,sort_keys=True).encode()).hexdigest()[:20]
    return dict(coins=coins,materials=materials,receipt=receipt,reason=reason,token=token)


def option(identity,text,reason=''):
    return dict(id=identity,text=text,enabled=not reason,**({'disabled_reason':reason} if reason else {}))


def project(game,row,node):
    if not node.startswith('civic:'):return None
    if not projects.owns(game,row):return None
    cfg=config();title=row['name']+' · 城务'
    if node=='civic:main':
        names='、'.join(cfg['city_facilities'][k]['name'] for k in facilities(row)) or '尚未营造公共设施'
        used=usage(game,row);cash=local_cash(game,row)
        body=(f"{row['level']}级城池 · 公共设施 {len(facilities(row))}/{row['level']}\n{names}\n\n"
            f"原地方经营账户实款：{cash:,}灵石。此账户与当地营造、市场手续费共用，不是可任意提取的独立城库。\n"
            f"累计经办成本 {used.get('expense',0):,}，累计实收 {used.get('income',0):,}灵石。\n"
            '经营仅在本地核账时结算当年一笔；离开、读档、重建和跨界不补领年份。')
        choices=[option('civic:facilities','公共设施'),option('civic:settle','办理市集经营'),option('civic:aid','赈济街坊'),option('back','返回城中')]
    elif node=='civic:facilities':
        body='城池每级提供一处公共设施位置，已建设施不能反复拆建套取收益。城池毁坏后设施不再生效，重建时须重新营造。'
        choices=[option('civic:'+k,s['name']+(' · 已建' if k in facilities(row) else '')) for k,s in cfg['city_facilities'].items()]+[option('civic:main','返回城务')]
    else:
        kind=node.split(':')[1]
        if kind not in (*cfg['city_facilities'],'settle','aid'):return None
        bill=quote(game,row,kind)
        if kind in cfg['city_facilities']:body=cfg['city_facilities'][kind]['description']
        elif kind=='settle':body=f"商会提交当年经营分成。须支付人工与巡检开支，再从原地方经营账户实际支付{bill['receipt']:,}灵石。账户不足不结算，不补发往年收益。"
        else:body='拨付本年度街坊救济，治理进度增加一。本次与普通治理共用本城本年城务次数，也占用当年的经营机会；没有现金分成。'
        body+='\n\n'+projects.bill_text(bill)
        choices=[option('civic:commit:'+bill['token'],'确认经办',bill['reason']),option('civic:main','返回城务')]
    choices.append(option('leave','离开'+row['name']))
    return dict(title=title,body=body,choices=choices)


def act(game,row,choice):
    if choice=='civic:main':
        if not projects.owns(game,row):raise ValueError('只有城主可以经营此城')
        ensure_state(game).setdefault('city_business',{}).setdefault(row['id'],dict(last_year=game.player.age,expense=0,income=0))
    if not choice.startswith('civic:commit:'):return choice
    kind=game.building_state['scene']['node'].split(':')[1]
    bill=quote(game,row,kind)
    if choice!='civic:commit:'+bill['token']:raise ValueError('城务报价已经变化，请重新查看')
    projects.pay(game,bill,'城市公共设施' if kind in config()['city_facilities'] else '城市当年经营开支')
    original=projects.persist(game,row)
    counter=ensure_state(game).setdefault('city_business',{}).setdefault(row['id'],dict(last_year=game.player.age,expense=0,income=0))
    counter['expense']+=bill['coins']
    if kind in config()['city_facilities']:original.setdefault('facilities',[]).append(kind)
    else:
        counter['last_year']=game.player.age
        if bill['receipt']:
            transfer_value(game,account_key(row),'player',bill['receipt'],'城市市集当年经营分成')
            counter['income']+=bill['receipt']
        else:
            original['development']=original.get('development',0)+1
            ensure_state(game).setdefault('city_usage',{}).setdefault(row['id'],{})['govern_year']=game.player.age
    game.history.append(HistoryRecord('SYS_CITY_BUSINESS',1,game.player.age,'城市经营',kind,'completed',
        '在原地完成本次城务，钱款沿原地方经营账户交割。',dict(city_id=row['id'],cost=bill['coins'],receipt=bill['receipt']),['building','city']))
    return 'civic:main'
