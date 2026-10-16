"""Promote world geography and extend Guixu catalogs for the 1.34 release."""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(path):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))

def write(path, data):
    (ROOT / path).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def merge(base, extra):
    for key, value in extra.items():
        if key in base and isinstance(value, dict):
            merge(base[key], value)
        elif key in base and isinstance(value, list):
            base[key].extend(x for x in value if x not in base[key])
        else:
            base[key] = copy.deepcopy(value)

def build():
    maps = read("content/maps.json")
    for package in ("monster-bloodlines", "ghost-reincarnation"):
        path = f"dlc/{package}/content/maps.json"
        doc = read(path)
        merge(maps["worlds"], doc["worlds"])
        doc["worlds"] = {}
        write(path, doc)
    write("content/maps.json", maps)
    world = read("content/world.json")
    monster = read("dlc/monster-bloodlines/content/world.json")
    for key in ("world_names", "world_profiles", "start_worlds", "cultivation_routes"):
        extra = monster["systems"].pop(key, {})
        if key in {"start_worlds", "cultivation_routes"}:
            world["systems"].setdefault(key, {}).update(extra)
        else:
            merge(world["systems"].setdefault(key, {}), extra)
    write("content/world.json", world)
    write("dlc/monster-bloodlines/content/world.json", monster)
    tianji = read("dlc/tianji-artifacts/content/world.json")
    config = tianji["systems"]["tianji_artifacts"]
    config["base_worlds"] = list(maps["worlds"])
    for name in maps["worlds"]:
        tier = world["systems"]["world_profiles"][name].get("tier", 1)
        config["world_replica_caps"][name] = {1: .2, 2: .6, 3: .9}.get(tier, .9)
    write("dlc/tianji-artifacts/content/world.json", tianji)

    # Keep the six existing dungeons and their unique treasures unchanged.
    import expand_guixu_catalog as catalog
    # Names are curated in the base catalogs. Rebuilding a dungeon must not
    # replace them with a shared prefix plus a repeated functional suffix.
    canonical_names = {row['id']: row['name'] for document, key in (
        ('content/items.json', 'items'), ('content/techniques.json', 'techniques'),
    ) for row in read(document)[key]}
    themes = []
    additions = [
        ("monster_realm", "ancestral_mountain", "妖祖沉庭", "monster", "祖灵", 6, 42000,
         ["祖山裂隙", "兽骨古道", "妖庭沉殿", "万灵祖座", "初血秘窟"]),
        ("celestial", "law_sea", "天律沉宫", "dao", "天律", 11, 1200000,
         ["碎律海岸", "仙舟遗港", "失序天廊", "沉天法座", "无字律藏"]),
        ("asura", "destruction_sea", "修罗劫海", "demonic", "劫刃", 11, 1200000,
         ["赤潮断岸", "万兵海沟", "不灭战冢", "劫主残庭", "寂灭刃藏"]),
        ("nether", "dragon_origin_sea", "太初龙渊", "monster", "龙源", 11, 1300000,
         ["鳞沙浅洲", "古龙沉脊", "源血潮眼", "初龙遗庭", "万祖心室"]),
        ("reincarnation", "timeless_grave", "无时轮回墟", "ghost", "溯魂", 11, 1250000,
         ["旧梦墓岸", "逆岁碑廊", "千生魂海", "无时轮座", "未生秘藏"]),
    ]
    for name, entry, title, path, prefix, rank, value, layers in additions:
        source = catalog.THEMES[2 if path == "monster" else 3 if path == "ghost" else 1]
        theme = copy.deepcopy(source)
        theme.update(key=name, world=name, id=f"guixu_{name}_depths", name=title, entry=entry,
                     path=path, max_rank=[rank, world["realms"][rank]["layers"]], eject_rank=[rank + 1, 1],
                     period=300 if rank > 8 else 180, first=300 if rank > 8 else 180,
                     grade=min(8, rank), base_value=value, layer_names=layers)
        for category, count in dict(techniques=10, equipment=12, consumable=8, plant=10, material=10).items():
            content_prefix = f'TECH_GUIXU_{name.upper()}' if category == 'techniques' else f'guixu_{name}_{category}'
            theme[category] = [canonical_names[f'{content_prefix}_{i:02d}'] for i in range(1, count + 1)]
        theme['currency'] = [f'{prefix}灵匣·{i}' for i in range(1, 11)]
        environment = world["systems"]["world_profiles"][name]["qi_concentrations"]
        theme["concentrations"] = [[round(environment[q] * (1.1 + i * .15), 2) for q in ("spirit", "demon", "monster", "yin")] for i in range(5)]
        theme["efficiencies"] = copy.deepcopy(theme["concentrations"])
        themes.append(theme)
    catalog.THEMES = themes
    catalog.build()

if __name__ == "__main__":
    build()
