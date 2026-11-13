"""Reviewed complete titles for offline authoring; never runtime RNG.

Each family has twelve grade groups, each main/support/combat. Titles are
literal editorial data, not combinations of images, prefixes or suffixes.
"""
from functools import lru_cache
from pathlib import Path

TITLE_ROOT = Path(__file__).resolve().parent / 'data' / 'common_titles'
PATHS = ('dao', 'demonic', 'monster', 'ghost')
ROLES = ('main', 'support', 'combat')
FAMILIES = (
    'neutral', 'metal', 'wood', 'water', 'fire', 'earth', 'wind', 'thunder',
    'yin', 'yang', 'metal_water', 'water_wood', 'wood_fire', 'fire_earth',
    'earth_metal', 'wind_thunder', 'yin_yang', 'wind_thunder_yin',
    'wind_thunder_yang', 'wind_yin_yang', 'thunder_yin_yang',
    'wind_thunder_yin_yang', 'metal_water_wood', 'wood_fire_earth',
    'metal_wood_water_earth', 'wood_water_fire_earth', 'five_elements',
)


@lru_cache(maxsize=1)
def _titles():
    result, used = {}, set()
    for path in PATHS:
        seen = set()
        for line in (TITLE_ROOT / f'{path}.txt').read_text(encoding='utf-8').splitlines():
            family, text = line.split(':', 1)
            groups = text.split('|')
            if family not in FAMILIES or family in seen or len(groups) != 12:
                raise ValueError(f'书名表分组错误：{path}/{family}')
            seen.add(family)
            for grade, group in enumerate(groups, 1):
                titles = group.split()
                if len(titles) != 3:
                    raise ValueError(f'书名表缺少三类完整标题：{path}/{family}/{grade}')
                for role, title in zip(ROLES, titles):
                    if title in used:
                        raise ValueError(f'功法书名重复：{title}')
                    used.add(title)
                    result[path, grade, family, role] = title
        if seen != set(FAMILIES):
            raise ValueError(f'书名表系列缺失：{path}')
    return result


def technique_name(path, grade, family, role):
    """Return the reviewed title for this immutable catalog position."""
    return _titles()[path, grade, family, role]
