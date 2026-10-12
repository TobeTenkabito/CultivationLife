"""Seeded bespoke loot, granted through existing inventory, learning and artifact ports."""
import copy
import hashlib
import random

from ..generated_loot_schema import validate_reward
from ..models import Item, Technique
from ..rules import expected_combat_power, add_item, learn_technique
from .crafting_system import store_crafted_artifact


def generate_rewards(seed, world, number, realm, path, names):
    rng = random.Random(f'{seed}:relic:v1:{world}:{number}')
    rewards = []
    families = [rng.choice(['technique', 'artifact']), rng.choice(['treasure', 'item', 'technique', 'artifact'])]
    power = expected_combat_power(realm, 5)
    for slot, family in enumerate(families):
        quality = rng.choice(['上品', '极品', '绝品'])
        scale = {'上品': 1.2, '极品': 1.45, '绝品': 1.7}[quality]
        name = rng.choice(names['prefix']) + rng.choice(names[family])
        identity = hashlib.sha256(f'{seed}:{world}:{number}:{slot}:relic1'.encode()).hexdigest()[:24]
        amount = max(1., round(power * rng.uniform(.12, .2) * scale, 2))
        if family == 'technique':
            stats = dict(combat_bonus=amount, opportunity_bonus=round(realm*rng.uniform(.3,.7)*scale,2))
            stats['hp_bonus'] = max(.1,round(amount*rng.uniform(.2,.5),2))
            stats['mp_bonus'] = max(.1,round(amount*rng.uniform(.2,.5),2))
        elif family == 'artifact':
            stats = dict(combat_power=amount)
            stats[rng.choice(['max_hp','max_mp'])] = round(amount*rng.uniform(.3,.6),2)
        elif family == 'treasure':
            stats = dict(combat_bonus=round(amount*.7,2), hp_bonus=max(1,round(amount*.25)))
        else:
            stats = {rng.choice(['permanent_intrinsic_hp_bonus','permanent_intrinsic_mp_bonus']):max(1,round(amount*.2))}
        row = dict(kind='technique' if family == 'technique' else 'item', content_id='RELIC_'+identity,
                   name=name, tier=realm, roll=dict(family=family,path=path,quality=quality,stats=stats))
        validate_reward(row); rewards.append(row)
    return rewards


def grant(game, reward):
    validate_reward(reward)
    roll, tier = reward['roll'], reward['tier']
    stats = copy.deepcopy(roll['stats'])
    identity, name = reward['content_id'], reward['name']
    labels = {'combat_bonus':'战力','combat_power':'战力','hp_bonus':'气血','max_hp':'气血','mp_bonus':'法力','max_mp':'法力','opportunity_bonus':'机缘','permanent_intrinsic_hp_bonus':'永久气血','permanent_intrinsic_mp_bonus':'永久法力'}
    description = roll['quality'] + '遗泽：' + '、'.join(f'{labels[k]} +{v:g}' for k,v in stats.items())
    force_tier = 2 if tier >= 9 else 1
    if roll['family'] == 'technique':
        learn_technique(game.player, Technique(id=identity, name=name, path=roll['path'], grade=tier,
            force_tier=force_tier, element='neutral', growth_preference='combat', **stats))
    elif roll['family'] == 'artifact':
        artifact = dict(id=identity, name=name, quality='excellent', quality_name=roll['quality'],
            quality_multiplier=1., mold_id='relic', mold_name='上古遗宝', creator_name='前代修士',
            creator_id='ancient', created_year=game.player.age, scaling_realm_index=tier,
            scaling_realm_name='', scaling_benchmarks={}, materials=[], material_effects=[],
            allocations={}, designed_stats=copy.deepcopy(stats), actual_stats=stats, combat_effects=[],
            anchor_value=max(100,round(sum(stats.values())*10)), mold_rule_description='古修遗下的道韵，随器而存。',
            description=description,is_natal=False,force_tier=force_tier)
        store_crafted_artifact(game.player, artifact)
        for item in game.player.inventory:
            if item.id == identity: item.force_tier = force_tier
    else:
        consumable = roll['family'] == 'item'
        item = Item(id=identity,name=name,force_tier=force_tier,description=description,
            tags=['generated_loot', 'pill' if consumable else 'equipment', f'grade:{tier}'],**stats)
        add_item(game.player,item)
    return f'获得{roll["quality"]}遗泽“{name}”。'
