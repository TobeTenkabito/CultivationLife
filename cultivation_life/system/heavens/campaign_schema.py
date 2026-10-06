"""Pure save contract for one bounded campaign and its exclusive assets."""
from .campaign_definitions import (CAMPAIGN_ID, SOURCE, DEFENDER, DONOR, TARGET_SITE, REPORT_SITE,
    SOURCE_SITE, BUILD_YEARS, BUDGET, MANDATE_YEARS, INITIAL_SUPPLY, ANNUAL_COST, UNIT_PHASES,
    ROUTE_ID, EVAC_ROUTE, AID_ROUTE, AID_BUDGET, AID_COST, DEFENSE_BUDGET, DURATIONS, CAMPAIGN_ACTIONS)
from .settlement_schema import validate_settlement


def counter(value):
    if type(value) is not int or value < 0:
        raise ValueError('军事计数必须为非负整数')


def choice(value, options):
    if not isinstance(value, str) or value not in options:
        raise ValueError('军事枚举值无效')


def text(value):
    if not isinstance(value, str) or not value or len(value) > 1500:
        raise ValueError('军事文字或引用无效')


def mandate(value, faction, scope, route, now):
    keys = {'faction_id','issuer_id','scope','source','granted_at','expires_at','route_id','capacity','location'}
    if type(value) is not dict or set(value) != keys:
        raise ValueError('军事批准字段无效')
    text(value['issuer_id'])
    choice(value['source'], {'existing_office','native_sect_leadership'})
    for key in ('granted_at','expires_at'):
        counter(value[key])
    if (value['faction_id'] != faction or value['scope'] != scope or value['route_id'] != route
            or value['issuer_id'] == 'player' or type(value['capacity']) is not int or value['capacity'] != 1
            or value['location'] != (REPORT_SITE if route == AID_ROUTE else TARGET_SITE)
            or value['granted_at'] > now or value['expires_at'] != value['granted_at']+MANDATE_YEARS):
        raise ValueError('军事批准越界或时间无效')


def material(item, world):
    if type(item) is not dict or set(item) != {'id','material_id','name','source','origin_world','acquired_tier','base_value'}:
        raise ValueError('军事阵材不是实际标准实例')
    for key in ('id','material_id','name','source'):
        text(item[key])
    if item['origin_world'] != world or item['acquired_tier'] != (6 if world == 'spirit' else 4):
        raise ValueError('军事阵材来源或品阶无效')


