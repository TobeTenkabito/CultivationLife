"""Authored lineage grammar. Each tuple is main, support, combat; no RNG/state."""

# kind:trigger:delivery. Themes determine play, not just a name or random weight.
PROFILES = {
    'thunder': ('breach:after_hit:immediate', 'guard:first_exchange:immediate', 'strike:first_exchange:immediate'),
    'star': ('frugal:odd_round:split', 'guard:even_round:split', 'strike:even_round:delayed'),
    'void': ('breach:steady:immediate', 'guard:after_hurt:delayed', 'strike:steady:immediate'),
    'frost': ('guard:opening:split', 'frugal:after_hurt:split', 'breach:after_hurt:delayed'),
    'flame': ('strike:after_hit:split', 'frugal:after_hit:immediate', 'strike:after_hit:immediate'),
    'water': ('recover:after_hurt:split', 'guard:after_hurt:split', 'breach:even_round:immediate'),
    'mountain': ('guard:opening:immediate', 'recover:low_state:immediate', 'strike:after_hurt:immediate'),
    'wind': ('frugal:first_exchange:immediate', 'guard:odd_round:immediate', 'strike:odd_round:immediate'),
    'wood': ('recover:opening:split', 'guard:low_state:split', 'strike:steady:split'),
    'metal': ('breach:opening:immediate', 'guard:after_hit:immediate', 'strike:after_hit:delayed'),
    'sun': ('strike:odd_round:immediate', 'recover:odd_round:immediate', 'breach:odd_round:immediate'),
    'moon': ('recover:even_round:split', 'guard:even_round:immediate', 'strike:even_round:immediate'),
    'mirror': ('frugal:after_hurt:immediate', 'guard:after_hurt:immediate', 'breach:after_hurt:immediate'),
    'dream': ('guard:steady:delayed', 'recover:steady:delayed', 'strike:steady:delayed'),
    'sound': ('recover:after_hit:split', 'guard:after_hit:split', 'strike:opening:split'),
    'time': ('frugal:opening:delayed', 'recover:opening:delayed', 'breach:opening:delayed'),
    'fate': ('frugal:after_hit:delayed', 'guard:after_hurt:delayed', 'strike:after_hurt:delayed'),
    'sword': ('breach:after_hit:immediate', 'frugal:after_hit:immediate', 'strike:target_wounded:immediate'),
    'seal': ('guard:first_exchange:delayed', 'frugal:steady:immediate', 'breach:steady:delayed'),
    'lotus': ('recover:low_state:immediate', 'frugal:low_state:immediate', 'breach:low_state:immediate'),
    'mist': ('frugal:opening:split', 'guard:opening:delayed', 'strike:odd_round:delayed'),
    'life': ('recover:after_hurt:immediate', 'guard:low_state:immediate', 'strike:low_state:split'),
    'death': ('breach:target_wounded:immediate', 'frugal:target_wounded:immediate', 'strike:target_wounded:split'),
    'dragon': ('strike:first_exchange:immediate', 'guard:after_hit:immediate', 'breach:first_exchange:immediate'),
    'ink': ('breach:even_round:delayed', 'frugal:odd_round:immediate', 'strike:even_round:split'),
    'jade': ('guard:steady:immediate', 'recover:steady:immediate', 'breach:steady:immediate'),
    'ocean': ('recover:even_round:immediate', 'frugal:even_round:split', 'strike:even_round:split'),
    'balance': ('frugal:even_round:immediate', 'guard:odd_round:split', 'breach:even_round:immediate'),
    'lightning': ('breach:first_exchange:immediate', 'frugal:first_exchange:immediate', 'strike:first_exchange:split'),
    'dust': ('guard:low_state:split', 'frugal:low_state:split', 'strike:after_hurt:split'),
    'heaven': ('breach:odd_round:immediate', 'guard:steady:split', 'strike:steady:immediate'),
    'origin': ('recover:opening:immediate', 'frugal:opening:immediate', 'breach:opening:immediate'),
}

THEME_NAMES = dict(zip(PROFILES, (
    '雷霆', '星辰', '虚空', '霜雪', '离火', '沧溟', '山岳', '清风', '青木', '庚金',
    '曜阳', '太阴', '玄镜', '梦境', '天音', '岁序', '因缘', '剑意', '镇封', '净莲',
    '烟霞', '生息', '寂灭', '龙章', '玄文', '玉清', '归潮', '衡律', '霹雳', '微尘', '苍穹', '混元',
)))

# The original theme sampler may also select either of the two fixed themes.
# Give that generated lineage a distinct branch without changing the sampler,
# the old names, or the original fixed inheritance.
GENERATED_BRANCHES = {
    'origin': ('recover:opening:split', 'frugal:steady:immediate', 'breach:steady:delayed'),
    'balance': ('frugal:even_round:split', 'guard:odd_round:immediate', 'breach:after_hurt:immediate'),
}

# Existing three-world upper manuals: cultivation, combat, body, divine sense.
UPPER_PROFILES = {
    'asura': {'MAIN': 'frugal:after_hurt:immediate', 'COMBAT': 'strike:low_state:immediate',
              'BODY': 'guard:after_hurt:immediate', 'SENSE': 'breach:after_hit:immediate'},
    'nether': {'MAIN': 'recover:after_hurt:split', 'COMBAT': 'strike:after_hit:split',
               'BODY': 'guard:opening:split', 'SENSE': 'breach:target_wounded:immediate'},
    'reincarnation': {'MAIN': 'frugal:even_round:immediate', 'COMBAT': 'strike:even_round:delayed',
                      'BODY': 'guard:odd_round:split', 'SENSE': 'breach:odd_round:immediate'},
}


def theme_key(theme):
    if theme in PROFILES:
        return theme
    return next((key for key, name in THEME_NAMES.items() if name == theme), None)
