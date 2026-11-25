"""Base-game puppet forms and tiered components for all eleven worlds."""
from .definition_data import definition as _content_definition
from functools import lru_cache

FORMS = _content_definition(__name__, "FORMS")
WORLDS = {
    'human': ('青岚', range(1,6)), 'demon': ('赤煞', range(1,6)),
    'spirit': ('玄灵',range(5,9)), 'true_demon': ('真魔',range(5,9)),
    'monster_realm': ('妖元',range(5,9)), 'phantom_underworld': ('冥阴',range(5,9)),
    'hell': ('冥火',range(5,9)), 'celestial': ('云笈',range(9,13)),
    'asura': ('烬海',range(9,13)), 'nether': ('烛夜',range(9,13)), 'reincarnation': ('三生',range(9,13)),
}
PRICES = (0, 18, 80, 360, 1600, 7200, 32000, 144000, 648000, 2900000, 13000000, 58000000, 260000000)

@lru_cache(maxsize=1)
def definitions():
    rows = {}
    components = _content_definition(__name__, "definitions_components")
    components += [('shell',form,info['shell'],1.) for form,info in FORMS.items()]
    for world,(prefix,tiers) in WORLDS.items():
        for tier in tiers:
            for slot,variant,name,quality in components:
                id_ = f'puppet_{world}_{tier}_{slot}_{variant}'
                axis={'core':'神识','shell':'炼体','energy':'修为'}[slot]
                shape=f"，仅适用{FORMS[variant]['name']}" if slot=='shell' else '，适用所有形态'
                rows[id_] = dict(id=id_,name=f'{prefix}{name}（{tier}阶）',world=world,tier=tier,
                    slot=slot,form=variant if slot=='shell' else None,quality=quality,
                    price=round(PRICES[tier]*quality*(1.2 if slot=='core' else 1)),
                    description=f'{tier}阶傀儡材料，决定成品{axis}{shape}；材料威能系数{quality:g}。')
    return rows


def item_definitions():
    return [dict(id=r['id'],name=r['name'],description=r['description'],
                 tags=['material','puppet_material',r['slot']]) for r in definitions().values()]
