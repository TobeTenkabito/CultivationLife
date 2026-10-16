"""Compatibility for renamed catalog identifiers within schema 10.

Pure decoding only: no files, catalog imports, RNG, stats, or save-schema upgrade.
Only exact identifiers in reference fields/maps are changed. Player text, logs,
custom artifact names and unknown identifiers remain untouched.
"""
from __future__ import annotations

from typing import Any


LEGACY_CONTENT_IDS = {
    'TECH_COMMON_CORE': 'TECH_BAOPU_CANON',
    'TECH_COMMON_LUO': 'TECH_XUANDU_CANON',
    'TECH_COMMON_NASCENT': 'TECH_YELLOW_COURT_INNER',
    'TECH_COMMON_SPIRIT': 'TECH_MYSTIC_OBSERVATION',
    'TECH_COMMON_VOID': 'TECH_VOID_ORIGIN_CANON',
    'TECH_COMMON_INTEGRATION': 'TECH_MYRIAD_LAW_UNITY',
    'TECH_COMMON_MAHAYANA': 'TECH_SUPREME_SALVATION',
    'TECH_CELESTIAL_BREATHING': 'TECH_ROSY_CLOUD_BREATH',
    'TECH_HEAVEN_DEMON_VOID': 'TECH_HEAVEN_DEMON_MYSTERIES',
    'TECH_EMPTY_VOID_CANON': 'TECH_LUCID_SUBTLETY_CANON',
    'TECH_MONSTER_DEMON_CORE': 'TECH_CRIMSON_FURNACE',
    'TECH_MONSTER_GREAT_STRENGTH_BODY': 'TECH_MOUNTAIN_BEARING_BODY',
    'TECH_GHOST_BODY_THIEF': 'TECH_CICADA_METAMORPHOSIS',
    'TECH_GHOST_TEN_THOUSAND_HOSTS': 'TECH_BUTTERFLY_DREAM_CANON',
    'heroic_progeny_elixir': 'qilin_blessing_elixir',
    'nascent_incense': 'purple_mansion_incense',
    'repair_sky_pill': 'nine_return_truth_pill',
    'infant_origin_fruit': 'purple_stamen_fruit',
    'infant_transformation_pill': 'jade_pivot_pill',
    'god_transformation_dew': 'mystic_vision_dew',
    'nascent_flame_crystal': 'radiant_flame_crystal',
    'soul_infant_marrow': 'dark_jade_soul_marrow',
    'infant_soul_dew': 'moon_soul_dew',
    'spirit_calling_incense': 'returning_light_incense',
    'great_crossing_incense': 'serene_incense',
    'mahayana_soul_marrow': 'nine_depths_soul_marrow',
    'beast_infant_pill': 'moon_howl_pill',
    'void_refining_pill': 'profound_mystery_pill',
    'great_ascension_pill': 'heaven_bearing_pill',
    'mahayana_spirit_pill': 'mystic_firmament_pill',
    'heaven_reaching_treasure': 'heaven_bearing_scepter',
    'true_immortal_breakthrough_1': 'clear_void_origin_pill',
    'true_immortal_breakthrough_2': 'nine_turn_meridian_pill',
    'true_immortal_breakthrough_3': 'supreme_clarity_barrier_pill',
    'golden_immortal_breakthrough_1': 'golden_flower_dao_pill',
    'golden_immortal_breakthrough_2': 'imperishable_truth_pill',
    'golden_immortal_breakthrough_3': 'purple_heaven_mystery_pill',
    'taiyi_breakthrough_1': 'supreme_unity_pill',
    'taiyi_breakthrough_2': 'three_flower_dao_pill',
    'taiyi_breakthrough_3': 'five_breath_truth_pill',
    'daluo_breakthrough_1': 'boundless_perfection_pill',
    'daluo_breakthrough_2': 'primordial_harmony_pill',
    'daluo_breakthrough_3': 'myriad_lucid_pill'
}

# Field names, not substring replacements: e.g. 'major:4', realm IDs and text
# containing an old spelling are never interpreted as catalog references.
_REFERENCE_FIELDS = frozenset({
    'id', 'item', 'item_id', 'content_id', 'technique_id', 'main_technique_id',
    'support_technique_id', 'treasure_item_id', 'material_id', 'plant_id',
    'target_item_id', 'source_item_id', 'product_id', 'output_item_id', 'manual_id',
    'active_breakthrough_aids', 'technique_ids', 'material_ids', 'item_ids',
    'main_technique', 'support_technique', 'starting_techniques',
    'materials', 'inputs', 'outputs',
})


def canonical_content_id(identity: str) -> str:
    if identity in LEGACY_CONTENT_IDS:
        return LEGACY_CONTENT_IDS[identity]
    prefix = 'technique_manual::'
    if identity.startswith(prefix):
        technique, separator, level = identity[len(prefix):].partition('::lv')
        if technique in LEGACY_CONTENT_IDS:
            return prefix + LEGACY_CONTENT_IDS[technique] + (separator + level if separator else '')
    return identity


def normalize_content_references(value: Any, field: str = '') -> Any:
    """Copy changed branches only; never mutate the decoded document in place.

    Catalog-keyed inventories, market stocks, inheritance ledgers and recipe
    inputs share the exact same alias table. Reject ambiguous map collisions
    rather than silently discarding either stock or currency history.
    """
    if isinstance(value, str):
        return canonical_content_id(value) if field in _REFERENCE_FIELDS else value
    if isinstance(value, list):
        result = None
        for index, child in enumerate(value):
            updated = normalize_content_references(child, field)
            if updated is not child:
                if result is None:
                    result = list(value)
                result[index] = updated
        return value if result is None else result
    if isinstance(value, dict):
        result = None
        for key, child in value.items():
            canonical_key = canonical_content_id(key) if isinstance(key, str) else key
            if canonical_key != key and canonical_key in value:
                raise ValueError(f'物品标识同时存在新旧记录，不能自动覆盖：{key} / {canonical_key}')
            updated = normalize_content_references(child, key)
            if canonical_key != key or updated is not child:
                if result is None:
                    result = dict(value)
                if canonical_key != key:
                    del result[key]
                result[canonical_key] = updated
        return value if result is None else result
    return value
