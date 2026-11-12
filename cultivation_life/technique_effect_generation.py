"""Seeded doctrine-manual effects on a dedicated versioned random stream."""
import hashlib
import random

from .technique_effect_schema import describe, validate_effect
from .technique_effect_profiles import PROFILES, UPPER_PROFILES, GENERATED_BRANCHES, theme_key

GENERATOR_VERSION = 2
FEATURES = frozenset({'fortify', 'opening', 'retaliate', 'sacrifice', 'frugal', 'shelter', 'execution'})


def generate_effect(seed, doctrine_id, manual_id, *, feature, preference, theme):
    if type(seed) is not int or not isinstance(doctrine_id, str) or not doctrine_id:
        raise ValueError('功法效果种子或道统身份无效')
    if not isinstance(manual_id, str) or not (manual_id.startswith(doctrine_id + ':manual:') or manual_id == doctrine_id + ':concordance'):
        raise ValueError('功法须归属原道统')
    if (not isinstance(feature, str) or not isinstance(preference, str) or feature not in FEATURES
            or preference not in {'main', 'support', 'combat', 'balanced'} or not isinstance(theme, str)):
        raise ValueError('未知道统效果主题或功法倾向')
    # No consumption of the doctrine name/stat streams or game.rng_state.
    lineage = theme_key(theme)
    if lineage is None:
        raise ValueError('未知道统主题，不能退回通用随机效果')
    material = f'technique-effect:v{GENERATOR_VERSION}:{seed}:{doctrine_id}:{manual_id}:{lineage}:{feature}'
    rng = random.Random(int.from_bytes(hashlib.sha256(material.encode('utf-8')).digest(), 'big'))
    role = {'main': 0, 'balanced': 0, 'support': 1, 'combat': 2}[preference]
    suite = (GENERATED_BRANCHES.get(lineage, PROFILES[lineage])
             if doctrine_id.startswith('celestial:generated_') else PROFILES[lineage])
    kind, trigger, delivery = suite[role].split(':')
    strength = (rng.choice((75, 100, 125)) if kind in {'guard', 'recover', 'frugal'} else
                rng.choice((400, 500, 600)) if preference != 'combat' else rng.choice((600, 800, 1000)))
    return validate_effect(dict(version=2, generator_version=GENERATOR_VERSION, lineage=lineage, mastery=False, kind=kind,
        trigger=trigger, delivery=delivery, strength_bp=strength,
        cost_bp={'main': 200, 'support': 250, 'combat': 300, 'balanced': 250}[preference],
        cooldown=rng.choice((1, 2)), uses=3, duration=2,
        refund_bp=2000 if kind == 'frugal' else 0))


def attach_effect(manual, seed, *, feature, theme, theme_name=None):
    """Generation-time only; an already frozen effect must never be rerolled."""
    if manual.get('combat_effect'):
        validate_effect(manual['combat_effect'])
        return False
    effect = generate_effect(seed, manual['doctrine_id'], manual['id'], feature=feature,
                             preference=manual['growth_preference'], theme=theme)
    manual['combat_effect'] = effect
    manual['description'] = f'承自本门{theme_name or theme}之意，以自身修习与真实气机运转成法。' + describe(effect)
    return True


def concordance_effect(books, *, seed, doctrine_id, feature, theme):
    """Carry the original main signature forward, with a strict bounded advantage."""
    lineage = theme_key(theme)
    if lineage is None:
        raise ValueError('合练传承主题无效')
    original = next((b['combat_effect'] for b in books
                     if b.get('growth_preference') == 'main' and b.get('combat_effect')), None)
    if original is None:
        original = generate_effect(seed, doctrine_id, doctrine_id + ':concordance',
                                   feature=feature, preference='main', theme=theme)
    effect = validate_effect(original)
    # Same trigger, delivery and payload as the collected main manual. No reroll
    # into an unrelated build, and no exponential fusion-of-fusion amplification.
    ceiling = 150 if effect['kind'] in {'guard', 'recover', 'frugal'} else 1000
    costs = [b['combat_effect']['cost_bp'] for b in books if b.get('combat_effect')]
    cooldowns = [b['combat_effect']['cooldown'] for b in books if b.get('combat_effect')]
    effect.update(version=2, generator_version=2, lineage=lineage, mastery=True,
                  strength_bp=ceiling * 6 // 5,
                  cost_bp=max(100, min(costs or [effect['cost_bp']]) * 4 // 5),
                  cooldown=max(0, min(cooldowns or [effect['cooldown']]) - 1))
    return validate_effect(effect)


def upper_effect(world, role, grade):
    """Authoring helper for the 48 existing upper-world books, not a load hook."""
    from .technique_effect_schema import integer
    integer(grade, 9, 12, '三界功法品阶')
    if world not in UPPER_PROFILES or role not in UPPER_PROFILES[world]:
        raise ValueError('未知三界功法系列')
    kind, trigger, delivery = UPPER_PROFILES[world][role].split(':')
    strength = (100, 110, 120, 125)[grade - 9] if kind in {'guard', 'recover', 'frugal'} else (600, 700, 800, 900)[grade - 9]
    return validate_effect(dict(version=2, generator_version=2, lineage=world, mastery=False,
        kind=kind, trigger=trigger, delivery=delivery, strength_bp=strength,
        cost_bp=200 if role in {'MAIN', 'BODY'} else 250, cooldown=1, uses=3, duration=2,
        refund_bp=2000 if kind == 'frugal' else 0))
