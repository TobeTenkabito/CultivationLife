"""Bounded, typed observations in a resumable combat instance."""
import json
from ...technique_effect_schema import finite, integer


def validate(runtime,value):
    units=runtime.battle.units;number=value['round'];sequence=value['sequence']
    def identity(key,owner,enemy=True):
        if key not in units or (units[key].unit.side!=units[owner].unit.side)!=enemy:
            raise ValueError('观察来源不是本场原合法人物')
    def seen(row):
        if not isinstance(row,dict) or set(row)!={'count','paid_count','ordinal','round','target','seq','receipts'}:
            raise ValueError('观招回执字段无效')
        receipts=row['receipts']
        if not isinstance(receipts,list) or len(receipts)>5 or any(k not in {'1','2','3','4','5'} for k in receipts) or len(set(receipts))!=len(receipts):
            raise ValueError('重复观招付款回执无效')
        for k in ('count','paid_count'):integer(row[k],0,1000000,'实际观招次数')
        integer(row['ordinal'],1,129,'来源序号');integer(row['round'],1,number,'观招轮次')
        integer(row['seq'],1,sequence,'观招序号')
        if row['target'] is not None and row['target'] not in units:raise ValueError('观招对象不存在')
    rounds={'field_paid_round','field_ended_round','hit_round','hurt_round','complete_round','heavy_round','broken_round','broke_round'}
    sequences={'hit_seq','hurt_seq','broken_seq','broke_seq','shield_used_seq','attacked_shield_seq'}
    targets={'hit_target','hurt_source','first_target','broken_source','broke_target'}
    booleans={'first','changed','ever_second'}
    allowed=rounds|sequences|targets|booleans|{'hurt_amount','field','cast','source_kinds','losses'}
    for owner,facts in value['facts'].items():
        if set(facts)-allowed:raise ValueError('未知战斗事实')
        for k,v in facts.items():
            if k in rounds:integer(v,1,number,'事实轮次')
            elif k in sequences:integer(v,1,sequence,'事实序号')
            elif k in targets:
                if v is not None:identity(v,owner)
            elif k in booleans:
                if type(v) is not bool:raise ValueError('先后手事实无效')
            elif k=='hurt_amount':finite(v,0,1,'实际损耗')
            elif k=='source_kinds':integer(v,0,128,'已见来源')
            elif k=='field':
                if v is not None and v not in {d.id for d in units[owner].unit.capabilities.voisinages}:
                    raise ValueError('领域来源不存在')
            elif k=='losses':
                if not isinstance(v,list) or len(v)>32:raise ValueError('受损回执超过上限')
                last=0
                for row in v:
                    if not isinstance(row,dict) or set(row)!={'round','seq','source','amount'}:raise ValueError('损耗回执字段无效')
                    integer(row['seq'],last+1,sequence,'损耗序号');last=row['seq']
                    integer(row['round'],1,number,'损耗轮次');finite(row['amount'],0,1,'损耗额度')
                    identity(row['source'],owner)
            elif k=='cast':
                if not isinstance(v,dict) or set(v)!={'source','book','paid','actual','target','changed','streak','count','paid_count','ordinal','round','seq','receipts'}:
                    raise ValueError('观招事实字段无效')
                identity(v['source'],owner)
                if v['target'] is not None and v['target'] not in units:raise ValueError('观招对象不存在')
                if not isinstance(v['book'],str) or not 1<=len(v['book'])<=200:raise ValueError('观招功法无效')
                if any(type(v[k]) is not bool for k in ('paid','actual','changed')):raise ValueError('观招类型无效')
                integer(v['streak'],0,1000000,'连续观招次数')
                seen({k:v[k] for k in ('count','paid_count','ordinal','round','target','seq','receipts')})
    for owner,records in value['observations'].items():
        for key,row in records.items():
            try:source,book=json.loads(key)
            except (ValueError,TypeError):raise ValueError('观招来源无效') from None
            identity(source,owner)
            if not isinstance(book,str) or not 1<=len(book)<=200:raise ValueError('观招书目无效')
            seen(row)
