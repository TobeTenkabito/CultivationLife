"""Current descriptions for generated books; stored recipes remain immutable."""
from .technique_effect_schema import describe


def generated(book):
    get=book.get if isinstance(book,dict) else lambda k,d=None:getattr(book,k,d)
    category=get('category','spiritual')
    name=get('name','无名传承')
    if category=='body':
        return f'《{name}》以周天温养筋骨、淬炼肉身。配置于炼体栏，随功法等级提升炼体修习助益。'
    purpose={'divine_sense':'凝聚神念，磨炼识海，修习所得随功法等级增长。',
             'transformation':'循血脉与形态变化之理，拓展变身容量与驾驭空间。'}.get(category,'引灵气循经脉而行，将修习心得化入周天。')
    prefix='前人合练完成的完整真传。' if get('id','').endswith(':concordance') else ''
    effect=get('combat_effect',{})
    detail=describe(effect) if effect and category=='spiritual' else ''
    if category=='spiritual' and get('authored_buffs',[]):
        from .authored_technique_schema import buff_text
        detail+=''.join(buff_text(b) for b in get('authored_buffs'))
    return f'《{name}》{prefix}{purpose}'+detail
