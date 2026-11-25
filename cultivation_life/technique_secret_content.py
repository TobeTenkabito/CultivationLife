"""Finite, authored manual-to-secret-art links; no custom-manual inference."""
from .definition_data import definition as _content_definition
SLOTS = {'main': '主修', 'support': '辅修', 'combat': '战斗'}
EFFECTS = {'major_bonus', 'minor_bonus', 'body_bonus', 'sense_discount',
           'cost_discount', 'ascension_guard', 'heart_relief', 'sense_experience', 'sense_rank',
           'trial_guard', 'trial_breach', 'trial_sustain', 'trial_sense',
           'body_progress', 'qi_experience', 'art_experience', 'clone_pair', 'frost_tribulation'}
NATURES = {'metal', 'wood', 'water', 'fire', 'earth', 'wind', 'thunder', 'yin', 'yang'}


def validate(config, books):
    ids, names, links = set(), set(), set()
    for row in config.get('technique_arts', []):
        fields = {'id','name','technique_id','slot','realm','effect','value','cost','requirements','description'}
        if not isinstance(row, dict) or set(row) not in (fields, fields | {'target'}):
            raise ValueError('功法秘术定义字段无效')
        identity, name, book_id = row['id'], row['name'], row['technique_id']
        if (not isinstance(identity,str) or not identity.startswith('manual_') or identity in ids
                or not isinstance(name,str) or not name or name in names or book_id in links or book_id not in books):
            raise ValueError('功法秘术身份、名称或原功法无效')
        book=books[book_id]
        if row['slot'] not in SLOTS or row['effect'] not in EFFECTS or book.category!='spiritual':
            raise ValueError('功法秘术栏位或效果不受支持')
        if type(row['realm']) is not int or row['realm']!=book.grade or not 1<=row['realm']<=12:
            raise ValueError('功法秘术适用境界无效')
        value=row['value']
        maximum = (150 if row['effect']=='art_experience' else 100) * row['realm'] ** 2 if row['effect'] in {'qi_experience','art_experience'} else 20 if row['effect'] in {'heart_relief','sense_experience'} else 1
        if type(value) not in (int,float) or not 0<value<=maximum:
            raise ValueError('功法秘术效果超出有限预算')
        targets = ({'spirit','demon','monster','yin'} if row['effect']=='qi_experience'
                   else {'alchemy','refining','formation','talisman','spirit_control'} if row['effect']=='art_experience' else None)
        if (targets is not None and row.get('target') not in targets
                or targets is None and 'target' in row):
            raise ValueError('秘术成长目标无效')
        cost=row['cost']; requirements=row['requirements']
        if not isinstance(cost,dict) or set(cost)-{'opportunity_bp','stones','formations','essences'}:
            raise ValueError('功法秘术代价种类无效')
        for k, ceiling in (('opportunity_bp',10000),('stones',1000000000)):
            if k in cost and (type(cost[k]) is not int or not 0<cost[k]<=ceiling):raise ValueError('秘术报价无效')
        for field in ('formations','essences'):
            entries=cost.get(field,[])
            if not isinstance(entries,list) or len(entries)>9:raise ValueError('秘术材料数量无效')
            for entry in entries:
                keys={'nature','tier'} if field=='formations' else {'nature','tier','kind'}
                if (not isinstance(entry,dict) or set(entry)!=keys or entry['nature'] not in NATURES
                        or type(entry['tier']) is not int or not 1<=entry['tier']<=12
                        or field=='essences' and entry['kind'] not in {'core','soul'}):
                    raise ValueError('秘术材料定义无效')
        if not isinstance(requirements,dict) or set(requirements)-{'level','body','sense','qi'}:
            raise ValueError('秘术前置种类无效')
        for key in ('level','body','sense'):
            if key in requirements and (type(requirements[key]) is not int or not 1<=requirements[key]<={'level':9,'body':100,'sense':1000}[key]):
                raise ValueError('秘术前置数值无效')
        if 'qi' in requirements:
            q=requirements['qi']
            if not isinstance(q,dict) or set(q)!={'source','level'} or q['source'] not in {'spirit','demon','monster','yin'} or type(q['level']) is not int or not 1<=q['level']<=1000:
                raise ValueError('秘术气经验前置无效')
        if not isinstance(row['description'],str) or not row['description']:raise ValueError('秘术缺少说明')
        ids.add(identity);names.add(name);links.add(book_id)
        if STATE_KINDS.get(identity)!=(row['effect'],row['realm']):raise ValueError('功法秘术内容与状态契约不一致')
    if ids and ids!=set(STATE_KINDS):raise ValueError('功法秘术目录不完整')


