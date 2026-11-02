"""Pure data validation and descriptor construction for the five monster changes."""
from .system.combat.body_mechanisms import BodyMechanism,REACTION_KINDS,validate_mechanisms

IDS=('xuanfu','nigu','liezang','feixue','shenhun')
UNLOCKS=dict(zip(REACTION_KINDS,(0,2,3,4,5,6,7,8,9,10)))


def build(row,rank,choice='auto'):
    effects={k:round(v['base']+v['growth']*rank,10) for k,v in row['effects'].items()}
    if row['id']=='liezang':
        effects.update({'retaliate_'+mode:1 for mode,level in UNLOCKS.items() if rank>=level})
        effects['retaliate_choice']=0 if choice=='auto' else REACTION_KINDS.index(choice)+1
    return BodyMechanism(row['id'],row['name'],effects,priority=row['priority'],requires=tuple(row.get('requires',())),level=rank)


def validate_record(record):
    if not isinstance(record,dict) or set(record)-{'level','training','reaction'}:raise ValueError('妖躯记录无效')
    if type(record.get('level',0)) is not int or not 0<=record.get('level',0)<=50:raise ValueError('妖躯层数须为0至50')
    ranks=record.get('training',{})
    if not isinstance(ranks,dict) or set(ranks)-set(IDS) or any(type(v) is not int or not 0<=v<=10 for v in ranks.values()):raise ValueError('五蜕修炼记录无效')
    mode=record.get('reaction','auto')
    if mode!='auto' and (mode not in UNLOCKS or ranks.get('liezang',0)<UNLOCKS[mode]):raise ValueError('烈脏选项尚未解锁')
    return record


def validate_content(config,items,goods):
    if not config:return
    rows=config['mechanisms']
    if any(type(config[k]) is not int or config[k]<0 for k in ('hp_per_level','mp_per_level')):raise ValueError('Invalid body intrinsic growth')
    if config['max_level']!=50 or tuple(r['id'] for r in rows)!=IDS or [r['unlock_level'] for r in rows]!=[10,20,30,40,50]:raise ValueError('Invalid monster body progression')
    for row in rows:
        if type(row['opportunity_multiplier']) is not int or row['opportunity_multiplier']<=0:raise ValueError('Invalid cultivation cost')
        recipe=row['recipe']
        if not isinstance(recipe,dict) or len(recipe)!=1 or any(type(n) is not int or n<=0 for n in recipe.values()):raise ValueError('Invalid material recipe')
        for key in recipe:
            if key not in items or 'monster_body_material' not in items[key].tags:raise ValueError('Unknown monster body material')
            sources=[r for r in goods if r.get('kind')=='item' and r['content_id']==key]
            if not sources or any(r.get('world')!='nether' or r['tier'] not in range(9,13) for r in sources):raise ValueError('Monster body materials originate only in Nether')
    if config['body_material'] not in rows[0]['recipe']:raise ValueError('Invalid body material')
    for rank in range(11):validate_mechanisms(tuple(build(r,rank) for r in rows))