def validate_campaign(row, runtime):
    keys = {'id','revision','created_at','last_year','status','authorization','evacuation_route','evidence','motive',
            'units','budget','materials','gate','supply','shipment','deliveries','defense','defense_requested',
            'aid','known','surveyed','warning_at','warning_received','reports','battles','last_battle','reason'}
    if type(row) is not dict or set(row)-{'settlement'} != keys or row['id'] != CAMPAIGN_ID or type(row['revision']) is not int or row['revision'] != 1:
        raise ValueError('军事案例字段或版本无效')
    for key in ('created_at','last_year','deliveries','last_battle'):
        counter(row[key])
    now = runtime['processed_years']
    if not row['created_at'] <= row['last_year'] <= now or row['last_battle'] > now:
        raise ValueError('军事日历超出实际年度')
    choice(row['status'], {'active','withdrawing','withdrawn','failed'})
    for key in ('known','surveyed','warning_received','defense_requested'):
        if type(row[key]) is not bool:
            raise ValueError('军情认识标志无效')
    if row['reason'] is not None:
        text(row['reason'])
    if row['warning_at'] is not None:
        counter(row['warning_at'])
        if row['warning_at'] > now+2:
            raise ValueError('施工预警未实际发出')
    recon = runtime.get('frontier')
    evidence = row['evidence']
    if (not recon or recon['status'] != 'completed' or recon['withdrawal']
            or not recon.get('landing_evidence') or evidence != recon['landing_evidence']
            or row['motive'] != 'recover_linked_ward' or row['evacuation_route'] != EVAC_ROUTE):
        raise ValueError('军事建设缺少实际回传的落点证据')
    mandate(row['authorization'], SOURCE, 'build_and_supply', ROUTE_ID, now)
    budget = row['budget']
    if type(budget) is not dict or set(budget) != {'owner','total','spent','refunded'} or budget['owner'] != SOURCE or budget['total'] != BUDGET:
        raise ValueError('军事储备来源无效')
    for key in ('total','spent','refunded'):
        counter(budget[key])
    if budget['spent'] % ANNUAL_COST or budget['spent']+budget['refunded'] > BUDGET or budget['refunded'] != (BUDGET-budget['spent'] if row['status'] in {'withdrawn','failed'} else 0):
        raise ValueError('军事预算不守恒')
    if type(row['units']) is not list or not 3 <= len(row['units']) <= 4:
        raise ValueError('军事编制超限')
    identities, roles = set(), set()
    for unit in row['units']:
        if type(unit) is not dict or set(unit) != {'person_id','faction_id','role','home','road','road_years','phase','duration','progress','observed','reason'}:
            raise ValueError('军事人员字段无效')
        for key in ('person_id','home'):
            text(unit[key])
        choice(unit['role'], {'builder','keeper','soldier','defender'})
        choice(unit['phase'], UNIT_PHASES)
        if unit['person_id'] in identities or unit['role'] in roles or unit['faction_id'] != (DEFENDER if unit['role'] == 'defender' else SOURCE):
            raise ValueError('军事人物重复或归属错误')
        identities.add(unit['person_id']); roles.add(unit['role'])
        for key in ('road_years','duration','progress'):
            counter(unit[key])
        if (not unit['road_years'] or not 0 <= unit['progress'] <= unit['duration']
                or type(unit['road']) is not list or not 1 <= len(unit['road']) <= 100
                or any(not isinstance(v,str) or not v for v in unit['road'])
                or unit['road'][0] != unit['home'] or unit['road'][-1] != (TARGET_SITE if unit['role'] == 'defender' else SOURCE_SITE)):
            raise ValueError('军事道路或行程进度无效')
        expected = unit['road_years'] if unit['phase'] in {'gathering','homeward'} else 8 if unit['phase'] in {'outbound','returning'} else 16 if unit['phase'] == 'transport' else 0
        if unit['duration'] != expected or type(unit['observed']) is not bool:
            raise ValueError('军事行程工期无效')
        if unit['reason'] is not None:
            text(unit['reason'])
    if not {'builder','keeper','soldier'} <= roles or row['authorization']['issuer_id'] in identities:
        raise ValueError('军事编制缺失或批准者被重复部署')
    gate = row['gate']
    if type(gate) is not dict or set(gate) != {'state','source_progress','target_progress','stability','repair_progress'}:
        raise ValueError('界门字段无效')
    choice(gate['state'], {'planned','building','open','interrupted','destroyed'})
    for key, maximum in [('source_progress',BUILD_YEARS),('target_progress',BUILD_YEARS),('stability',100),('repair_progress',4)]:
        counter(gate[key])
        if gate[key] > maximum:
            raise ValueError('界门进度或稳定性超限')
    if gate['state'] == 'open' and (min(gate['source_progress'],gate['target_progress']) != BUILD_YEARS or gate['stability'] < 50):
        raise ValueError('未完成两端施工不能开放军事输送')
    if type(row['materials']) is not dict or set(row['materials']) != {'source','target','reserve'}:
        raise ValueError('界门阵材储备无效')
    item_ids = set()
    for key, asset in row['materials'].items():
        if type(asset) is not dict or set(asset) != {'item','owner'}:
            raise ValueError('军事阵材物权字段无效')
        material(asset['item'],'demon')
        choice(asset['owner'], {'source_depot','carrier','target_depot','source_gate','target_gate','spent','lost'})
        if asset['item']['id'] in item_ids:
            raise ValueError('军事阵材重复')
        item_ids.add(asset['item']['id'])
    if gate['state'] == 'open' and any(row['materials'][key]['owner'] != key+'_gate' for key in ('source','target')):
        raise ValueError('稳定界门缺少已安装的真实阵材')
    supply = row['supply']
    if type(supply) is not dict or set(supply) != {'source','carried','target','spent','lost'}:
        raise ValueError('军事补给字段无效')
    for value in supply.values():
        counter(value)
    shipment = row['shipment']
    if shipment is not None:
        if type(shipment) is not dict or set(shipment) != {'kind','person_id','quantity','progress','duration'}:
            raise ValueError('军事输送字段无效')
        choice(shipment['kind'], {'troop','supply'})
        for key in ('quantity','progress','duration'):
            counter(shipment[key])
        if shipment['duration'] != 16 or not 0 <= shipment['progress'] < 16:
            raise ValueError('军事运输工期无效')
        if shipment['kind'] == 'troop':
            if shipment['quantity'] or shipment['person_id'] not in identities:
                raise ValueError('军事运输缺少真实人物')
        elif shipment['person_id'] is not None or shipment['quantity'] != 24:
            raise ValueError('军事物资运载量无效')
    if sum(supply.values()) + (shipment['quantity'] if shipment else 0) != INITIAL_SUPPLY:
        raise ValueError('军事补给不守恒')
    defense = row['defense']
    if defense is not None:
        if type(defense) is not dict or set(defense) != {'status','authorization','budget'}:
            raise ValueError('守备批准字段无效')
        choice(defense['status'], {'approved','declined'})
        ledger = defense['budget']
        if type(ledger) is not dict or set(ledger) != {'owner','total','spent','refunded'} or ledger['owner'] != DEFENDER or ledger['total'] != DEFENSE_BUDGET:
            raise ValueError('守备储备归属无效')
        for key in ('spent','refunded'):
            counter(ledger[key])
        finished = defense['status'] == 'declined' or any(u['role'] == 'defender' and u['phase'] in {'home','lost'} for u in row['units'])
        if ledger['spent']+ledger['refunded'] > DEFENSE_BUDGET or ledger['refunded'] != (DEFENSE_BUDGET-ledger['spent'] if finished else 0):
            raise ValueError('守备储备不守恒')
        if defense['status'] == 'approved':
            mandate(defense['authorization'],DEFENDER,'guard_lanjiang','road:human:lanjiang',now)
            if 'defender' not in roles:
                raise ValueError('守备批准缺少实际门人')
        elif defense['authorization'] is not None or 'defender' in roles:
            raise ValueError('未批准的守军不能出现')
    elif 'defender' in roles:
        raise ValueError('守军缺少独立授权')
    aid = row['aid']
    if aid is not None:
        if type(aid) is not dict or set(aid) != {'status','authorization','material','progress','duration','spent','refunded','owner','last_year','notice_progress','notice_delivered'}:
            raise ValueError('灵界援助字段无效')
        choice(aid['status'], {'transit','arrived','claimed','declined','cancelled'})
        owners = {'transit':'shipment','arrived':'wudi_depot','claimed':'player','declined':'donor','cancelled':'donor'}
        for key in ('progress','duration','spent','refunded','last_year'):
            counter(aid[key])
        counter(aid['notice_progress'])
        if (aid['notice_progress'] > 16 or type(aid['notice_delivered']) is not bool
                or aid['notice_delivered'] and (aid['status'] != 'cancelled' or aid['notice_progress'] != 16)):
            raise ValueError('援助撤销回函未实际送达')
        if (aid['owner'] != owners[aid['status']] or aid['duration'] != 16 or aid['progress'] > 16
                or aid['spent'] != aid['progress']*AID_COST or aid['last_year'] > now
                or aid['refunded'] != (0 if aid['status'] == 'transit' else AID_BUDGET-aid['spent'])):
            raise ValueError('援助物权、工时或预算不守恒')
        if aid['status'] in {'arrived','claimed'} and aid['progress'] != 16:
            raise ValueError('援助尚未实际抵达')
        if aid['authorization']:
            mandate(aid['authorization'],DONOR,'one_material_aid',AID_ROUTE,now)
            material(aid['material'],'spirit')
        elif aid['status'] != 'declined' or aid['material'] is not None or aid['progress']:
            raise ValueError('援助缺少合法批准')
    if type(row['reports']) is not list or len(row['reports']) > 24 or type(row['battles']) is not list or len(row['battles']) > 6:
        raise ValueError('军情或交战记录超限')
    for item in row['reports']:
        if type(item) is not dict or set(item) != {'kind','text','year'}:
            raise ValueError('军情记录字段无效')
        text(item['kind']); text(item['text']); counter(item['year'])
        if not row['created_at'] <= item['year'] <= now:
            raise ValueError('军情报告年代无效')
    for battle in row['battles']:
        if type(battle) is not dict or set(battle) != {'year','attacker','defender','outcome'}:
            raise ValueError('局部交战字段无效')
        choice(battle['outcome'], {'victory','defeat','stalemate'})
        counter(battle['year'])
        if not row['created_at'] <= battle['year'] <= now or battle['attacker'] not in identities or battle['defender'] not in identities:
            raise ValueError('局部交战缺少实际人物或年份')
    if 'settlement' in row:
        validate_settlement(row['settlement'], row, now)


