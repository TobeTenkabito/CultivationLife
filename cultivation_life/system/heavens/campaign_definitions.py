"""Finite, explicitly authorized military case; no generic invasion generator."""
from ...definition_data import definition as _content_definition
from .settlement_definitions import LABELS as SETTLEMENT_LABELS
CAMPAIGN_ID = _content_definition(__name__, "CAMPAIGN_ID")
SOURCE = _content_definition(__name__, "SOURCE")
DEFENDER = _content_definition(__name__, "DEFENDER")
DONOR = _content_definition(__name__, "DONOR")
SOURCE_WORLD, SOURCE_SITE = _content_definition(__name__, "SOURCE_WORLD_SOURCE_SITE")
TARGET_WORLD, TARGET_SITE = _content_definition(__name__, "TARGET_WORLD_TARGET_SITE")
REPORT_SITE = _content_definition(__name__, "REPORT_SITE")
BUILD_YEARS, LIFT_YEARS, EVAC_YEARS = _content_definition(__name__, "BUILD_YEARS_LIFT_YEARS_EVAC_YEARS")
MANDATE_YEARS, BUDGET, ANNUAL_COST = _content_definition(__name__, "MANDATE_YEARS_BUDGET_ANNUAL_COST")
INITIAL_SUPPLY, CARRIED_SUPPLY, BATCH = _content_definition(__name__, "INITIAL_SUPPLY_CARRIED_SUPPLY_BATCH")
AID_BUDGET, AID_COST = _content_definition(__name__, "AID_BUDGET_AID_COST")
DEFENSE_BUDGET = _content_definition(__name__, "DEFENSE_BUDGET")
ROUTE_ID = _content_definition(__name__, "ROUTE_ID")
EVAC_ROUTE = _content_definition(__name__, "EVAC_ROUTE")
AID_ROUTE = _content_definition(__name__, "AID_ROUTE")
LABELS = {'campaign_scout': '查勘界门工地', 'campaign_report': '呈交守备请求',
          'campaign_assault': '击退当地守卫', 'campaign_capture': '尝试擒拿守卫',
          'campaign_sabotage': '拆除目标端界门', 'campaign_aid': '申请灵界物资',
          'campaign_collect': '接收援助阵材', 'campaign_decline': '婉拒本次援助',
          'campaign_wait': '等候一年'}
LABELS.update(SETTLEMENT_LABELS)
DURATIONS = {key: 2 for key in LABELS}
DURATIONS.update(campaign_assault=1, campaign_capture=1, campaign_sabotage=4,
                 campaign_decline=0, campaign_wait=1)
CAMPAIGN_ACTIONS = frozenset(LABELS)
UNIT_PHASES = frozenset({'gathering', 'outbound', 'stationed', 'transport', 'returning', 'homeward', 'home', 'lost', 'held'})
TERMINAL_UNITS = frozenset({'home', 'lost'})
