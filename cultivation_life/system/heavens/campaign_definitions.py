"""Finite, explicitly authorized military case; no generic invasion generator."""
CAMPAIGN_ID = 'lanjiang_gate'
SOURCE = 'blood_prison'
DEFENDER = 'tianjian'
DONOR = 'taixuan'
SOURCE_WORLD, SOURCE_SITE = 'demon', 'red_marrow_city'
TARGET_WORLD, TARGET_SITE = 'human', 'lanjiang_steppe'
REPORT_SITE = 'wudi_plain'
BUILD_YEARS, LIFT_YEARS, EVAC_YEARS = 40, 16, 8
MANDATE_YEARS, BUDGET, ANNUAL_COST = 600, 90000, 100
INITIAL_SUPPLY, CARRIED_SUPPLY, BATCH = 120, 36, 24
AID_BUDGET, AID_COST = 12000, 500
DEFENSE_BUDGET = 30000
ROUTE_ID = 'military:demon:human:lanjiang'
EVAC_ROUTE = 'evacuation:human:demon:lanjiang'
AID_ROUTE = 'aid:spirit:human:wudi'
LABELS = {'campaign_scout': '查勘界门工地', 'campaign_report': '呈交守备请求',
          'campaign_assault': '击退当地守卫', 'campaign_capture': '尝试擒拿守卫',
          'campaign_sabotage': '拆除目标端界门', 'campaign_aid': '申请灵界物资',
          'campaign_collect': '接收援助阵材', 'campaign_decline': '婉拒本次援助',
          'campaign_wait': '等候一年'}
DURATIONS = {key: 2 for key in LABELS}
DURATIONS.update(campaign_assault=1, campaign_capture=1, campaign_sabotage=4,
                 campaign_decline=0, campaign_wait=1)
CAMPAIGN_ACTIONS = frozenset(LABELS)
UNIT_PHASES = frozenset({'gathering', 'outbound', 'stationed', 'transport', 'returning', 'homeward', 'home', 'lost', 'held'})
TERMINAL_UNITS = frozenset({'home', 'lost'})
