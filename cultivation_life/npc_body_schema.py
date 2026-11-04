"""Bounded body-owned NPC training save record."""
def validate(value):
    if not isinstance(value,dict) or set(value)-{'lights','wuyun','monster','ghost'}:
        raise ValueError('NPC肉身精修记录无效')
    for ranks in value.values():
        if not isinstance(ranks,dict) or len(ranks)>20 or any(
            not isinstance(k,str) or not 1<=len(k)<=64 or type(v) is not int or not 0<=v<=10
            for k,v in ranks.items()):raise ValueError('NPC肉身精修须为0至10重')
    return value


