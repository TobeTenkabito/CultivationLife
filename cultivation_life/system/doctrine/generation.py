"""Versioned, deterministic content compiler; no game/global registry access."""
from __future__ import annotations

import random
from typing import Any, Mapping

from ..combat.contracts import DomainDefinition, number


def rng_for(seed: int, version: int, stream: str) -> random.Random:
    return random.Random(f"{seed}:celestial-doctrine:v{version}:{stream}")


def validate_content(config: Mapping[str, Any]) -> None:
    if (config.get("world") != "celestial" or config.get("count") != 25
            or config.get("max_level") != 9 or config.get("domain_level") != 4
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
                         "domain_suffixes": 16, "ability_verbs": 24, "practice_images": 12,
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
        domain_name = names.choice(words["prefixes"]) + names.choice(theme["images"]) + names.choice(words["domain_suffixes"])
        stages = []
        for level in range(1, 10):
            stage_rng = rng_for(local_seed, version, f"{key}:stage:{level}")
            growth = 1.48 ** max(0, level - 4)
            traits = [{"kind": kind, "value": round(.08 + .02 * level, 3)}
                      for kind in evolution[:1 if level < 6 else 2 if level < 8 else 3]] if level >= 4 else []
            feature_descriptions = [config["features"][t["kind"]]["description"] for t in traits]
            domain = None
            if level >= 4:
                domain = dict(id=f"{key}:domain", name=domain_name, attainment=key, required_level=4,
                              strength=1, stability=round(stability * growth * stage_rng.uniform(.94, 1.06), 3),
                              incursion=round(incursion * growth * stage_rng.uniform(.94, 1.06), 3),
                              authority=round(authority * 1.12 ** (level - 4) * stage_rng.uniform(.96, 1.04), 3), opening_cost=round(100 + level * 15),
                              upkeep_cost=round(20 + level * 5), effect=effect, effect_cost=round(20 + level * 4),
                              effect_power=.32, max_targets=min(4, 1 + (level - 4) // 2),
                              extra_target_cost=15, max_investment=80, features=traits)
                # strength is retained only for old providers; generated fields
                # compare explicit incursion against explicit stability.
                DomainDefinition(**domain)
            title = names.choice(words["stage_titles"][level - 1])
            stages.append(dict(level=level, title=title, years=config["level_years"][level - 1],
                               realm=config["level_realms"][level - 1], domain=domain,
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
    return dict(version=version, world="celestial", definitions=definitions, player={
        "progress": {}, "origin": None, "active": None, "conversion_progress": 0,
    })
