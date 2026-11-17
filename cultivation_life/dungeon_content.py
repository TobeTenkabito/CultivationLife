"""Validate explicit local generation profiles without importing gameplay modules."""
from .dungeon_schema import WORLD_IDS, integer, finite


def validate(settings,maps):
    if not isinstance(settings,dict) or settings.get('version')!=1:raise ValueError('副本配置版本无效')
    if set(settings['ceilings'])!=WORLD_IDS or set(settings['legendary_limit'])!=WORLD_IDS:raise ValueError('副本界面配置不完整')
    for world in WORLD_IDS:
        integer(settings['ceilings'][world],1,12);integer(settings['legendary_limit'][world],0,99)
        for location in maps.get(world,{}).get('locations',[]):
            if world+':'+location['id'] not in settings['profiles']:raise ValueError('地图缺少副本生成配置：'+world+':'+location['id'])
    for key,profile in settings['profiles'].items():
        world=key.split(':',1)[0]
        if world not in WORLD_IDS:raise ValueError('副本配置包含未知界面')
        integer(profile['realm'],1,settings['ceilings'][world]);integer(profile['cap'],profile['realm'],settings['ceilings'][world])
        integer(profile['slots'],1,20);integer(profile['nodes'],4,32)
        if profile['theme'] not in {'water','mountain','fire','frost','fort','shadow','grove','ruins'}:raise ValueError('副本地图主题无效')
        if len(profile['weights'])!=4:raise ValueError('副本品质概率配置无效')
        for weight in profile['weights']:finite(weight,0,10000)
        if sum(profile['weights'][:-1])<=0:raise ValueError('传奇次数用尽后必须仍有有效品质')
    finite(settings['legendary_fusion_chance'],0,1);finite(settings['invitation_chance'],0,1)
    integer(settings['max_team'],2,8)
    if set(settings['growth_action_units'])!={'ordinary','rare','epic'}:raise ValueError('副本灵药预算配置无效')
    for value in settings['growth_action_units'].values():finite(value,0,10)
