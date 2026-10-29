"""First organizational frontier: explicit, civilian, reversible tier-one lanes."""
import re
from .development_definitions import LABELS as DEVELOPMENT_LABELS, OPTIONS as DEVELOPMENT_OPTIONS, LOCAL_PHASES

OUTPOST_ID = 'outpost_network'
ENDPOINTS = {'human': 'wudi_plain', 'demon': 'red_marrow_city'}
WORLD_NAMES = {'human': '人界', 'demon': '魔界'}
SITE_NAMES = {'human': '无棣原', 'demon': '赤髓城'}
CROSSING_YEARS = 8
BUILD_YEARS = 10
BUILD_COST = 10000
WORKING_CASH = 10000
ANNUAL_COST = 100
MAX_UNITS = 3
LABELS = {
    'outpost_authorize': '批准跨界开拓', 'outpost_dispatch': '派驻施工门人',
    'outpost_supply': '派遣补给使者', 'outpost_appoint': '任命驻地负责人',
    'outpost_recall': '召回驻守门人', 'outpost_suspend': '暂停驻地经营',
    'outpost_activate': '恢复驻地经营', 'outpost_withdraw': '撤销驻地并撤回',
    'outpost_depart': '亲赴异界驻地', 'outpost_return': '循开拓路线返程',
    'outpost_wait': '推进一年开拓行程',
}
ACTIONS = frozenset(LABELS)
TIMED_ACTIONS = frozenset({'outpost_depart', 'outpost_return', 'outpost_wait'})
OPTIONS = {action: ({'person_id'} if action in {
    'outpost_dispatch', 'outpost_supply', 'outpost_appoint', 'outpost_recall'} else set()) for action in ACTIONS}
PHASES = {'gathering', 'outbound', 'stationed', 'returning', 'homeward', 'home', 'lost'}
LABELS.update(DEVELOPMENT_LABELS)
OPTIONS.update(DEVELOPMENT_OPTIONS)
ACTIONS = frozenset(LABELS)
PHASES |= LOCAL_PHASES


def target(owner_id):
    return 'outpost:' + owner_id


def is_target(value):
    return isinstance(value, str) and re.fullmatch(r'outpost:[\w-]{1,100}', value) is not None


def route_id(source, destination):
    return f'expedition:{source}:{destination}'