# Reviewed personal-state identities; content validation checks this manifest.
STATE_KINDS = _content_definition(__name__, "STATE_KINDS")

# Reviewed major-breakthrough additions; original receipts keep their identity.
STATE_KINDS.update({
 'manual_demon_dance': ('clone_pair', 4),
 'manual_frost_sky': ('frost_tribulation', 8),
 'manual_gate_dao_2': ('major_bonus', 2),
 'manual_gate_dao_5': ('major_bonus', 5),
 'manual_gate_dao_8': ('ascension_guard', 8),
 'manual_gate_demonic_1': ('major_bonus', 1),
 'manual_gate_demonic_3': ('major_bonus', 3),
 'manual_gate_demonic_6': ('major_bonus', 6),
 'manual_gate_demonic_7': ('major_bonus', 7),
 'manual_gate_demonic_8': ('ascension_guard', 8),
 'manual_gate_ghost_1': ('major_bonus', 1),
 'manual_gate_ghost_2': ('major_bonus', 2),
 'manual_gate_ghost_4': ('major_bonus', 4),
 'manual_gate_ghost_5': ('major_bonus', 5),
 'manual_gate_ghost_7': ('major_bonus', 7),
 'manual_gate_ghost_8': ('ascension_guard', 8),
 'manual_gate_monster_1': ('cost_discount', 1),
 'manual_gate_monster_2': ('cost_discount', 2),
 'manual_gate_monster_3': ('cost_discount', 3),
 'manual_gate_monster_4': ('cost_discount', 4),
 'manual_gate_monster_5': ('cost_discount', 5),
 'manual_gate_monster_6': ('cost_discount', 6),
 'manual_gate_monster_8': ('cost_discount', 8),
 'manual_gate_buddhist_1': ('major_bonus', 1),
 'manual_gate_buddhist_2': ('major_bonus', 2),
 'manual_gate_buddhist_3': ('major_bonus', 3),
 'manual_gate_buddhist_4': ('major_bonus', 4),
 'manual_gate_buddhist_5': ('major_bonus', 5),
 'manual_gate_buddhist_6': ('major_bonus', 6),
 'manual_gate_buddhist_7': ('major_bonus', 7),
 'manual_gate_buddhist_8': ('ascension_guard', 8),
 'manual_gate_buddhist_9': ('major_bonus', 9),
 'manual_gate_buddhist_10': ('major_bonus', 10),
 'manual_gate_buddhist_11': ('major_bonus', 11),
 'manual_gate_confucian_1': ('major_bonus', 1),
 'manual_gate_confucian_2': ('major_bonus', 2),
 'manual_gate_confucian_3': ('major_bonus', 3),
 'manual_gate_confucian_4': ('major_bonus', 4),
 'manual_gate_confucian_5': ('major_bonus', 5),
 'manual_gate_confucian_6': ('major_bonus', 6),
 'manual_gate_confucian_7': ('major_bonus', 7),
 'manual_gate_confucian_8': ('ascension_guard', 8),
 'manual_gate_confucian_9': ('major_bonus', 9),
 'manual_gate_confucian_10': ('major_bonus', 10),
 'manual_gate_confucian_11': ('major_bonus', 11),
})

def decode_records(value):
    import copy
    if not isinstance(value,dict) or len(value)>128:raise ValueError('功法秘术记录无效')
    definitions=STATE_KINDS
    for identity,record in value.items():
        if identity not in definitions or not isinstance(record,dict) or set(record)!={'activated','realms'}:
            raise ValueError('功法秘术记录含未知字段或来源')
        if record['activated'] is not True or not isinstance(record['realms'],list):raise ValueError('功法秘术激活记录无效')
        used=record['realms'];effect, realm=definitions[identity]
        if (any(type(n) is not int or not realm<=n<=12 for n in used)
                or used!=sorted(set(used)) or len(used)>12
                or (bool(used) != (effect=='sense_rank'))):raise ValueError('秘术境界次数记录无效')
    return copy.deepcopy(value)
