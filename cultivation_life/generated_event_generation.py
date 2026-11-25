"""Pure seeded situation generation. Every consequence is fixed before display."""
from __future__ import annotations
from .definition_data import definition as _content_definition

import copy
import hashlib
import json
import random

from .generated_event_schema import VERSION, PREFIX, validate_record

# Each pair describes opposite mechanisms, not two cosmetic versions of one answer.


SITUATIONS = _content_definition(__name__, "SITUATIONS")


def generate(seed, sequence, source, reward_pool):
    """Accept only an explicit scene and legal reward descriptors, never a game."""
    identity = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    key = f'{seed}:generated-event:v{VERSION}:{sequence}:{identity}'
    situation_rng = random.Random(key + ':situation')
    reward_rng = random.Random(key + ':reward')
    template_id = situation_rng.choice(sorted(SITUATIONS))
    variant = situation_rng.randrange(2)
    title, subject, variants = SITUATIONS[template_id]
    clue, first, second, signal = variants[variant]
    # Sorting makes generation independent of mutable catalog iteration order.
    pool = sorted(reward_pool, key=lambda row: (row['kind'], row['content_id']))
    if not pool:
        raise ValueError('当前地点没有合法的随机异闻奖励')
    reward = copy.deepcopy(reward_rng.choice(pool))
    cost = situation_rng.choice((.04, .06, .08))
    injury = situation_rng.choice((.04, .06, .08))
    opportunity = situation_rng.randint(1, 3) * max(1, source['realm_index'])
    choices = []
    for index, label in enumerate((first, second)):
        correct = index == variant
        choices.append({
            'id': 'route_a' if index == 0 else 'route_b',
            'text': f'{label}（消耗 {cost:.0%} 法力上限；处理失当可能损失 {injury:.0%} 气血上限）',
            'hp_cost': 0 if correct else injury, 'mp_cost': cost,
            'opportunity': opportunity if correct else 0,
            'reward': copy.deepcopy(reward) if correct else None,
            'result_text': (f'你应下了{subject}牵系的因缘，一份遗泽留在掌中。'
                            if correct else f'你误解了{subject}背后的因缘，遭到反噬，机缘随之散去。'),
            'signal': signal if correct else 'damaged',
        })
    choices.append({'id': 'leave', 'text': '记下线索，放弃取藏', 'hp_cost': 0, 'mp_cost': 0,
                    'opportunity': 0, 'reward': None, 'result_text': '你记下所见，平安离开。', 'signal': 'left'})
    situation_rng.shuffle(choices)
    record = {
        'id': f'{PREFIX}{sequence}_{hashlib.sha256(key.encode()).hexdigest()[:16]}',
        'version': VERSION, 'sequence': sequence, 'source': copy.deepcopy(source),
        'template_id': template_id, 'variant': variant, 'title': title,
        'body': f'你在{source["location_name"]}发现{subject}。{clue} '
                '两种处理都需要法力；判断失当会受创并损毁遗藏，也可选择放弃。',
        'choices': choices,
    }
    validate_record(record)
    return record
