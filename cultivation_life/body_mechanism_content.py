"""Pure validation of optional high-body content and personal cultivation records."""
from .system.combat.body_mechanisms import BodyMechanism,validate_mechanisms

AGGREGATES=('se','shou','xiang','xing','shi')


def build(row,rank):
    return BodyMechanism(row['id'],row['name'],
        {k:v['base']+v['growth']*rank for k,v in row['effects'].items()},row['priority'],
        row['chance']['base']+row['chance']['growth']*rank,tuple(row['requires']),rank)


def validate_config(config):
    if 'five_aggregates' not in config:return
    rows=config['five_aggregates']
    if config.get('body_max_level')!=50 or not isinstance(rows,list) or tuple(r['id'] for r in rows)!=AGGREGATES:
        raise ValueError('Five aggregates require a fifty-layer body and five ordered mechanisms')
    if [r['unlock_level'] for r in rows]!=[10,20,30,40,50]:raise ValueError('Invalid aggregate unlocks')
    for row in rows:
        if not isinstance(row.get('effects'),dict) or not row['effects'] or not isinstance(row.get('chance'),dict):
            raise ValueError('Invalid aggregate probability or outputs')
        if any(not isinstance(v,dict) or set(v)!={'base','growth'} for v in [row['chance'],*row['effects'].values()]):
            raise ValueError('Aggregate growth requires base and growth')
        if not isinstance(row.get('cost'),dict):raise ValueError('Invalid aggregate costs')
        if any(type(v) is not int or v<=0 for v in row['cost'].values()) or set(row['cost'])!={'souls','opportunity_multiplier'}:
            raise ValueError('Aggregate costs must be positive')
        recipe=row.get('recipe')
        if not isinstance(recipe,dict) or len(recipe)!=1 or any(
                not isinstance(k,str) or type(v) is not int or v<=0 for k,v in recipe.items()):
            raise ValueError('Each aggregate requires one real material with a positive quantity')
    for rank in range(11):validate_mechanisms(tuple(build(row,rank) for row in rows))


def validate_material_sources(config,items,goods):
    """Natural supply is world-local; carried inventory and resale keep ownership."""
    for row in config.get('five_aggregates',[]):
        for key in row['recipe']:
            item=items.get(key)
            sources=[r for r in goods if r.get('kind')=='item' and r.get('content_id')==key]
            if item is None or 'wuyun_material' not in item.tags:
                raise ValueError('Unknown five-aggregate material')
            if not sources or any(r.get('world','human')!='asura' or r.get('tier') not in range(9,13) for r in sources):
                raise ValueError('Five-aggregate materials must originate only in Asura')


def validate_state(record):
    if not isinstance(record,dict):raise ValueError('魔躯记录须为对象')
    level=record.get('body_level',0)
    if type(level) is not int or not 0<=level<=50:raise ValueError('魔躯层数须为0至50')
    ranks=record.get('aggregates',{})
    if not isinstance(ranks,dict) or set(ranks)-set(AGGREGATES):raise ValueError('五蕴修炼记录无效')
    if any(type(v) is not int or not 0<=v<=10 for v in ranks.values()):raise ValueError('五蕴修炼等级须为0至10')
    return record
