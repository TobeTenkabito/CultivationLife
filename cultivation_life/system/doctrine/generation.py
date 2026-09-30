"""Versioned, deterministic content compiler; no game/global registry access."""
from __future__ import annotations

import random
from typing import Any, Mapping

from ..combat.contracts import VoisinageDefinition, number


def rng_for(seed: int, version: int, stream: str) -> random.Random:
    return random.Random(f"{seed}:celestial-doctrine:v{version}:{stream}")


def validate_content(config: Mapping[str, Any]) -> None:
    if (config.get("world") != "celestial" or config.get("count") != 25
            or config.get("max_level") != 9 or config.get("voisinage_level") != 4
            or config.get("origin_level") != 5 or config.get("manual_count") != [3, 8]):
        raise ValueError("道统须配置仙界 25 门、Lv9 上限、Lv4 仙域、Lv5 本源及 3—8 门功法")
    if not 1 <= len(config.get("fixed", [])) <= 2:
        raise ValueError("固定道统须为一至两门")
    themes = config.get("themes", [])
    if len(themes) < 25 or len({t["id"] for t in themes}) != len(themes):
        raise ValueError("道统主题词库至少须有 25 种不重复主题")
    for theme in themes:
        if len(set(theme["images"])) < 6 or not theme["description"]:
            raise ValueError("每个道统主题须包含六个以上意象及背景描述")
    words = config["words"]
    for key, minimum in {"prefixes": 48, "manual_verbs": 40, "manual_suffixes": 20,
                         "voisinage_suffixes": 16, "ability_verbs": 24, "practice_images": 12,
                         "practice_endings": 8, "acquisition_places": 12}.items():
        if len(set(words[key])) < minimum:
            raise ValueError(f"道统词库 {key} 过于贫乏")
    if len(words["stage_titles"]) != 9 or any(len(set(row)) < 8 for row in words["stage_titles"]):
        raise ValueError("九级道统须各有八种以上阶段题名")
    for key, count in (("level_years", 9), ("level_realms", 9), ("conversion_years", 5)):
        if len(config[key]) != count:
            raise ValueError(f"Invalid {key}")
        for value in config[key]:
            number(value, key, minimum=1)
    rules = config["cultivation"]
    rates, pity = rules["success_rates"], rules["pity_steps"]
    if (len(rates) != 9 or any(not 0 < number(x, "success rate") < 1 for x in rates)
            or any(a <= b for a, b in zip(rates, rates[1:]))
            or pity != [.05] * 3 + [.04] * 3 + [.02] * 3):
        raise ValueError("道统成功率须逐层递减，保底增量须为 5%/4%/2%")
    if rules["veins_per_layer"] != 3 or rules["veins_per_realm"] != 27:
        raise ValueError("每层三条仙脉，每境二十七条")
    for key in ('creation_traces', 'study_traces_per_level'):
        if type(rules['fusion'][key]) is not int or rules['fusion'][key] <= 0:
            raise ValueError('合练与参悟仙痕须为正整数')
    for key in ("vein_opportunity_base", "vein_opportunity_step", "vein_trace_base", "vein_trace_step",
                "voisinage_max_training", "voisinage_opportunity_base", "voisinage_trace_base",
                "annotation_price", "explore_price"):
        if type(rules[key]) is not int or rules[key] <= 0:
            raise ValueError(f"Invalid cultivation parameter {key}")
    if rules['trace_gain_chance'] != .07 or len(rules['vein_success_rates']) != 9:
        raise ValueError('仙痕判定须为 7%，仙脉须配置九层成功率')
    for rate in [*rules['vein_success_rates'], rules['vein_pity_step']]:
        if not 0 < number(rate, 'vein probability') <= 1:
            raise ValueError('仙脉概率无效')
    stages = rules['golden_light']['stages']
    if [s['resistance'] for s in stages] != [.01, .02, .04, .06, .10]:
        raise ValueError('金光五阶抵抗比例须为 1%/2%/4%/6%/10%')
    if stages[0]['recipe'] or any(not s['recipe'] for s in stages[1:]):
        raise ValueError('微光随仙躯解锁，其后四阶须有资材配方')
    for stage in stages:
        for quantity in stage['recipe'].values():
            if type(quantity) is not int or quantity <= 0:
                raise ValueError('金光资材数量须为正整数')
    for values in rules['vein_intrinsic'].values():
        if len(values) != 4 or any(type(x) is not int or x <= 0 for x in values):
            raise ValueError('四境仙脉须分别配置正整数本源成长')
    body = rules['body']
    if body['required_training'] != 100 or body['golden_light_level'] != 20:
        raise ValueError('仙躯须炼体百层起修、二十层激发金光')
    for key in ('max_level', 'hp_per_level', 'mp_per_level'):
        number(body[key], key, minimum=1)
    if body['max_level'] < body['golden_light_level']:
        raise ValueError('仙躯上限不能低于金光门槛')
    for key in ('base_chance', 'chance_step', 'minimum_chance', 'pity_step'):
        if not 0 < number(body[key], key) <= 1:
            raise ValueError('仙躯概率无效')
    if not body['manuals'] or len({m['id'] for m in body['manuals']}) != len(body['manuals']):
        raise ValueError('仙躯功法须具有独立标识')
    supplies = {s['id'] for s in body['supplies']}
    for manual in body['manuals']:
        if not manual['recipe'] or set(manual['recipe']) - supplies:
            raise ValueError('仙躯配方引用了不可获得的药材')
        number(manual['price'], 'manual price', minimum=1)
        if not 0 <= number(manual['chance_bonus'], 'manual bonus') < 1:
            raise ValueError('仙躯功法概率加成无效')
        for quantity in manual['recipe'].values():
            if type(quantity) is not int or quantity <= 0:
                raise ValueError('药材数量须为正整数')
    if not 0 < number(rules["voisinage_training_gain"], "voisinage training gain") <= .1:
        raise ValueError("额外邻域温养不能替代道统成就")


