"""Pure, bounded player cultivation rules; no engine or global registries."""
from dataclasses import replace

AXES = ("stability", "incursion", "authority")


def chance(progress, rules):
    target = int(progress.get("level", 0)) + 1
    if target > 9:
        return 1.0
    failures = int(progress.get("failures", {}).get(str(target), 0))
    return min(1.0, rules["success_rates"][target - 1] + failures * rules["pity_steps"][target - 1])


def prerequisites(record, key, manual_level):
    progress = record.get("progress", {}).get(key, {})
    target = int(progress.get("level", 0)) + 1
    if target > 9:
        raise ValueError("此道统已达 Lv9")
    if manual_level < target:
        raise ValueError(f"须先将此道统的一部功法修至 Lv{target}")
    if target not in record.get("annotations", {}).get(key, []):
        raise ValueError(f"须先取得此道统 Lv{target} 的注解")


def attempt(progress, definition, years, origin, rules, roll):
    """One action, at most one revelation. Failed time is spent; notes persist."""
    level = int(progress.get("level", 0))
    if level >= 9 or (level >= 4 and origin not in (None, definition["id"])):
        return "blocked"
    required = definition["stages"][level]["years"]
    progress["experience"] = min(required, progress.get("experience", 0) + max(0, years))
    if progress["experience"] < required:
        return "training"
    if level == 4 and not origin:
        return "origin_required"
    probability = chance(progress, rules)
    progress["attempts"] = progress.get("attempts", 0) + 1
    progress["experience"] = 0
    if probability >= 1 or roll < probability:
        progress["level"] = level + 1
        return "success"
    failures = progress.setdefault("failures", {})
    failures[str(level + 1)] = failures.get(str(level + 1), 0) + 1
    return "failed"


def vein_cost(realm, opened, rules):
    ordinal = (realm - 9) * rules["veins_per_realm"] + opened
    return {"opportunity": rules["vein_opportunity_base"] + ordinal * rules["vein_opportunity_step"],
            "traces": rules["vein_trace_base"] + ordinal * rules["vein_trace_step"]}


def training_cost(level, rules):
    return {"opportunity": rules["voisinage_opportunity_base"] * (level + 1),
            "traces": rules["voisinage_trace_base"] * (level + 1)}


def immortal_breakthrough_cost(realm, layer, rules):
    """A ritual fee after opening veins, independent of the legacy progress bar."""
    base = rules['breakthrough_opportunity_base'][realm - 9]
    return round(base * (1 + rules['breakthrough_opportunity_layer_step'] * max(0, min(8, layer - 1))))


def cultivated_voisinage(definition, training, gain=.03):
    # Training is additive to each base dimension, not a replacement for doctrine.
    from .voisinage_training import project
    tempered = replace(definition, **{axis: getattr(definition, axis) * (1 + gain * training.get(axis, 0))
                                      for axis in AXES if getattr(definition, axis) is not None})
    return project(tempered, training)
