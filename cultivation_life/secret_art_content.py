"""Finite secret-art definitions and their ordinary, tradable source items."""
from __future__ import annotations

AFFINITIES = dict(metal='金', wood='木', water='水', fire='火', earth='土',
                  wind='风', thunder='雷', yin='阴', yang='阳')
FIVE = frozenset(('metal', 'wood', 'water', 'fire', 'earth'))


def definitions(config):
    if not isinstance(config, dict) or config.get('schema_version') != 1:
        raise ValueError('秘法配置版本不受支持')
    result = {}
    for row in config.get('arts', []):
        affinity = row.get('affinity')
        if affinity not in AFFINITIES or row.get('id') != 'root_' + affinity or row['id'] in result:
            raise ValueError('补灵秘法编号或属性不合法')
        group = config['five_element' if affinity in FIVE else 'mutated']
        for key in ('study_years', 'casting_years', 'study_stones', 'material_realm'):
            value = group[key]
            if type(value) is not int or value < (0 if key == 'study_stones' else 1):
                raise ValueError('秘法时间、代价及材料境界必须为合法整数')
        if not 1 <= group['material_realm'] <= 12:
            raise ValueError('秘法材料境界不存在')
        result[row['id']] = dict(row, **group,
                                 manual_id='secret_manual_' + affinity)
    if len(result) != len(AFFINITIES):
        raise ValueError('补灵秘法须覆盖九种属性')
    for key in ('core_drop_chance', 'soul_drop_chance'):
        if type(config.get(key)) not in (int, float) or not 0 <= config[key] <= 1:
            raise ValueError('内丹与元神掉落概率必须在零至一之间')
    for key in ('manual_price', 'core_price_multiplier'):
        if type(config.get(key)) is not int or config[key] <= 0:
            raise ValueError('秘法传承与内丹价格配置不合法')
    return result


def core_id(affinity, rank):
    return f'secret_core_{affinity}_{rank}'


def soul_id(affinity, rank):
    return f'secret_soul_{affinity}_{rank}'


def build(config, profiles):
    from .economy_content import BASE_PRICES
    arts = definitions(config)
    items, goods = [], []
    for art in arts.values():
        affinity = art['affinity']
        items.append(dict(id=art['manual_id'], name=art['name'] + '玉简',
                          tags=['secret_art_manual', 'secret_art:' + art['id']],
                          description=f"记载{art['name']}；在秘法中消耗时间与灵石独立修习，无修为境界要求。"))
        for rank in range(1, 13):
            for kind, identity, label in [('core', core_id(affinity, rank), '内丹'), ('soul', soul_id(affinity, rank), '元神')]:
                items.append(dict(id=identity, name=f'{AFFINITIES[affinity]}属{label}（{rank}级）',
                                  tags=['material', 'secret_art_' + kind, 'affinity:' + affinity, 'realm:' + str(rank)],
                                  description=f'保留明确{AFFINITIES[affinity]}属本源的{rank}级{label}，跨界通用。补灵秘法另有材料境界要求；普通无属性内丹不能替代。'))
        for world, profile in profiles.items():
            tier = int(profile['tier'])
            if tier not in {1, 2, 3}:
                continue
            cap = {1: 5, 2: 8, 3: 12}[tier]
            goods.append(dict(world=world, kind='item', content_id=art['manual_id'], tier=1, price=config['manual_price']))
            for rank in range(1, cap + 1):
                for identity in (core_id(affinity, rank), soul_id(affinity, rank)):
                    goods.append(dict(world=world, kind='item', content_id=identity, tier=rank,
                                      price=BASE_PRICES[rank - 1] * config['core_price_multiplier']))
    return items, goods
