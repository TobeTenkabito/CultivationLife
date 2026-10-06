"""Pure validation of the bounded M3 expedition and its public evidence."""
from .frontier_definitions import (FRONTIER_ID, FRONTIER_ACTIONS, DURATIONS, PHASES, ROUTE,
                                   SOURCE_FACTION, INITIAL_RESERVE, ANNUAL_COST, SCOUT_YEARS, MANDATE_YEARS)


def counter(value):
    if type(value) is not int or value < 0:
        raise ValueError('边情计数必须为非负整数')


def validate_frontier(row, runtime):
    keys = {'id', 'revision', 'created_at', 'last_year', 'status', 'phase', 'progress', 'duration',
            'person_id', 'home', 'road', 'road_years', 'authorization', 'budget', 'source_evidence',
            'withdrawal', 'reason', 'observed', 'reported', 'reports'}
    if type(row) is not dict or set(row) != keys or row['id'] != FRONTIER_ID or type(row['revision']) is not int or row['revision'] != 1:
        raise ValueError('边情字段或定义版本无效')
    for key in ('created_at', 'last_year', 'progress', 'duration', 'road_years'):
        counter(row[key])
    if not row['created_at'] <= row['last_year'] <= runtime['processed_years']:
        raise ValueError('边情时钟与实际年度不符')
    if row['status'] not in {'inquiry', 'active', 'completed', 'declined', 'cancelled', 'failed'} or row['phase'] not in PHASES:
        raise ValueError('边情阶段无效')
    terminal = row['status'] not in {'inquiry', 'active'}
    if (terminal != (row['phase'] == 'closed') or (row['status'] == 'inquiry') != (row['phase'] == 'inquiry')
            or not 0 <= row['progress'] <= row['duration']):
        raise ValueError('边情阶段与进度不符')
    duration = {'inquiry': 0, 'review': 0, 'closed': 0, 'gathering': row['road_years'], 'homeward': row['road_years'],
                'outbound': ROUTE.crossing_years, 'returning': ROUTE.crossing_years, 'scouting': SCOUT_YEARS, 'reply': 2}[row['phase']]
    if row['duration'] != duration or row['phase'] in {'gathering', 'homeward'} and duration < 1:
        raise ValueError('边情工期不符')
    if any(type(row[k]) is not bool for k in ('withdrawal', 'observed', 'reported')) or row['reported'] and not row['observed']:
        raise ValueError('边情认识来源无效')
    if row['reason'] is not None and (not isinstance(row['reason'], str) or len(row['reason']) > 500):
        raise ValueError('边情中止原因无效')
    budget = row['budget']
    if type(budget) is not dict or set(budget) != {'owner', 'total', 'spent', 'refunded'} or budget['owner'] != SOURCE_FACTION:
        raise ValueError('先遣储备所有者无效')
    for key in ('total', 'spent', 'refunded'):
        counter(budget[key])
    if (budget['total'] != INITIAL_RESERVE or budget['spent'] % ANNUAL_COST
            or budget['spent']+budget['refunded'] > budget['total']
            or budget['refunded'] != (INITIAL_RESERVE-budget['spent'] if terminal else 0)):
        raise ValueError('先遣预算不守恒')
    evidence = row['source_evidence']
    if evidence is not None:
        if (type(evidence) is not dict or set(evidence) != {'source', 'world', 'location', 'sent_at'}
                or (evidence['source'], evidence['world'], evidence['location']) != ('causal_ruins', 'human', 'wudi_plain')):
            raise ValueError('先遣来源证据无效')
        counter(evidence['sent_at'])
        if not row['created_at']+2 <= evidence['sent_at'] <= runtime['processed_years']:
            raise ValueError('问讯尚未实际递送')
    if row['status'] == 'active' and evidence is None:
        raise ValueError('未获来源证据不能派遣')
    ruins = runtime.get('ruins', {})
    if (not ruins.get('contact_known') or 'ruins_contact' not in ruins.get('sent_records', {})
            or ruins['sent_records']['ruins_contact']['sent_at'] > row['created_at']):
        raise ValueError('边情缺少原有阵眼接触记录')
    authorization = row['authorization']
    if row['person_id'] is not None:
        if not isinstance(row['person_id'], str) or not row['person_id'] or not isinstance(row['home'], str) or not row['home']:
            raise ValueError('先遣人物或原驻地无效')
        if (type(row['road']) is not list or not row['road'] or len(row['road']) > 100
                or any(not isinstance(n, str) or not n for n in row['road'])
                or row['road'][0] != row['home'] or row['road'][-1] != ROUTE.source_location):
            raise ValueError('先遣集结道路无效')
        if type(authorization) is not dict or set(authorization) != {'faction_id', 'issuer_id', 'scope', 'source', 'granted_at', 'expires_at', 'route_id', 'capacity', 'purpose'}:
            raise ValueError('先遣缺少具名授权')
        if (authorization['faction_id'] != SOURCE_FACTION or authorization['scope'] != 'recon_only'
                or authorization['source'] not in {'existing_office', 'native_sect_leadership'}
                or authorization['route_id'] != ROUTE.id or type(authorization['capacity']) is not int or authorization['capacity'] != 1
                or authorization['purpose'] != 'inspect_linked_ward' or not isinstance(authorization['issuer_id'], str)
                or not authorization['issuer_id'] or authorization['issuer_id'] in {'player', row['person_id']} or evidence is None):
            raise ValueError('先遣授权越权或范围无效')
        for key in ('granted_at', 'expires_at'):
            counter(authorization[key])
        if not evidence['sent_at'] < authorization['granted_at'] <= runtime['processed_years'] or authorization['expires_at'] != authorization['granted_at']+MANDATE_YEARS:
            raise ValueError('先遣授权时间无效')
    elif authorization is not None or row['home'] is not None or row['road'] or row['road_years'] or budget['spent']:
        raise ValueError('无先遣人物不能保存部署与支出')
    elif row['phase'] not in {'inquiry', 'review', 'reply', 'closed'}:
        raise ValueError('行军缺少真实人物')
    if authorization and (budget['spent'] > ANNUAL_COST*(row['last_year']-authorization['granted_at'])
            or row['phase'] not in {'closed', 'reply'} and row['progress']*ANNUAL_COST > budget['spent']):
        raise ValueError('先遣工时与实际年度支出不一致')
    if type(row['reports']) is not list or len(row['reports']) > 6:
        raise ValueError('边情报告超限')
    kinds = set()
    for report in row['reports']:
        if type(report) is not dict or set(report) != {'kind', 'year', 'text'}:
            raise ValueError('边情报告字段无效')
        kind = report['kind']
        if kind not in {'inquiry', 'sighting', 'identity', 'reported', 'agreement', 'reply'} or kind in kinds:
            raise ValueError('边情报告重复或来源无效')
        kinds.add(kind)
        counter(report['year'])
        if not row['created_at'] <= report['year'] <= runtime['processed_years'] or not isinstance(report['text'], str) or not 0 < len(report['text']) <= 1000:
            raise ValueError('边情报告年代或内容无效')
    if row['observed'] != ('identity' in kinds) or row['reported'] != ('reported' in kinds):
        raise ValueError('边情认识与亲历报告不一致')


def validate_frontier_task(task, row):
    for key in ('progress', 'duration', 'cycle'):
        counter(task[key])
    if (task['action'] not in FRONTIER_ACTIONS or task['duration'] != DURATIONS[task['action']]
            or task['cycle'] != 0 or task['person_id'] is not None
            or task['escrow'] != dict(total=0, spent=0, refunded=0, material=None, mp_paid=0)
            or task['status'] == 'completed' and task['progress'] != task['duration']):
        raise ValueError('边情亲自任务或费用无效')
    if task['status'] == 'completed':
        if (task['action'] == 'frontier_inquire' and row['source_evidence'] is None
                or task['action'] == 'frontier_scout' and not row['observed']
                or task['action'] == 'frontier_report' and not row['reported']
                or task['action'] == 'frontier_parley' and not any(r['kind'] == 'agreement' for r in row['reports'])):
            raise ValueError('边情任务完成事实不一致')
