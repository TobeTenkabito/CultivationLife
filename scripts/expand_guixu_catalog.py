"""Build the four post-1.1 Guixu catalogs from compact, reviewable themes.

All dungeon worlds and entry locations deliberately come from the base game.
The Guixu DLC must remain loadable without the monster or ghost DLCs.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "dlc" / "guixu-tide" / "content"


THEMES = [
    {
        "key": "bloodriver", "world": "demon", "id": "guixu_demon_bloodriver",
        "name": "血河沉渊", "entry": "nine_yin_marsh", "path": "demonic",
        "max_rank": [4, 9], "eject_rank": [5, 1], "period": 120, "first": 120,
        "lead": 12, "window": 42, "grade": 3, "base_value": 2200,
        "layer_names": ["血沫滩", "沉骨河床", "万魂漩眼", "逆血天井", "魔胎暗窟"],
        "concentrations": [
            [0.48, 1.65, 0.72, 1.05], [0.55, 1.90, 0.84, 1.22],
            [0.64, 2.20, 0.98, 1.45], [0.76, 2.55, 1.15, 1.72],
            [0.90, 2.95, 1.34, 2.05],
        ],
        "efficiencies": [
            [0.42, 1.55, 0.68, 1.05], [0.48, 1.78, 0.76, 1.18],
            [0.55, 2.02, 0.86, 1.34], [0.62, 2.28, 0.98, 1.52],
            [0.70, 2.55, 1.10, 1.72],
        ],
        "techniques": ["血河逆转经", "九阴沉魔录", "白骨潮生诀", "噬魂归墟法", "魔胎炼形篇", "血月照神术", "万煞沉河经", "逆脉遁天法", "黑莲葬海典", "无间吞潮经"],
        "equipment": ["血河魔珠", "沉骨战旗", "九阴噬魂剑", "万骸魔甲", "赤潮炼魂鼎", "无间血轮", "葬魂幡", "魔胎心镜", "逆流骨舟", "黑莲界尺", "血狱镇河碑", "沉渊万煞钟"],
        "consumable": ["血髓还元丹", "九阴定魂露", "魔胎续命丸", "万煞洗脉丹", "逆血回天散", "沉河养神液", "白骨生肌膏", "黑莲渡厄丹"],
        "plant": ["血潮莲", "九阴骨芝", "魔胎参", "噬魂藤", "黑莲魔藕", "万煞苔", "沉河鬼兰", "赤髓果", "逆脉草", "无间血桑"],
        "material": ["血河玄铁", "九阴潮晶", "万魂砂", "沉骨魔钢", "魔胎石", "黑莲髓", "噬魂铜", "逆流血玉", "无间骨金", "煞海母晶"],
        "currency": ["血纹石匣·一", "血纹石匣·二", "血纹石匣·三", "血纹石匣·四", "血纹石匣·五", "血纹石匣·六", "血纹石匣·七", "血纹石匣·八", "血纹石匣·九", "血纹石匣·极"],
        "elements": ["yin", "water", "neutral", "yin", "earth", "yin", "fire", "wind", "neutral", "water"],
    },
    {
        "key": "demon_grave", "world": "true_demon", "id": "guixu_true_demon_grave",
        "name": "太古葬魔墟", "entry": "ancient_demon_grave", "path": "demonic",
        "max_rank": [6, 9], "eject_rank": [7, 1], "period": 240, "first": 240,
        "lead": 24, "window": 56, "grade": 5, "base_value": 60000,
        "layer_names": ["黑日残岸", "神骸墓道", "太古魔腹", "葬魔王庭", "无相魔心"],
        "concentrations": [
            [0.38, 2.35, 0.72, 1.00], [0.46, 2.65, 0.86, 1.18],
            [0.56, 3.00, 1.02, 1.40], [0.68, 3.40, 1.20, 1.66],
            [0.82, 3.85, 1.42, 1.98],
        ],
        "efficiencies": [
            [0.34, 2.15, 0.66, 0.92], [0.40, 2.42, 0.76, 1.06],
            [0.47, 2.72, 0.88, 1.23], [0.55, 3.05, 1.02, 1.42],
            [0.64, 3.42, 1.18, 1.64],
        ],
        "techniques": ["黑日葬天经", "太古魔胎录", "神骸炼界篇", "万劫不灭魔身", "无相天魔观", "堕星吞海诀", "九渊魔皇典", "血焰折空遁", "葬神逆命书", "混沌魔源经"],
        "equipment": ["黑日魔轮", "太古神骸甲", "葬天魔剑", "无相心镜", "万劫镇魂钟", "堕星血旗", "九渊魔鼎", "神骨界舟", "血焰天戈", "魔皇印", "葬神碑", "混沌魔胎珠"],
        "consumable": ["黑日还魂丹", "神骸补天露", "太古魔髓丸", "万劫养神液", "无相定心丹", "堕星续命散", "九渊洗魂水", "混沌魔胎膏"],
        "plant": ["黑日魔莲", "神骸血芝", "太古魔参", "万劫魂藤", "无相心花", "堕星骨木", "九渊冥果", "葬神苔", "血焰天葵", "混沌魔桑"],
        "material": ["黑日母金", "太古神骨", "葬天魔晶", "无相魂银", "万劫血髓", "堕星玄铁", "九渊魔铜", "神骸界石", "血焰法砂", "混沌魔源核"],
        "currency": ["魔纹源匣·一", "魔纹源匣·二", "魔纹源匣·三", "魔纹源匣·四", "魔纹源匣·五", "魔纹源匣·六", "魔纹源匣·七", "魔纹源匣·八", "魔纹源匣·九", "魔纹源匣·极"],
        "elements": ["fire", "yin", "earth", "neutral", "yin", "water", "neutral", "wind", "yin", "neutral"],
    },
    {
        "key": "beast_vortex", "world": "phantom_underworld", "id": "guixu_monster_beast_vortex",
        "name": "万兽祖涡", "entry": "phantom_tide", "path": "monster",
        "max_rank": [6, 9], "eject_rank": [7, 1], "period": 180, "first": 180,
        "lead": 18, "window": 49, "grade": 5, "base_value": 52000,
        "layer_names": ["百骸浅滩", "祖血回廊", "万兽胎海", "始祖巢庭", "混沌卵室"],
        "concentrations": [
            [0.82, 0.62, 2.75, 0.78], [0.94, 0.72, 3.05, 0.92],
            [1.08, 0.84, 3.40, 1.10], [1.24, 0.98, 3.80, 1.32],
            [1.42, 1.16, 4.25, 1.58],
        ],
        "efficiencies": [
            [0.76, 0.58, 2.48, 0.72], [0.84, 0.66, 2.74, 0.84],
            [0.94, 0.76, 3.02, 0.98], [1.06, 0.88, 3.34, 1.14],
            [1.20, 1.02, 3.70, 1.34],
        ],
        "techniques": ["万兽归源经", "祖血沸海篇", "百骸不灭身", "吞天妖胎录", "星落炼形诀", "苍鳞覆海典", "雷羽裂空法", "青丘照神术", "始祖蜕命经", "混沌万象妖书"],
        "equipment": ["祖血妖珠", "万兽战旗", "苍鳞裂海戟", "百骸祖甲", "雷羽天冠", "青丘幻镜", "吞天妖鼎", "始祖骨轮", "混沌卵舟", "星落妖钟", "万灵镇脉碑", "祖涡源印"],
        "consumable": ["祖血回元丹", "万兽养神露", "百骸生肌膏", "妖胎续命丸", "雷羽淬骨液", "青丘定魂香", "苍鳞补海散", "混沌返祖丹"],
        "plant": ["祖血莲", "万兽髓芝", "百骸妖参", "吞天胎藤", "雷羽天草", "青丘梦花", "苍鳞海藻", "始祖蜕皮木", "星落妖果", "混沌卵苔"],
        "material": ["祖血源晶", "万兽骨金", "百骸玄铁", "吞天妖髓", "雷羽神铜", "青丘幻砂", "苍鳞海玉", "始祖蜕石", "星落天银", "混沌卵核"],
        "currency": ["兽纹灵匣·一", "兽纹灵匣·二", "兽纹灵匣·三", "兽纹灵匣·四", "兽纹灵匣·五", "兽纹灵匣·六", "兽纹灵匣·七", "兽纹灵匣·八", "兽纹灵匣·九", "兽纹灵匣·极"],
        "elements": ["neutral", "fire", "earth", "neutral", "metal", "water", "thunder", "yin", "wood", "neutral"],
    },
    {
        "key": "yellow_spring", "world": "hell", "id": "guixu_hell_yellow_spring",
        "name": "黄泉无底狱", "entry": "ninefold_prison", "path": "ghost",
        "max_rank": [6, 9], "eject_rank": [7, 1], "period": 210, "first": 210,
        "lead": 21, "window": 49, "grade": 5, "base_value": 56000,
        "layer_names": ["引魂滩", "忘川沉床", "罪业涡心", "无底狱门", "生死簿隙"],
        "concentrations": [
            [0.20, 0.68, 0.42, 2.35], [0.26, 0.80, 0.50, 2.65],
            [0.34, 0.94, 0.60, 3.00], [0.44, 1.10, 0.72, 3.40],
            [0.56, 1.30, 0.86, 3.85],
        ],
        "efficiencies": [
            [0.18, 0.62, 0.38, 2.16], [0.22, 0.72, 0.44, 2.42],
            [0.28, 0.84, 0.52, 2.72], [0.35, 0.98, 0.62, 3.06],
            [0.43, 1.14, 0.74, 3.44],
        ],
        "techniques": ["黄泉逆渡经", "忘川炼魂录", "无底阴身篇", "十殿照神术", "罪业噬心法", "鬼柏养魂经", "生死簿遁法", "六道归阴典", "幽关镇魄书", "轮回无岸经"],
        "equipment": ["黄泉魂灯", "忘川渡舟", "无底狱甲", "十殿判官笔", "罪业轮", "鬼柏心镜", "生死簿残页", "六道魂幡", "幽关镇魄印", "引魂天索", "轮回石碑", "无岸冥钟"],
        "consumable": ["黄泉还魂丹", "忘川养神露", "无底固魄丸", "十殿续命散", "罪业洗魂水", "鬼柏生阴膏", "六道定心香", "轮回返照丹"],
        "plant": ["黄泉彼岸花", "忘川魂藻", "无底阴芝", "十殿判木", "罪业心莲", "鬼柏灵果", "生死簿藤", "六道轮回草", "幽关冥参", "无岸魂苔"],
        "material": ["黄泉阴铁", "忘川魂晶", "无底冥金", "十殿判玉", "罪业火砂", "鬼柏心木", "生死簿银", "六道轮回石", "幽关镇魂铜", "无岸阴源核"],
        "currency": ["冥纹灵匣·一", "冥纹灵匣·二", "冥纹灵匣·三", "冥纹灵匣·四", "冥纹灵匣·五", "冥纹灵匣·六", "冥纹灵匣·七", "冥纹灵匣·八", "冥纹灵匣·九", "冥纹灵匣·极"],
        "elements": ["yin", "water", "earth", "yin", "fire", "wood", "wind", "neutral", "metal", "yin"],
    },
]


def read(name: str) -> dict:
    return json.loads((CONTENT / name).read_text(encoding="utf-8"))


def write(name: str, value: dict) -> None:
    (CONTENT / name).write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
    )


def weights(index: int, count: int) -> dict[str, int]:
    ratio = index / max(1, count - 1)
    if ratio < .28:
        values = (6, 3, 1, 0)
    elif ratio < .58:
        values = (3, 4, 2, 1)
    elif ratio < .80:
        values = (1, 3, 4, 2)
    else:
        values = (0, 1, 3, 6)
    return dict(zip(("outer", "middle", "inner", "final"), values))


def values(theme: dict, count: int) -> list[int]:
    return [int(round(theme["base_value"] * (1.48 ** index), -1)) for index in range(count)]


def build() -> None:
    guixu = read("guixu_tide.json")
    item_doc = read("items.json")
    technique_doc = read("techniques.json")
    new_ids = {theme["id"] for theme in THEMES}
    new_keys = tuple(f"guixu_{theme['key']}_" for theme in THEMES)
    new_technique_prefixes = tuple(f"TECH_GUIXU_{theme['key'].upper()}_" for theme in THEMES)
    guixu["dungeons"] = [row for row in guixu["dungeons"] if row["id"] not in new_ids]
    item_doc["items"] = [row for row in item_doc["items"] if not row["id"].startswith(new_keys)]
    technique_doc["techniques"] = [
        row for row in technique_doc["techniques"]
        if not row["id"].startswith(new_technique_prefixes)
    ]

    for theme in THEMES:
        layers = []
        for index, (layer_id, travel_days, roster_size) in enumerate(zip(
            ("outer", "middle", "inner", "final", "secret"),
            (1, 3, 4, 5, 2), (12, 8, 5, 3, 0),
        )):
            spirit, demon, monster, yin = theme["concentrations"][index]
            es, ed, em, ey = theme["efficiencies"][index]
            layers.append({
                "id": layer_id, "name": theme["layer_names"][index],
                "travel_days": travel_days, "roster_size": roster_size,
                "qi_concentrations": {"spirit": spirit, "demon": demon, "monster": monster, "yin": yin},
                "qi_gain_efficiencies": {"spirit": es, "demon": ed, "monster": em, "yin": ey},
            })

        pool = []
        technique_values = values(theme, 10)
        for index, name in enumerate(theme["techniques"]):
            number = index + 1
            content_id = f"TECH_GUIXU_{theme['key'].upper()}_{number:02d}"
            technique_doc["techniques"].append({
                "id": content_id, "name": name, "path": theme["path"],
                "element": theme["elements"][index],
                "grade": min(8, theme["grade"] + index // 4), "level": 1,
                "opportunity_bonus": round(.24 + theme["grade"] * .035 + index * .018, 3),
                "hp_bonus": round(.20 + theme["grade"] * .03 + index * .014, 3),
                "mp_bonus": round(.22 + theme["grade"] * .034 + index * .016, 3),
                "combat_bonus": int(theme["base_value"] * (.7 + index * .24)),
                "karma_multiplier": 1.0,
            })
            pool.append({
                "id": f"{theme['key']}_technique_{number:02d}", "name": name,
                "category": "technique", "kind": "technique",
                "exclusive_source": "guixu_tide", "content_id": content_id,
                "tier": "major" if index < 2 else "normal", "value": technique_values[index],
                "layer_weights": weights(index, 10),
            })

        category_specs = (("equipment", 12), ("consumable", 8), ("plant", 10), ("material", 10))
        for category, count in category_specs:
            category_values = values(theme, count)
            for index, name in enumerate(theme[category]):
                number = index + 1
                item_id = f"guixu_{theme['key']}_{category}_{number:02d}"
                item = {
                    "id": item_id, "name": name,
                    "description": f"{name}出自{theme['name']}，无法从归墟之外的途径获得。",
                    "tags": ["guixu_tide", theme["key"], category, "treasure"],
                }
                if category == "equipment":
                    item.update(
                        combat_bonus=int(theme["base_value"] * (.45 + index * .18)),
                        hp_bonus=int(theme["grade"] * 22 * (index + 1)),
                        mp_bonus=int(theme["grade"] * 26 * (index + 1)),
                    )
                elif category == "consumable":
                    item["tags"] = ["guixu_tide", "guixu_consumable", theme["key"], "consumable", "pill"]
                elif category == "plant":
                    item.update(
                        hp_bonus=int(theme["grade"] * 24 * (index + 1)),
                        mp_bonus=int(theme["grade"] * 28 * (index + 1)),
                        opportunity_bonus=round(.012 + .004 * (index + 1), 3),
                        plant_id=item_id, plant_years=int(300 * theme["grade"] + 500 * index),
                        plant_kind="guixu", plant_value=category_values[index],
                    )
                    item["tags"] = ["guixu_tide", theme["key"], "spirit_plant", "treasure"]
                else:
                    item["combat_bonus"] = int(theme["base_value"] * .06 * (index + 1))
                    item["tags"] = ["guixu_tide", theme["key"], "crafting_material", "treasure"]
                item_doc["items"].append(item)
                pool.append({
                    "id": f"{theme['key']}_{category}_{number:02d}", "name": name,
                    "category": category, "kind": "item", "exclusive_source": "guixu_tide",
                    "content_id": item_id, "tier": "major" if index < 2 and category in {"equipment", "material"} else "normal",
                    "value": category_values[index], "layer_weights": weights(index, count),
                })

        currency_values = values(theme, 10)
        for index, name in enumerate(theme["currency"]):
            pool.append({
                "id": f"{theme['key']}_currency_{index + 1:02d}", "name": name,
                "category": "currency", "kind": "item_bundle", "content_id": "spirit_stone",
                "quantity": currency_values[index], "tier": "normal", "value": currency_values[index],
                "layer_weights": weights(index, 10),
            })

        guixu["dungeons"].append({
            "id": theme["id"], "name": theme["name"], "world": theme["world"],
            "entry_location_id": theme["entry"], "max_entry_rank": theme["max_rank"],
            "eject_rank": theme["eject_rank"], "period_years": theme["period"],
            "first_open_year": theme["first"], "announce_lead_years": theme["lead"],
            "window_days": theme["window"], "layers": layers, "treasure_pool": pool,
        })

    write("items.json", item_doc)
    write("techniques.json", technique_doc)
    write("guixu_tide.json", guixu)


if __name__ == "__main__":
    build()
