"""Finite, authored manual-to-secret-art links; no custom-manual inference."""
SLOTS = {'main': '主修', 'support': '辅修', 'combat': '战斗'}
EFFECTS = {'major_bonus', 'minor_bonus', 'body_bonus', 'sense_discount',
           'cost_discount', 'heart_relief', 'sense_experience', 'sense_rank',
           'trial_guard', 'trial_breach', 'trial_sustain', 'trial_sense',
           'body_progress', 'qi_experience', 'art_experience'}
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
STATE_KINDS = {'manual_common_qi': ('major_bonus', 1),
 'manual_demon_breathing': ('body_bonus', 1),
 'manual_ghost_breathing': ('sense_experience', 1),
 'manual_monster_breathing': ('body_bonus', 1),
 'manual_void_cycle': ('minor_bonus', 2),
 'manual_blood_river': ('major_bonus', 2),
 'manual_yin': ('heart_relief', 2),
 'manual_monster_iron_bone': ('sense_experience', 2),
 'manual_tianjian': ('major_bonus', 3),
 'manual_wanmo': ('cost_discount', 3),
 'manual_ghostfire_blade': ('major_bonus', 3),
 'manual_crimson_furnace': ('body_bonus', 3),
 'manual_common_gui': ('cost_discount', 4),
 'manual_blood_sea_embryo': ('major_bonus', 4),
 'manual_soul_lamp_canon': ('sense_discount', 4),
 'manual_monster_moon_form': ('body_bonus', 4),
 'manual_sea': ('minor_bonus', 5),
 'manual_four_source_devouring': ('major_bonus', 5),
 'manual_nether_tide_canon': ('cost_discount', 5),
 'manual_monster_myriad_spirits': ('sense_experience', 5),
 'manual_void_origin_canon': ('major_bonus', 6),
 'manual_black_sun_true_flame': ('sense_discount', 6),
 'manual_nine_prison_void': ('major_bonus', 6),
 'manual_monster_heaven_bone': ('body_bonus', 6),
 'manual_chunli_sword_array': ('major_bonus', 7),
 'manual_all_heavens_demon': ('minor_bonus', 7),
 'manual_yin_yang_soul_unity': ('heart_relief', 7),
 'manual_monster_ancestral_court': ('cost_discount', 7),
 'manual_origin_gang_shield': ('sense_discount', 8),
 'manual_primordial_demon_lord': ('cost_discount', 8),
 'manual_reincarnation_gate_canon': ('heart_relief', 8),
 'manual_monster_primordial_body': ('sense_experience', 8),
 'manual_celestial_heritage_1': ('trial_guard', 9),
 'manual_asura_9_combat': ('trial_breach', 9),
 'manual_reincarnation_9_main': ('trial_sense', 9),
 'manual_nether_9_main': ('trial_sustain', 9),
 'manual_celestial_heritage_2': ('trial_sustain', 10),
 'manual_asura_10_main': ('trial_guard', 10),
 'manual_reincarnation_10_combat': ('trial_breach', 10),
 'manual_nether_10_main': ('trial_guard', 10),
 'manual_celestial_heritage_5': ('trial_breach', 11),
 'manual_asura_11_main': ('trial_sustain', 11),
 'manual_reincarnation_11_main': ('trial_guard', 11),
 'manual_nether_11_combat': ('trial_breach', 11),
 'manual_celestial_heritage_4': ('sense_discount', 12),
 'manual_asura_12_main': ('minor_bonus', 12),
 'manual_reincarnation_12_main': ('cost_discount', 12),
 'manual_nether_12_main': ('sense_discount', 12),
 'manual_five_color_ice': ('major_bonus', 4),
 'manual_know_heaven': ('sense_rank', 2),
 'manual_earth_marrow': ('body_progress', 2),
 'manual_five_mountains': ('body_progress', 5),
 'manual_blood_marrow': ('body_progress', 8),
 'manual_spirit_return': ('qi_experience', 3),
 'manual_demon_return': ('qi_experience', 4),
 'manual_yin_return': ('qi_experience', 5),
 'manual_monster_return': ('qi_experience', 6),
 'manual_read_flame': ('art_experience', 2),
 'manual_hear_metal': ('art_experience', 2),
 'manual_array_pivots': ('art_experience', 4),
 'manual_thunder_script': ('art_experience', 2),
 'manual_beast_breath': ('art_experience', 7)}

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
