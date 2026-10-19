"""Validate declarative settlements without loading runtime game state."""
import math


def validate(config,maps,profiles):
    def require(condition,message):
        if not condition:raise ValueError(message)
    require(isinstance(config,dict),'建筑配置缺失')
    for key in ('cave_prices','cave_bonus'):
        require(set(config.get(key,{}))=={'self','professional'},'洞府营造方式无效')
        for values in config[key].values():
            require(isinstance(values,list) and len(values)==3 and all(type(n) in (int,float) and math.isfinite(n) and n>0 for n in values),'洞府数值无效')
    require(config.get('city_arena_attempts')==3,'试场次数须与持久上限一致')
    require(config.get('city_development') and len(config['city_development'])==2 and all(type(n) is int and 1<=n<=12 for n in config['city_development']),'城市发展进度无效')
    for role in ('ore_structure','ore_conduct','ore_store'):
        values=config.get('city_materials',{}).get(role)
        require(isinstance(values,list) and len(values)==3 and all(type(n) is int and n>0 for n in values),'城市工料无效')
    require(config.get('city_material_grade')=={'1':1,'2':5,'3':9},'城市材料须使用原本界品阶')
    values=config.get('city_labor_units')
    require(isinstance(values,list) and len(values)==3 and all(type(n) is int and n>0 for n in values),'城市工费无效')
    for field in ('city_story_opportunity_fraction','city_arena_opportunity_fraction','war_destruction_chance'):
        n=config.get(field)
        require(type(n) in (int,float) and math.isfinite(n) and 0<=n<=1,'建筑概率或奖励比例无效')
    for category in ('cities','scenery'):
        require(isinstance(config.get(category),dict),'建筑目录缺失')
        for world,rows in config[category].items():
            require(world in profiles and profiles[world].get('tier',0)>0 and world in maps['worlds'],'建筑引用未知界面')
            require(isinstance(rows,list) and (len(rows)==2 if category=='cities' else len(rows)>0),'初始城市或景观数量无效')
            seen=set()
            locations={p['id'] for p in maps['worlds'][world]['locations']}
            for row in rows:
                require(isinstance(row,dict) and isinstance(row.get('id'),str) and row['id'] not in seen,'初始建筑编号重复或缺失')
                seen.add(row['id'])
                require(isinstance(row.get('name'),str) and 1<=len(row['name'])<=40 and row.get('location_id') in locations,'建筑名称或地点无效')
                if category=='scenery':
                    require(isinstance(row.get('description'),str) and bool(row['description']),'景色描述缺失')
                    continue
                require(row.get('subtype') in {'military','economic','comprehensive'} and row.get('population') in {'mortal','cultivator','mixed'},'城市属性无效')
                require(type(row.get('level')) is int and 1<=row['level']<=3,'城市规模无效')
                for field in ('flavor','audience','rumor','arena'):
                    require(isinstance(row.get(field),str) and bool(row[field]),'城市专有描述缺失')
                story=row.get('story',{})
                require(isinstance(story,dict) and isinstance(story.get('title'),str) and isinstance(story.get('body'),str),'城市专有事件缺失')
                choices=story.get('choices')
                require(isinstance(choices,list) and len(choices)==2 and all(isinstance(c,list) and len(c)==2 and all(isinstance(t,str) and t for t in c) for c in choices),'城市事件分支无效')