def generate(seed: int, config: Mapping[str, Any], realm_power: Mapping[int, float]) -> dict[str, Any]:
    """Freeze all future stages once. Separate streams isolate names and mechanics."""
    validate_content(config)
    version, words = config["generation_version"], config["words"]
    themes = {row["id"]: row for row in config["themes"]}
    selected = rng_for(seed, version, "themes").sample(list(themes), 25 - len(config["fixed"]))
    slots = [*config["fixed"], *({"id": f"generated_{i + 1:02d}", "theme": theme}
                               for i, theme in enumerate(selected))]
    definitions, used_names = {}, set()
    for slot in slots:
        fixed = "name" in slot
        key = f"celestial:{slot['id']}"
        local_seed = 0 if fixed else seed
        names = rng_for(local_seed, version, f"{key}:names")
        mechanics = rng_for(local_seed, version, f"{key}:mechanics")
        theme = themes[slot["theme"]]
        name = slot.get("name") or names.choice(words["prefixes"]) + names.choice(theme["images"]) + names.choice(words["doctrine_suffixes"])
        if name in used_names:
            name = names.choice(theme["images"]) + name
        used_names.add(name)
        primary = slot.get("feature") or mechanics.choice(list(config["features"]))
        compatible = {
            "fortify": ["retaliate", "frugal", "shelter"], "opening": ["sacrifice", "execution", "frugal"],
            "retaliate": ["fortify", "shelter", "execution"], "sacrifice": ["opening", "execution", "frugal"],
            "frugal": ["fortify", "shelter", "retaliate"], "shelter": ["fortify", "frugal", "retaliate"],
            "execution": ["opening", "sacrifice", "retaliate"],
        }
        evolution = [primary, *mechanics.sample(compatible[primary], 2)]
        stability, incursion = mechanics.uniform(85, 125), mechanics.uniform(85, 125)
        if primary in {"fortify", "retaliate", "shelter"}:
            stability *= 1.2
            incursion *= .9
        elif primary in {"opening", "sacrifice", "execution"}:
            incursion *= 1.2
            stability *= .9
        authority = mechanics.uniform(85, 120)
        effect = mechanics.choice(["strike", "suppress"]) if primary == "execution" else mechanics.choice(["strike", "suppress", "seal"])
        voisinage_name = names.choice(words["prefixes"]) + names.choice(theme["images"]) + names.choice(words["voisinage_suffixes"])
        stages = []
        for level in range(1, 10):
            stage_rng = rng_for(local_seed, version, f"{key}:stage:{level}")
            growth = 1.48 ** max(0, level - 4)
            traits = [{"kind": kind, "value": round(.08 + .02 * level, 3)}
                      for kind in evolution[:1 if level < 6 else 2 if level < 8 else 3]] if level >= 4 else []
            feature_descriptions = [config["features"][t["kind"]]["description"] for t in traits]
            voisinage = None
            if level >= 4:
                voisinage = dict(id=f"{key}:voisinage", name=voisinage_name, attainment=key, required_level=4,
                              strength=1, stability=round(stability * growth * stage_rng.uniform(.94, 1.06), 3),
                              incursion=round(incursion * growth * stage_rng.uniform(.94, 1.06), 3),
                              authority=round(authority * 1.12 ** (level - 4) * stage_rng.uniform(.96, 1.04), 3), opening_cost=round(100 + level * 15),
                              upkeep_cost=round(20 + level * 5), effect=effect, effect_cost=round(20 + level * 4),
                              effect_power=.32, max_targets=min(4, 1 + (level - 4) // 2),
                              extra_target_cost=15, max_investment=80, features=traits)
                # strength is retained only for old providers; generated fields
                # compare explicit incursion against explicit stability.
                VoisinageDefinition(**voisinage)
            title = names.choice(words["stage_titles"][level - 1])
            stages.append(dict(level=level, title=title, years=config["level_years"][level - 1],
                               realm=config["level_realms"][level - 1], voisinage=voisinage,
                               description=(f"{names.choice(words['practice_images'])}，{names.choice(words['practice_endings'])}。"
                                            + ("此层凝成仙域。" if level == 4 else "此层将确定唯一的本源归属。" if level == 5 else "")),
                               ability_name=names.choice(theme["images"]) + names.choice(words["ability_verbs"]),
                               features=feature_descriptions))
        book_rng = rng_for(local_seed, version, f"{key}:manuals")
        manuals = []
        manual_origins = {}
        for index in range(book_rng.randint(3, 8)):
            grade = 9 if index == 0 else book_rng.choice([9, 10, 11, 12])
            preference = ("main", "support", "combat")[index % 3]
            title = names.choice(words["prefixes"]) + names.choice(theme["images"]) + names.choice(words["manual_verbs"]) + names.choice(words["manual_suffixes"])
            for attempt in range(16):
                if title not in used_names:
                    break
                title = names.choice(words["prefixes"]) + names.choice(theme["images"]) + names.choice(words["manual_verbs"]) + names.choice(words["manual_suffixes"])
            if title in used_names:
                title = f"{title}·{slot['id']}-{index + 1}"
            used_names.add(title)
            base = float(realm_power[grade])
            manuals.append(dict(id=f"{key}:manual:{index + 1}", doctrine_id=key, name=title,
                                path="dao", element="neutral", grade=grade, level=1, category="spiritual",
                                growth_preference=preference, requires_immortal_power=True,
                                immortal_power_cost=round(.025 + .005 * (grade - 9), 3),
                                opportunity_bonus=round(book_rng.uniform(.25, .45) * (grade - 7), 3),
                                hp_bonus=round(book_rng.uniform(.18, .3) * (grade - 7), 3),
                                mp_bonus=round(book_rng.uniform(.2, .35) * (grade - 7), 3),
                                combat_bonus=round(base * book_rng.uniform(.035, .065), 1),
                                effective_worlds=["celestial"],
                                sources={"spirit": 1.0}, combat_requirements={"source": {"id": "spirit", "op": ">=", "level": 30}}))
            manual_origins[manuals[-1]["id"]] = names.choice(words["acquisition_places"])
        definitions[key] = dict(id=key, name=name, fixed=fixed, theme=theme["name"],
                                description=theme["description"], stages=stages, manuals=manuals, manual_origins=manual_origins)
    from .effects import enrich_effects, ensure_offensive_doctrine
    enrich_effects(definitions)
    ensure_offensive_doctrine(definitions, seed, version)
    return dict(version=version, effects_schema=1, offensive_schema=1, world="celestial", definitions=definitions, player={
        "progress": {}, "origin": None, "active": None, "conversion_progress": 0,
    })
