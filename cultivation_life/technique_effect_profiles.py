"""Authored lineage grammar. Each tuple is main, support, combat; no RNG/state."""
from .definition_data import definition as _content_definition

# kind:trigger:delivery. Themes determine play, not just a name or random weight.


PROFILES = _content_definition(__name__, "PROFILES")

THEME_NAMES = dict(zip(PROFILES, (
    '雷霆', '星辰', '虚空', '霜雪', '离火', '沧溟', '山岳', '清风', '青木', '庚金',
    '曜阳', '太阴', '玄镜', '梦境', '天音', '岁序', '因缘', '剑意', '镇封', '净莲',
    '烟霞', '生息', '寂灭', '龙章', '玄文', '玉清', '归潮', '衡律', '霹雳', '微尘', '苍穹', '混元',
)))

# The original theme sampler may also select either of the two fixed themes.
# Give that generated lineage a distinct branch without changing the sampler,
# the old names, or the original fixed inheritance.
GENERATED_BRANCHES = _content_definition(__name__, "GENERATED_BRANCHES")

# Existing three-world upper manuals: cultivation, combat, body, divine sense.
UPPER_PROFILES = _content_definition(__name__, "UPPER_PROFILES")


def theme_key(theme):
    if theme in PROFILES:
        return theme
    return next((key for key, name in THEME_NAMES.items() if name == theme), None)
