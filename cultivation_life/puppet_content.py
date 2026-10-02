"""Base-game puppet forms and tiered components for all eleven worlds."""
from functools import lru_cache

FORMS = {
    'humanoid': dict(name='人形', shell='玄甲外骨', route=None),
    'deva': dict(name='天人像', shell='净相玉躯', route='deva'),
    'dragon': dict(name='龙形', shell='盘龙鳞骨', route='naga'),
    'yaksha': dict(name='夜叉形', shell='夜叉战甲', route='yaksha'),
    'flora': dict(name='灵木形', shell='香音灵木', route='gandharva'),
    'serpent': dict(name='蛇形', shell='玄蛇柔骨', route='mahoraga'),
    'kinnara': dict(name='乐伎形', shell='合鸣音躯', route='kinnara'),
    'bird': dict(name='鸟形', shell='云翼羽骨', route='garuda'),
}
WORLDS = {
    'human': ('灵', range(1,6)), 'demon': ('魔', range(1,6)),
    'spirit': ('玄灵',range(5,9)), 'true_demon': ('真魔',range(5,9)),
    'monster_realm': ('妖元',range(5,9)), 'phantom_underworld': ('冥阴',range(5,9)),
    'hell': ('冥火',range(5,9)), 'celestial': ('仙',range(9,13)),
    'asura': ('煞',range(9,13)), 'nether': ('幽',range(9,13)), 'reincarnation': ('轮回',range(9,13)),
}
PRICES = (0, 18, 80, 360, 1600, 7200, 32000, 144000, 648000, 2900000, 13000000, 58000000, 260000000)

@lru_cache(maxsize=1)
def definitions():
    rows = {}
    components = [('core','array','阵枢核心',1.), ('core','spirit','通灵核心',1.15),
                  ('energy','crystal','元晶能源',1.), ('energy','marrow','元髓能源',1.15)]
    components += [('shell',form,info['shell'],1.) for form,info in FORMS.items()]
    for world,(prefix,tiers) in WORLDS.items():
        for tier in tiers:
            for slot,variant,name,quality in components:
                id_ = f'puppet_{world}_{tier}_{slot}_{variant}'
                axis={'core':'神识','shell':'炼体','energy':'修为'}[slot]
                shape=f"，仅适用{FORMS[variant]['name']}" if slot=='shell' else '，适用所有形态'
                rows[id_] = dict(id=id_,name=f'{tier}阶·{prefix}{name}',world=world,tier=tier,
                    slot=slot,form=variant if slot=='shell' else None,quality=quality,
                    price=round(PRICES[tier]*quality*(1.2 if slot=='core' else 1)),
                    description=f'{tier}阶傀儡材料，决定成品{axis}{shape}；材料威能系数{quality:g}。')
    return rows


def item_definitions():
    return [dict(id=r['id'],name=r['name'],description=r['description'],
                 tags=['material','puppet_material',r['slot']]) for r in definitions().values()]
