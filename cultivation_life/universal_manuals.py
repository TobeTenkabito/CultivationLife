"""Leveled universal inheritance manuals and their natural circulation bands."""
import re

PATHS = dict(dao='道', demonic='魔', monster='妖', ghost='鬼', buddhist='佛', confucian='儒')
PREFIX = 'universal_manual_'


def identity(path, grade, level=1):
    base=f'{PREFIX}{path}_{grade}'
    return base if level==1 else f'{base}_lv{level}'


def parse(key):
    match=re.fullmatch(r'universal_manual_([a-z]+)_(1[0-2]|[1-9])(?:_lv([2-9]))?',key)
    if not match or match[1] not in PATHS:return None
    return match[1],int(match[2]),int(match[3] or 1)


def material(book):
    return identity(book.path, book.grade, book.level)


def cost(book):
    return 1


def count(player, book):
    return sum(max(0, item.quantity) for item in player.inventory if item.id == material(book))


def supported(book):
    return book.path in PATHS and 1 <= book.grade <= 12


def name(path, grade, level=1):
    return f'{grade}阶{PATHS[path]}途万能玉简 Lv.{level}'


def allowed(grade, ceiling):
    floor={5:1,8:6,12:9}.get(ceiling)
    return floor is not None and floor<=grade<=ceiling


def build(ceilings, realms):
    items, goods = [], []
    for path, title in PATHS.items():
        for grade in range(1, 13):
            for level in range(1,10):
                key=identity(path,grade,level)
                effect=(f'在功法页消耗一份，为同道途、同品阶的 Lv.{level} 功法升至 Lv.{level+1}；'
                        f'两份本级玉简可合成一份 Lv.{level+1} 万能玉简。') if level<9 else '九重修习心得，玉简已达最高等级。'
                items.append(dict(id=key,name=name(path,grade,level),technique_level=level,
                    description=f'汇录{title}途{grade}阶修习心得。'+effect,
                    tags=['material','economic_product','universal_manual',f'grade:{grade}',f'path:{path}'],
                    force_tier=2 if grade>=9 else 1))
            price=max(12, round(realms[grade]['base_power']*1.5))
            for world,ceiling in ceilings.items():
                if allowed(grade,ceiling):
                    goods.append(dict(kind='item',content_id=identity(path,grade),tier=grade,price=price,world=world))
    return items,goods
