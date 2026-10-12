"""Pure seeded situation generation. Every consequence is fixed before display."""
from __future__ import annotations

import copy
import hashlib
import json
import random

from .generated_event_schema import VERSION, PREFIX, validate_record

# Each pair describes opposite mechanisms, not two cosmetic versions of one answer.
SITUATIONS = {
    'spring': ('逆流灵泉', '青石泉眼', (
        ('泉水不断涨高，溢出的灵光冲击石槽；槽上旧刻写着“满则疏”。', '沿石槽疏导灵流', '向泉眼注入灵力', 'released'),
        ('泉眼已近干涸，石槽完整，却没有灵光流出；槽上旧刻写着“竭则续”。', '沿石槽疏导灵流', '向泉眼注入灵力', 'stabilized'),
    )),
    'array': ('残阵回路', '三环阵枢', (
        ('外环灵流持续涌向中心，中心阵纹已发烫；石盘刻着“外涌则断”。', '切断外环回路', '接通残缺回路', 'released'),
        ('中心阵纹黯淡，外环有一处明显断口；石盘刻着“断流则接”。', '切断外环回路', '接通残缺回路', 'stabilized'),
    )),
    'casket': ('封匣灵压', '玄纹石匣', (
        ('匣盖向外鼓起，缝隙喷出细碎灵火；锁扣刻着“胀则泄”。', '打开泄压孔再解封', '补入灵力再解封', 'preserved'),
        ('锁扣陷入内侧，灵纹因失去供给而闭死；锁扣刻着“枯则充”。', '打开泄压孔再解封', '补入灵力再解封', 'preserved'),
    )),
    'tablet': ('古碑拓印', '无名古碑', (
        ('文字浮在碑面，背后的导灵纹已经安静；碑侧写着“文显可拓”。', '以灵力拓印碑面', '引导背面灵纹', 'preserved'),
        ('文字深陷碑内，背面灵纹紊乱闪烁；碑侧写着“脉定文出”。', '以灵力拓印碑面', '引导背面灵纹', 'stabilized'),
    )),
    'plant': ('遗圃灵植', '石阶遗圃', (
        ('叶面布满黑斑，根旁湿土充足；遗圃木牌写着“浊叶先净”。', '净化叶面浊气', '润泽根旁土壤', 'preserved'),
        ('叶面清亮，根旁土壤却已开裂；遗圃木牌写着“燥根先润”。', '净化叶面浊气', '润泽根旁土壤', 'stabilized'),
    )),
    'lamp': ('长明灵灯', '回光灯座', (
        ('灯焰越过灯罩，灯座浮现裂纹；罩内写着“焰盛则收”。', '收拢散逸灯焰', '续入灯座灵力', 'released'),
        ('灯焰几近熄灭，灯罩却完好无损；罩内写着“焰衰则续”。', '收拢散逸灯焰', '续入灯座灵力', 'stabilized'),
    )),
}


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
            'result_text': (f'你顺着线索处理{subject}，遗藏得以保存。'
                            if correct else f'你的处理与{subject}的实际状态相反，灵流失衡，遗藏损毁。'),
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