def validate_campaign_task(task, row):
    duration_valid = (type(task['duration']) is int and 1 <= task['duration'] <= 1000) if task['action'] == 'campaign_evacuate' else task['duration'] == DURATIONS.get(task['action'])
    if (task['action'] not in CAMPAIGN_ACTIONS or not duration_valid
            or task['cycle'] != 0 or task['escrow'] != dict(total=0,spent=0,refunded=0,material=None,mp_paid=0)):
        raise ValueError('军事个人任务费用或工期无效')
    if task['status'] == 'completed':
        if (task['progress'] != task['duration']
                or task['action'] == 'campaign_scout' and not row['surveyed']
                or task['action'] == 'campaign_report' and not row['defense_requested']
                or task['action'] == 'campaign_sabotage' and row['gate']['state'] != 'destroyed'
                or task['action'] == 'campaign_aid' and row['aid'] is None
                or task['action'] == 'campaign_collect' and (not row['aid'] or row['aid']['status'] != 'claimed')):
            raise ValueError('军事个人任务完成事实无效')
        state = row.get('settlement', {})
        if (task['action'] in {'campaign_truce', 'campaign_vassal', 'campaign_withdrawal'}
                and (state.get('treaty') or {}).get('kind') != task['action'].removeprefix('campaign_')
                or task['action'] == 'campaign_relief' and task['person_id'] not in state.get('treated', [])):
            raise ValueError('战后任务缺少实际协议或救护事实')
    if task['action'] in {'campaign_assault','campaign_capture'}:
        if task['person_id'] not in {u['person_id'] for u in row['units'] if u['faction_id'] == SOURCE}:
            raise ValueError('军事交锋引用无效')
    elif task['action'] in {'campaign_relief', 'campaign_release'}:
        if task['person_id'] not in {u['person_id'] for u in row['units']}:
            raise ValueError('救护缺少原人物引用')
    elif task['person_id'] is not None:
        raise ValueError('非交锋任务不能引用对手')
