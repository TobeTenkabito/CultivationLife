"""Bounded civilian development commands; no military authorization."""
LABELS = {
    'outpost_develop': '开办地方经营', 'outpost_invest': '向驻地注资',
    'outpost_buy_materials': '采购开拓资材', 'outpost_expand': '派人联络地方',
    'outpost_build_site': '派人建设外驻点', 'outpost_spar': '派人论道争取支持',
    'outpost_policy': '调整地方政策', 'outpost_retract': '撤去当地影响',
    'outpost_cancel_local': '结束地方行程并返回驻地', 'outpost_export': '运款返回总部',
}
OPTIONS = {key: set() for key in LABELS}
OPTIONS.update(outpost_buy_materials={'quote_id'}, outpost_expand={'person_id', 'location_id'},
    outpost_build_site={'person_id', 'location_id'}, outpost_spar={'person_id', 'location_id', 'rival_id'},
    outpost_policy={'location_id', 'policy'}, outpost_retract={'location_id'},
    outpost_cancel_local={'person_id'}, outpost_export={'person_id'})
JOBS = {'outpost_expand': ('expand_influence', 5, 1000),
        'outpost_build_site': ('build_outpost', 10, 10000),
        'outpost_spar': ('territory_spar', 5, 1000)}
LOCAL_PHASES = {'local_outbound', 'local_work', 'local_return'}
MAX_CLAIMS = 8
