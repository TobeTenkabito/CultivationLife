"""Pure seeded situation generation. Every consequence is fixed before display."""
from __future__ import annotations

import copy
import hashlib
import json
import random

from .generated_event_schema import VERSION, PREFIX, validate_record

# Each pair describes opposite mechanisms, not two cosmetic versions of one answer.
SITUATIONS = {
    "spring": [
        "白鹿衔芝",
        "一头衔着灵芝的白鹿",
        [
            [
                "白鹿腹侧有新伤，蹄边落着断箭。它不肯靠近，却一次次把灵芝推向你，目光落在你掌中的药囊上。",
                "散去兵刃气息，替白鹿疗伤",
                "催动御兽诀，强留白鹿",
                "released"
            ],
            [
                "白鹿踏过水面却没有倒影，身后草木迅速枯萎。它衔着的灵芝鲜红欲滴，伤口下隐约有黑气翻动。",
                "散去兵刃气息，替白鹿疗伤",
                "催动御兽诀，强留白鹿",
                "stabilized"
            ]
        ]
    ],
    "array": [
        "古道借伞",
        "一位执伞的旧时行客",
        [
            [
                "行客不言，伞下却站着数道小小魂影。雨丝穿过它们的身体，远处荒坟忽然响起孩童哭声。",
                "燃一缕引魂香，送行客归乡",
                "以镇魂诀定住伞中身影",
                "released"
            ],
            [
                "伞外雨声戛然而止，你脚下的影子却向伞中缓缓爬去。行客的笑容未变，荒坟里也没有任何回应。",
                "燃一缕引魂香，送行客归乡",
                "以镇魂诀定住伞中身影",
                "stabilized"
            ]
        ]
    ],
    "casket": [
        "剑冢遗诺",
        "一柄无主古剑",
        [
            [
                "古剑旁埋着半枚同心结，剑鸣随你念出碑上姓名而渐平。远处无名坟前，另一半红结正迎风轻摇。",
                "合上同心结，了却旧诺",
                "敛神守心，斩去红结",
                "preserved"
            ],
            [
                "红结悬空而动，碑上姓名却随着你的心念变成了自己的名字。古剑无声，剑影已抵住你的胸口。",
                "合上同心结，了却旧诺",
                "敛神守心，斩去红结",
                "preserved"
            ]
        ]
    ],
    "tablet": [
        "石壁留经",
        "一面留有指痕的山壁",
        [
            [
                "壁上字迹随晨光浮现，每一笔都与山间鸟鸣相应。你静息片刻，心中杂念竟自行退去。",
                "顺着鸟鸣静观，拓下经意",
                "封闭五感，以神识照破字影",
                "preserved"
            ],
            [
                "字迹映在水中却与石壁相反，鸟鸣每响一次，你便忘却一句刚刚读过的经文。水底仿佛有人替你诵读。",
                "顺着鸟鸣静观，拓下经意",
                "封闭五感，以神识照破字影",
                "stabilized"
            ]
        ]
    ],
    "plant": [
        "灵圃候雨",
        "一株垂首的灵花",
        [
            [
                "花根湿润，叶背却结着细密黑茧。一只金色幼蝶困在茧外，翅上沾满凋落的花粉。",
                "以灵火焚去黑茧",
                "引清露润泽花根",
                "preserved"
            ],
            [
                "花根周围寸寸龟裂，金蝶守着最后一滴露水。花叶虽垂，迎光处仍透出温润灵色。",
                "以灵火焚去黑茧",
                "引清露润泽花根",
                "stabilized"
            ]
        ]
    ],
    "lamp": [
        "长夜归灯",
        "一盏漂在河面的魂灯",
        [
            [
                "灯中人影向岸边稽首，灯焰却越烧越急。上游的孤坟已有人添土，旧主所求，似乎终于有了着落。",
                "掩灯诵别，送故人归去",
                "以法力护灯，续照归路",
                "released"
            ],
            [
                "灯中人影远望上游，岸边一座新坟尚未封土。夜雾正吞没渡口，灯火每暗一分，人影便向河底沉下一寸。",
                "掩灯诵别，送故人归去",
                "以法力护灯，续照归路",
                "stabilized"
            ]
        ]
    ]
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
