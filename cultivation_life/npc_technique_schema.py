"""Pure preservation of NPC learning facts, including their recorded levels."""
def normalize(levels, main=None, main_level=1, traits=None):
    if not isinstance(levels, dict) or len(levels)>20000:
        raise ValueError('人物功法等级记录无效')
    result=dict(levels)
    for key,value in (traits or {}).get('heritage_study',{}).get('levels',{}).items():
        result[key]=max(result.get(key,1),value)
    if main:
        result[main]=max(result.get(main,1),main_level)
    if any(not isinstance(k,str) or len(k)>200 or type(v) is not int or not 1<=v<=9 for k,v in result.items()):
        raise ValueError('人物功法等级须为1–9')
    return result
