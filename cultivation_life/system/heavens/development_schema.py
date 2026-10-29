"""Pure optional state contract for regional development and original workers."""
from .development_definitions import JOBS, LOCAL_PHASES, MAX_CLAIMS
from .outpost_definitions import ENDPOINTS
from .outpost_routes import profile


def counter(value):
    if type(value) is not int or value < 0:
        raise ValueError('地方经营数量和年份无效')


def validate_development(value):
    keys = {'version', 'started_at', 'claims', 'income', 'expense', 'counter_decade'}
    if type(value) is not dict or set(value) != keys or type(value['version']) is not int or value['version'] != 1:
        raise ValueError('地方经营字段或版本无效')
    for key in keys - {'claims'}:
        counter(value[key])
    if type(value['claims']) is not dict or len(value['claims']) > MAX_CLAIMS:
        raise ValueError('地方经营地区超出容量')
    for location, year in value['claims'].items():
        if not isinstance(location, str) or not location:
            raise ValueError('地方经营地址无效')
        counter(year)
        if year < value['started_at']:
            raise ValueError('地方经营不能早于开办年份')


def validate_job(unit, row, stock_validator):
    job = unit.get('local_job')
    if job is None:
        if unit['phase'] in LOCAL_PHASES:
            raise ValueError('地方行程缺少原任务')
        return
    keys = {'action', 'location_id', 'rival_id', 'out_route', 'return_route', 'out_years', 'return_years',
            'wallet', 'stock', 'fee_spent', 'started_at', 'cancel_requested', 'installed', 'status', 'result'}
    if type(job) is not dict or set(job) != keys or job['action'] not in JOBS or 'development' not in row:
        raise ValueError('地方行程字段无效')
    if unit['courier'] or type(job['installed']) is not bool or type(job['cancel_requested']) is not bool:
        raise ValueError('地方行程人员或投入状态无效')
    if job['status'] not in {'active', 'done', 'cancelled', 'lost'} or (job['status'] == 'active') != (unit['phase'] in LOCAL_PHASES):
        raise ValueError('地方行程阶段不一致')
    for key in ('out_years', 'return_years', 'fee_spent', 'started_at'):
        counter(job[key])
    if job['fee_spent'] > JOBS[job['action']][2]*profile(row['source'])['scale'] or not isinstance(job['wallet'], str):
        raise ValueError('地方行程费用无效')
    if not isinstance(job['location_id'], str) or not isinstance(job['rival_id'], str):
        raise ValueError('地方行程地点或对手无效')
    for field in ('out_route', 'return_route'):
        route = job[field]
        if type(route) is not list or not route or any(not isinstance(loc, str) or not loc for loc in route):
            raise ValueError('地方行程道路无效')
    stock_validator(job['stock'], row['source'], row['destination'])
    main, location = ENDPOINTS[row['destination']], job['location_id']
    if (job['out_route'][0] != main or job['out_route'][-1] != location
            or job['return_route'][0] != location or job['return_route'][-1] != main):
        raise ValueError('地方行程起讫地址无效')
    durations = {'local_outbound': {job['out_years']}, 'local_return': {0, job['return_years']}}
    if unit['phase'] in durations and unit['duration'] not in durations[unit['phase']]:
        raise ValueError('地方行程道路工期无效')
    if job['status'] != 'active' and job['stock']:
        raise ValueError('已结束的地方行程不能保留在途货物')
    if job['result'] not in {None, 'expanded', 'built', 'won', 'lost', 'cancelled'}:
        raise ValueError('地方行程结果无效')
    if unit['phase'] == 'local_work' and unit['duration'] != JOBS[job['action']][1]:
        raise ValueError('地方行程工期无效')
