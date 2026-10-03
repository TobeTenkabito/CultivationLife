from __future__ import annotations
from functools import cached_property
from .formation.wiring import bind_formation
from .formation import presentation as formation_presentation
from .formation import npcs as formation_npcs
from .formation import market as formation_market
from .formation import loadouts as formation_loadouts
from .formation import ground as formation_ground

import copy
import math
import random
import uuid
from functools import lru_cache
from typing import Any

from ..content_registry import CONTENT_DOCUMENTS, ITEM_CATALOG, REALMS, WORLD_SYSTEMS
from ..formation_content import expanded_formation_materials
from ..models import GameState, HistoryRecord, Item, Player
from ..runtime import now_iso
from ..rules import expected_combat_power


STAT_NAMES = {
    "might": "威能", "guard": "防护", "mobility": "身法",
    "sense": "神识", "sustain": "续航", "breach": "破法",
}
NATURE_NAMES = {
    "metal": "金", "wood": "木", "water": "水", "fire": "火",
    "earth": "土", "yin": "阴", "yang": "阳", "wind": "风",
    "thunder": "雷", "soul": "魂", "space": "空", "star": "星",
    "law": "律", "neutral": "中",
}
CHANGE_MODE_NAMES = {
    "none": "无变", "positive": "顺变", "negative": "逆变", "rotating": "轮转",
}


def formation_config() -> dict[str, Any]:
    return CONTENT_DOCUMENTS.get("formations.json", {})


@lru_cache(maxsize=1)
def formation_material_definitions() -> dict[str, dict[str, Any]]:
    return {str(row["id"]): row for row in expanded_formation_materials(formation_config())}


def formation_maintenance_definitions() -> dict[str, dict[str, Any]]:
    return {str(row["id"]): row for row in formation_config().get("maintenance_resources", [])}


def formation_shared_definitions() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for group, source_kind in (
        ("crafting_materials", "crafting_material"),
        ("inventory_items", "inventory"),
        ("spirit_plants", "inventory"),
    ):
        for row in formation_config().get(group, []):
            definition = copy.deepcopy(row)
            definition["source_kind"] = source_kind
            key = str(definition.get("id") or definition.get("item_id") or definition.get("plant_id"))
            definition.setdefault("id", f"{group}:{key}")
            result[str(definition["id"])] = definition
    nature_by_source = {
        "canghai": "water", "weir": "space", "bloodriver": "yin",
        "demon_grave": "law", "beast_vortex": "wood", "yellow_spring": "soul",
        "monster_realm": "wood", "celestial": "law", "asura": "fire", "nether": "water", "reincarnation": "soul",
    }
    for item in ITEM_CATALOG.values():
        tags = set(item.tags)
        if "guixu_tide" not in tags or not tags.intersection({"crafting_material", "spirit_plant"}):
            continue
        source = next((key for key in nature_by_source if key in tags), "canghai")
        raw_value = float(item.plant_value or item.combat_bonus or 10)
        result[f"guixu:{item.id}"] = {
            "id": f"guixu:{item.id}", "item_id": item.id, "name": item.name,
            "source_kind": "inventory", "nature": nature_by_source[source],
            "formation_value": round(max(2.0, math.log10(max(10.0, raw_value)) * 4.0), 2),
            "tier": 9 if source in {"celestial", "asura", "nether", "reincarnation"} else 6 if source not in {"canghai", "bloodriver"} else 3,
        }
    return result


def formation_level(player: Player) -> int:
    base = max(1.0, float(formation_config().get("settings", {}).get("experience_base", 100)))
    return int(math.sqrt(max(0.0, float(player.art_experience.get("formation", 0.0))) / base))


def formation_alpha(player: Player) -> float:
    settings = formation_config().get("settings", {})
    low = float(settings.get("alpha_min", 0.50))
    high = float(settings.get("alpha_max", 0.90))
    scale = max(1.0, float(settings.get("alpha_level_scale", 12)))
    return low + (high - low) * (1.0 - math.exp(-formation_level(player) / scale))


def ensure_formation_state(player: Player) -> None:
    player.formation_materials = [
        copy.deepcopy(row) for row in player.formation_materials if isinstance(row, dict)
    ]
    # Preserve the first ID referenced by an existing loadout; split duplicate
    # black-market copies from older saves into independent physical objects.
    for materials in (player.formation_materials, player.crafting_materials):
        material_ids = set()
        for material in materials:
            if not material.get("id") or material["id"] in material_ids:
                material["id"] = f"material-{uuid.uuid4().hex}"
            material_ids.add(material["id"])
    loadouts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in player.formation_loadouts:
        if not isinstance(row, dict):
            continue
        loadout_id = str(row.get("id", ""))
        if not loadout_id or loadout_id in seen:
            continue
        slots = list(row.get("slots", []))[:9]
        slots.extend([None] * (9 - len(slots)))
        loadouts.append({
            "id": loadout_id,
            "name": str(row.get("name", "无名阵"))[:20] or "无名阵",
            "slots": [str(value) if value else None for value in slots],
            "created_year": int(row.get("created_year", player.age)),
        })
        seen.add(loadout_id)
    player.formation_loadouts = loadouts
    if player.active_formation_id not in seen:
        player.active_formation_id = None
        player.formation_active_bindings = []
        player.formation_profile_cache = {}
    bindings = list(player.formation_active_bindings)[:9]
    bindings.extend([None] * (9 - len(bindings)))
    player.formation_active_bindings = [
        copy.deepcopy(row) if isinstance(row, dict) else None for row in bindings
    ] if player.active_formation_id else []
    player.formation_sequence = max(0, int(player.formation_sequence), len(loadouts))
    ground_arrays: list[dict[str, Any]] = []
    ground_ids: set[str] = set()
    for raw in player.formation_ground_arrays:
        if not isinstance(raw, dict):
            continue
        ground_id = str(raw.get("id", ""))
        world = str(raw.get("world", ""))
        location_id = str(raw.get("location_id", ""))
        if not ground_id or ground_id in ground_ids or not world or not location_id:
            continue
        bindings = list(raw.get("bindings", []))[:9]
        bindings.extend([None] * (9 - len(bindings)))
        if sum(isinstance(binding, dict) for binding in bindings) < 2:
            continue
        owner_kind = str(raw.get("owner_kind", "player"))
        if owner_kind not in {"player", "sect"}:
            owner_kind = "player"
        ground_arrays.append({
            "id": ground_id,
            "name": str(raw.get("name", "无名镇地阵"))[:20] or "无名镇地阵",
            "loadout_id": str(raw.get("loadout_id", "")),
            "owner_kind": owner_kind,
            "owner_id": str(raw.get("owner_id", "player")),
            "owner_name": str(raw.get("owner_name", "自身")),
            "creator_id": str(raw.get("creator_id", "")),
            "creator_name": str(raw.get("creator_name", "")),
            "world": world,
            "location_id": location_id,
            "bindings": [copy.deepcopy(binding) if isinstance(binding, dict) else None for binding in bindings],
            "durability": round(max(0.0, min(100.0, float(raw.get("durability", 100.0)))), 4),
            "created_year": int(raw.get("created_year", player.age)),
            "last_repaired_year": int(raw.get("last_repaired_year", raw.get("created_year", player.age))),
            "battles": max(0, int(raw.get("battles", 0))),
        })
        ground_ids.add(ground_id)
    player.formation_ground_arrays = ground_arrays
    player.formation_repair_supplies = {
        str(key): max(0, int(quantity))
        for key, quantity in player.formation_repair_supplies.items()
        if int(quantity) > 0
    }
    ground_sequence_floor = max(
        (int(row["id"].rsplit("-", 1)[-1]) for row in ground_arrays
         if row["id"].rsplit("-", 1)[-1].isdigit()),
        default=0,
    )
    player.formation_ground_sequence = max(
        0, int(player.formation_ground_sequence), len(ground_arrays), ground_sequence_floor,
    )


def _distance(left: int, right: int) -> float:
    lr, lc = divmod(left, 3)
    rr, rc = divmod(right, 3)
    return math.hypot(lr - rr, lc - rc)


def relation_coefficient(source: dict[str, Any], target: dict[str, Any], config: dict[str, Any] | None = None) -> float:
    config = config or formation_config()
    target_nature = str(target.get("nature", "neutral"))
    override = source.get("relation_overrides", {}).get(target_nature)
    if override is not None:
        return max(-1.2, min(1.2, float(override)))
    source_nature = str(source.get("nature", "neutral"))
    return max(-1.0, min(1.0, float(config.get("relations", {}).get(source_nature, {}).get(target_nature, 0.0))))


def adjacency_matrix(nodes: list[dict[str, Any] | None], alpha: float, config: dict[str, Any] | None = None) -> list[list[float]]:
    matrix = [[0.0] * 9 for _ in range(9)]
    for left in range(9):
        if not nodes[left]:
            continue
        for right in range(9):
            if left == right or not nodes[right]:
                continue
            distance = max(1.0, _distance(left, right))
            matrix[left][right] = relation_coefficient(nodes[left], nodes[right], config) * alpha ** (distance - 1.0)
    return matrix


def effect_matrix(nodes: list[dict[str, Any] | None], adjacency: list[list[float]]) -> list[list[float]]:
    values = [max(0.0, float(row.get("formation_value", 0.0))) if row else 0.0 for row in nodes]
    return [
        [values[left] * adjacency[left][right] * values[right] for right in range(9)]
        for left in range(9)
    ]


def _matmul(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    size = len(left)
    return [
        [sum(left[row][inner] * right[inner][column] for inner in range(size)) for column in range(size)]
        for row in range(size)
    ]


def _trace(matrix: list[list[float]]) -> float:
    return sum(matrix[index][index] for index in range(len(matrix)))


def _qr_decompose(matrix: list[list[float]]) -> tuple[list[list[float]], list[list[float]]]:
    size = len(matrix)
    columns = [[matrix[row][column] for row in range(size)] for column in range(size)]
    q_columns: list[list[float]] = []
    upper = [[0.0] * size for _ in range(size)]
    for column_index, original in enumerate(columns):
        vector = list(original)
        for previous, basis in enumerate(q_columns):
            coefficient = sum(basis[row] * original[row] for row in range(size))
            upper[previous][column_index] = coefficient
            for row in range(size):
                vector[row] -= coefficient * basis[row]
        norm = math.sqrt(sum(value * value for value in vector))
        if norm < 1e-12:
            # Rank-deficient matrices are common for sparse arrays. Complete an
            # orthonormal basis deterministically instead of introducing noise.
            candidates = ([1.0 if row == axis else 0.0 for row in range(size)] for axis in range(size))
            for candidate in candidates:
                vector = candidate
                for basis in q_columns:
                    coefficient = sum(basis[row] * vector[row] for row in range(size))
                    vector = [value - coefficient * basis[row] for row, value in enumerate(vector)]
                norm = math.sqrt(sum(value * value for value in vector))
                if norm >= 1e-12:
                    break
        upper[column_index][column_index] = norm
        q_columns.append([value / norm for value in vector])
    orthogonal = [[q_columns[column][row] for column in range(size)] for row in range(size)]
    return orthogonal, upper


def qr_eigenvalues(matrix: list[list[float]], iterations: int = 96) -> list[complex]:
    size = len(matrix)
    if not size:
        return []
    working = [list(map(float, row)) for row in matrix]
    for _ in range(iterations):
        shift = working[-1][-1]
        shifted = [
            [working[row][column] - (shift if row == column else 0.0) for column in range(size)]
            for row in range(size)
        ]
        orthogonal, upper = _qr_decompose(shifted)
        working = _matmul(upper, orthogonal)
        for index in range(size):
            working[index][index] += shift
    values: list[complex] = []
    index = size - 1
    while index >= 0:
        if index > 0 and abs(working[index][index - 1]) > 1e-6:
            a, b = working[index - 1][index - 1], working[index - 1][index]
            c, d = working[index][index - 1], working[index][index]
            trace = a + d
            determinant = a * d - b * c
            discriminant = trace * trace - 4.0 * determinant
            if discriminant >= 0:
                root = math.sqrt(discriminant)
                values.extend([complex((trace + root) / 2.0), complex((trace - root) / 2.0)])
            else:
                root = math.sqrt(-discriminant) / 2.0
                values.extend([complex(trace / 2.0, root), complex(trace / 2.0, -root)])
            index -= 2
        else:
            values.append(complex(working[index][index]))
            index -= 1
    return values


def _fast_spectral_radius(square: list[list[float]], iterations: int = 12) -> float:
    """Estimate |lambda|max from M² for off-screen formation comparisons.

    M² keeps negative and rotating eigenmodes measurable without paying for a
    full shifted QR decomposition. Detailed player-involved combat still uses
    ``qr_eigenvalues`` and exposes the exact spectrum in the formation panel.
    """
    size = len(square)
    if not size:
        return 0.0
    vector = [1.0 / math.sqrt(size)] * size
    squared_radius = 0.0
    for _ in range(iterations):
        next_vector = [
            sum(square[row][column] * vector[column] for column in range(size))
            for row in range(size)
        ]
        norm = math.sqrt(sum(value * value for value in next_vector))
        if norm < 1e-12:
            return 0.0
        vector = [value / norm for value in next_vector]
        squared_radius = norm
    return math.sqrt(max(0.0, squared_radius))


def empty_formation_profile(name: str = "") -> dict[str, Any]:
    return {
        "active": False, "name": name, "occupied_count": 0, "alpha": 0.0,
        "metrics": {key: 0.0 for key in ("growth", "kill", "focus", "balance", "cycle", "change")},
        "metric_names": {"growth":"生势", "kill":"杀势", "focus":"聚势", "balance":"均势", "cycle":"环势", "change":"变势"},
        "change_mode": "none", "change_mode_name": CHANGE_MODE_NAMES["none"],
        "cycle_mode": "none", "core_node": None,
        "static_player_multipliers": {key: 1.0 for key in STAT_NAMES},
        "static_enemy_multipliers": {key: 1.0 for key in STAT_NAMES},
        "artificial_conditions": [], "round_rules": {}, "effects": [], "stability": "未成阵",
        "advanced": {"adjacency": [[0.0] * 9 for _ in range(9)], "matrix": [[0.0] * 9 for _ in range(9)], "eigenvalues": []},
    }


def calculate_formation_profile(
    nodes: list[dict[str, Any] | None], *, alpha: float, name: str = "无名阵",
    config: dict[str, Any] | None = None, detailed_spectrum: bool = True,
) -> dict[str, Any]:
    config = config or formation_config()
    settings = config.get("settings", {})
    nodes = list(nodes[:9])
    nodes.extend([None] * (9 - len(nodes)))
    occupied = [index for index, node in enumerate(nodes) if node and float(node.get("formation_value", 0)) > 0]
    if len(occupied) < 2:
        return empty_formation_profile(name)
    adjacency = adjacency_matrix(nodes, alpha, config)
    matrix = effect_matrix(nodes, adjacency)
    growth_raw = sum(max(value, 0.0) for row in matrix for value in row)
    kill_raw = sum(max(-value, 0.0) for row in matrix for value in row)
    total = growth_raw + kill_raw
    if total <= 1e-10:
        profile = empty_formation_profile(name)
        profile.update(occupied_count=len(occupied), alpha=round(alpha, 6))
        profile["advanced"] = {"adjacency": adjacency, "matrix": matrix, "eigenvalues": []}
        return profile

    incoming = [sum(abs(matrix[source][target]) for source in range(9)) for target in range(9)]
    incoming_total = sum(incoming)
    core_index = max(occupied, key=lambda index: (incoming[index], -index))
    count = len(occupied)
    baseline = 1.0 / count
    focus = 0.0 if count <= 1 else max(0.0, min(1.0, (incoming[core_index] / incoming_total - baseline) / (1.0 - baseline)))
    shares = [incoming[index] / incoming_total for index in occupied if incoming[index] > 0]
    balance = 0.0 if len(shares) <= 1 else max(0.0, min(1.0, -sum(value * math.log(value) for value in shares) / math.log(count)))

    row_norm = max(sum(abs(value) for value in row) for row in matrix)
    normalized = [[value / row_norm for value in row] for row in matrix]
    square = _matmul(normalized, normalized)
    cube = _matmul(square, normalized)
    fourth = _matmul(cube, normalized)
    weights = settings.get("cycle_weights", {"2": 0.50, "3": 0.30, "4": 0.20})
    traces = {2: _trace(square) / 9.0, 3: _trace(cube) / 9.0, 4: _trace(fourth) / 9.0}
    cycle_strength = min(1.0, 6.0 * sum(float(weights[str(power)]) * abs(traces[power]) for power in (2, 3, 4)))
    cycle_signed = sum(float(weights[str(power)]) * traces[power] for power in (2, 3, 4))
    # A loop made entirely from clashes has a positive even-power trace, so
    # trace sign alone cannot identify a killing cycle. Its dominant flow type
    # supplies the semantic sign while the traces measure loop strength.
    cycle_mode = (
        "negative" if cycle_strength > 1e-8 and kill_raw > growth_raw
        else "positive" if cycle_strength > 1e-8 and growth_raw >= kill_raw
        else "none"
    )

    if detailed_spectrum:
        eigenvalues = qr_eigenvalues(normalized)
        dominant = max(eigenvalues, key=abs, default=0j)
        radius = min(1.0, abs(dominant))
        if abs(dominant.imag) >= max(0.05, abs(dominant.real) * 0.18):
            change_mode = "rotating"
        elif dominant.real < -0.04 or kill_raw > growth_raw * 1.15:
            change_mode = "negative"
        else:
            change_mode = "positive"
    else:
        eigenvalues = []
        radius = min(1.0, _fast_spectral_radius(square))
        change_mode = "negative" if kill_raw > growth_raw * 1.15 else "positive"

    softcap = max(1.0, float(settings.get("metric_softcap_per_node", 50.0)) * count)
    activity = min(1.0, math.tanh(total / softcap))
    growth = activity * (growth_raw / total) ** 0.65
    kill = activity * (kill_raw / total) ** 0.65
    focus_score = focus * activity
    balance_score = balance * activity
    cycle_score = cycle_strength * activity
    change_score = radius * activity
    ratios = {
        "growth": growth, "kill": kill, "focus": focus_score,
        "balance": balance_score, "cycle": cycle_score, "change": change_score,
    }
    bonuses = {key: 0.0 for key in STAT_NAMES}
    bonuses["sustain"] += 0.075 * growth
    bonuses["might"] += 0.065 * kill
    bonuses["breach"] += 0.052 * kill
    bonuses["guard"] += 0.070 * balance_score
    if cycle_mode == "positive":
        bonuses["sustain"] += 0.022 * cycle_score
        bonuses["guard"] += 0.010 * cycle_score
    elif cycle_mode == "negative":
        bonuses["might"] += 0.018 * cycle_score
        bonuses["breach"] += 0.018 * cycle_score

    core = nodes[core_index] or {}
    core_nature = str(core.get("nature", "neutral"))
    focus_bonus = 0.055 * focus_score
    channels = config.get("nature_channels", {}).get(core_nature, [])
    for stat in channels:
        if stat in bonuses:
            bonuses[stat] += focus_bonus / max(1, len(channels)) ** 0.35
    if core_nature == "star":
        for stat in bonuses:
            bonuses[stat] += 0.012 * focus_score

    stat_cap = float(settings.get("stat_bonus_cap", 0.14))
    player_multipliers = {stat: 1.0 + min(stat_cap, max(0.0, bonus)) for stat, bonus in bonuses.items()}
    enemy_reductions = {key: 0.0 for key in STAT_NAMES}
    if core_nature == "space":
        enemy_reductions["mobility"] += 0.030 * focus_score
    if core_nature == "soul":
        enemy_reductions["sense"] += 0.025 * focus_score
    enemy_cap = float(settings.get("enemy_stat_reduction_cap", 0.06))
    enemy_multipliers = {stat: 1.0 - min(enemy_cap, reduction) for stat, reduction in enemy_reductions.items()}

    conditions = ["大阵"]
    field_threshold = float(settings.get("field_structure_threshold", 0.35))
    node_threshold = float(settings.get("field_node_ratio", 0.55))
    strongest = max(incoming) or 1.0
    for index in occupied:
        hook = nodes[index].get("field_hook") if nodes[index] else None
        strong_node = incoming[index] / strongest >= node_threshold
        structured = activity >= 0.15 and (focus >= field_threshold or cycle_strength >= field_threshold)
        if hook and strong_node and structured:
            condition = {"forbidden_air":"禁空", "forbidden_sense":"禁神识"}.get(str(hook))
            if condition and condition not in conditions:
                conditions.append(condition)

    positive_cycle = cycle_score if cycle_mode == "positive" else 0.0
    negative_cycle = cycle_score if cycle_mode == "negative" else 0.0
    round_rules = {
        "state_restore": min(0.015, 0.010 * growth + 0.004 * positive_cycle),
        "mp_restore": min(0.008, 0.005 * growth + 0.0025 * positive_cycle),
        "integrity_restore": min(0.018, 0.018 * positive_cycle),
        "integrity_extra_loss": min(0.012, 0.012 * negative_cycle),
        "integrity_kill_penalty": min(0.30, 0.30 * kill),
        "integrity_balance_reduction": min(0.42, 0.42 * balance_score),
        "enemy_morale_loss": min(2.4, 1.8 * kill + 0.6 * negative_cycle),
        "player_morale_loss_reduction": min(0.20, 0.16 * balance_score + 0.04 * growth),
        "dealt_bonus": min(0.025, 0.018 * kill + 0.007 * negative_cycle),
        "change_round_cap": float(settings.get("change_round_cap", 0.08)),
    }

    metric_values = {key: round(value * 100.0, 2) for key, value in ratios.items()}
    effects = [
        f"{STAT_NAMES[stat]} +{(multiplier - 1.0):.1%}"
        for stat, multiplier in player_multipliers.items() if multiplier > 1.00005
    ]
    effects.extend(
        f"敌方{STAT_NAMES[stat]} {(multiplier - 1.0):.1%}"
        for stat, multiplier in enemy_multipliers.items() if multiplier < 0.99995
    )
    if round_rules["state_restore"]:
        effects.append(f"每轮恢复 {round_rules['state_restore']:.1%} 战斗态势")
    if round_rules["mp_restore"]:
        effects.append(f"每轮恢复 {round_rules['mp_restore']:.1%} 最大法力")
    stability_value = balance_score + positive_cycle * 0.35 - kill * 0.45 - negative_cycle * 0.25
    stability = "高" if stability_value >= 0.45 else "中" if stability_value >= 0.05 else "低"
    return {
        "active": True, "name": name, "occupied_count": count, "alpha": round(alpha, 6),
        "metrics": metric_values,
        "metric_names": {"growth":"生势", "kill":"杀势", "focus":"聚势", "balance":"均势", "cycle":"环势", "change":"变势"},
        "change_mode": change_mode, "change_mode_name": CHANGE_MODE_NAMES[change_mode],
        "cycle_mode": cycle_mode,
        "core_node": {
            "index": core_index, "position": core_index + 1, "name": str(core.get("name", "阵材")),
            "nature": core_nature, "nature_name": NATURE_NAMES.get(core_nature, core_nature),
        },
        "static_player_multipliers": {key: round(value, 8) for key, value in player_multipliers.items()},
        "static_enemy_multipliers": {key: round(value, 8) for key, value in enemy_multipliers.items()},
        "artificial_conditions": conditions,
        "round_rules": {key: round(value, 8) for key, value in round_rules.items()},
        "effects": effects, "stability": stability,
        "advanced": {
            "adjacency": [[round(value, 6) for value in row] for row in adjacency],
            "matrix": [[round(value, 6) for value in row] for row in matrix],
            "incoming": [round(value, 6) for value in incoming],
            "raw_growth": round(growth_raw, 6), "raw_kill": round(kill_raw, 6),
            "activity": round(activity, 6),
            "eigenvalues": [
                {"real": round(value.real, 6), "imag": round(value.imag, 6), "magnitude": round(abs(value), 6)}
                for value in eigenvalues
            ],
        },
    }


@lru_cache(maxsize=4096)
def _cached_npc_formation_profile(
    slot_ids: tuple[str | None, ...], alpha: float, name: str, detailed_spectrum: bool,
) -> dict[str, Any]:
    definitions = formation_material_definitions()
    nodes = [
        copy.deepcopy(definitions[definition_id]) if definition_id in definitions else None
        for definition_id in slot_ids[:9]
    ]
    nodes.extend([None] * (9 - len(nodes)))
    return calculate_formation_profile(
        nodes, alpha=alpha, name=name, detailed_spectrum=detailed_spectrum,
    )


def formation_round_effects(profile: dict[str, Any], round_no: int, integrity: float) -> dict[str, Any]:
    integrity = max(0.0, min(1.0, float(integrity)))
    neutral = {
        "player_stat_multipliers": {key: 1.0 for key in STAT_NAMES},
        "enemy_stat_multipliers": {key: 1.0 for key in STAT_NAMES},
        "dealt_multiplier": 1.0, "received_multiplier": 1.0,
        "state_restore": 0.0, "mp_restore": 0.0,
        "integrity_restore": 0.0, "integrity_extra_loss": 0.0,
        "integrity_decay_multiplier": 1.0, "enemy_morale_loss": 0.0,
        "player_morale_loss_multiplier": 1.0, "change_event": "",
    }
    if not profile.get("active") or integrity <= 0:
        return neutral
    metrics = {key: float(value) / 100.0 for key, value in profile.get("metrics", {}).items()}
    rules = profile.get("round_rules", {})
    mode = str(profile.get("change_mode", "none"))
    change = metrics.get("change", 0.0)
    cap = float(rules.get("change_round_cap", 0.08))
    growth_scale = 1.0
    additions = {key: 0.0 for key in STAT_NAMES}
    event = ""
    if mode == "positive":
        growth_scale += min(cap, max(0, round_no - 1) * 0.015 * change)
        if round_no > 1 and growth_scale > 1.001:
            event = f"顺变将阵势效果推高至 {growth_scale:.1%}。"
    elif mode == "negative":
        if round_no % 2:
            additions["might"] += 0.045 * change
            additions["breach"] += 0.035 * change
            event = "逆变转入攻势，相克灵流集中于威能与破法。"
        else:
            additions["guard"] += 0.045 * change
            additions["sustain"] += 0.035 * change
            event = "逆变转入守势，逆流回折为防护与续航。"
    elif mode == "rotating":
        stat = ("might", "mobility", "guard")[(round_no - 1) % 3]
        additions[stat] += 0.055 * change
        event = f"轮转灵流行至{STAT_NAMES[stat]}位。"

    for stat, multiplier in profile.get("static_player_multipliers", {}).items():
        if stat in neutral["player_stat_multipliers"]:
            bonus = max(0.0, float(multiplier) - 1.0) * growth_scale + additions[stat]
            neutral["player_stat_multipliers"][stat] = 1.0 + bonus * integrity
    for stat, multiplier in profile.get("static_enemy_multipliers", {}).items():
        if stat in neutral["enemy_stat_multipliers"]:
            reduction = max(0.0, 1.0 - float(multiplier)) * growth_scale
            neutral["enemy_stat_multipliers"][stat] = 1.0 - reduction * integrity
    neutral.update(
        dealt_multiplier=1.0 + float(rules.get("dealt_bonus", 0.0)) * integrity,
        state_restore=float(rules.get("state_restore", 0.0)) * integrity,
        mp_restore=float(rules.get("mp_restore", 0.0)) * integrity,
        integrity_restore=float(rules.get("integrity_restore", 0.0)),
        integrity_extra_loss=float(rules.get("integrity_extra_loss", 0.0)),
        integrity_decay_multiplier=(
            1.0 + float(rules.get("integrity_kill_penalty", 0.0))
        ) * (
            1.0 - float(rules.get("integrity_balance_reduction", 0.0))
        ),
        enemy_morale_loss=float(rules.get("enemy_morale_loss", 0.0)) * integrity,
        player_morale_loss_multiplier=1.0 - float(rules.get("player_morale_loss_reduction", 0.0)) * integrity,
        change_event=event,
    )
    return neutral


def _profile_from_bindings(player: Player) -> dict[str, Any]:
    ensure_formation_state(player)
    if not player.active_formation_id or not player.formation_active_bindings:
        return empty_formation_profile()
    loadout = next((row for row in player.formation_loadouts if row["id"] == player.active_formation_id), None)
    if not loadout:
        return empty_formation_profile()
    nodes = [
        copy.deepcopy(binding.get("formation_profile", {})) | {"name": binding.get("name", "阵材")}
        if binding else None
        for binding in player.formation_active_bindings
    ]
    profile = calculate_formation_profile(nodes, alpha=formation_alpha(player), name=loadout["name"])
    profile["loadout_id"] = loadout["id"]
    return profile


def active_formation_profile(player: Player) -> dict[str, Any]:
    ensure_formation_state(player)
    cached = player.formation_profile_cache
    if (
        player.active_formation_id and isinstance(cached, dict)
        and cached.get("active") and cached.get("loadout_id") == player.active_formation_id
        and abs(float(cached.get("alpha", -1)) - formation_alpha(player)) < 1e-9
    ):
        return copy.deepcopy(cached)
    profile = _profile_from_bindings(player)
    player.formation_profile_cache = copy.deepcopy(profile) if profile.get("active") else {}
    return profile


def formation_battle_experience_gain(profile: dict[str, Any], rounds: int, power_ratio: float) -> float:
    if not profile.get("active") or rounds <= 0:
        return 0.0
    occupied = int(profile.get("occupied_count", 0))
    difficulty = max(0.70, min(1.50, 1.0 / max(0.25, float(power_ratio)) ** 0.25))
    return round(min(45.0, (5.0 + rounds * 2.0 + occupied * 1.25) * difficulty), 2)


def make_formation_material_instance(definition: dict[str, Any], *, source: str, origin_world: str) -> dict[str, Any]:
    return {
        "id": f"formation-material-{uuid.uuid4().hex}",
        "material_id": str(definition["id"]), "name": str(definition["name"]),
        "source": source, "origin_world": origin_world,
        "acquired_tier": int(definition.get("tier", 1)),
        "base_value": max(1, int(definition.get("base_value", 1))),
    }


def formation_profile_from_bindings(
    bindings: list[dict[str, Any] | None], *, alpha: float, name: str,
) -> dict[str, Any]:
    nodes = [
        copy.deepcopy(binding.get("formation_profile", {})) | {"name": binding.get("name", "阵材")}
        if binding else None
        for binding in list(bindings[:9])
    ]
    nodes.extend([None] * (9 - len(nodes)))
    return calculate_formation_profile(nodes, alpha=alpha, name=name)


def ground_formation_power(array: dict[str, Any], profile: dict[str, Any]) -> float:
    """Convert a matrix profile into one bounded off-screen defence value.

    The matrix broadcasts percentages in player combat. Ground defence needs an
    absolute comparison against an attacking force, so its anchor comes from
    the real nodes' acquired tiers. Structural quality only chooses a bounded
    fraction of that tier's normal combat baseline and is never rebroadcast.
    """
    if not profile.get("active") or float(array.get("durability", 0.0)) <= 0:
        return 0.0
    bindings = [binding for binding in array.get("bindings", []) if isinstance(binding, dict)]
    tiers = [
        max(0, min(len(REALMS) - 1, int(
            binding.get("acquired_tier", binding.get("source_snapshot", {}).get("acquired_tier", 1))
        )))
        for binding in bindings
    ]
    if not tiers:
        return 0.0
    tiers.sort()
    tier = tiers[len(tiers) // 2]
    baseline = expected_combat_power(tier, 1)
    settings = formation_config().get("settings", {})
    activity = max(0.0, min(1.0, float(profile.get("advanced", {}).get("activity", 0.0))))
    metrics = profile.get("metrics", {})
    structure = max(0.0, min(1.0, (
        float(metrics.get("focus", 0.0))
        + float(metrics.get("balance", 0.0))
        + float(metrics.get("cycle", 0.0))
    ) / 300.0))
    low = float(settings.get("ground_power_ratio_min", 0.18))
    high = float(settings.get("ground_power_ratio_max", 0.52))
    ratio = low + (high - low) * (activity * 0.65 + structure * 0.35)
    ratio = min(float(settings.get("ground_power_hard_cap_ratio", 0.58)), ratio)
    durability_scale = math.sqrt(max(0.0, min(1.0, float(array.get("durability", 0.0)) / 100.0)))
    return round(baseline * ratio * durability_scale, 2)


def _formation_rules() -> dict[str, Any]:
    return formation_config().get("settings", {})


def _formation_material_defs() -> dict[str, dict[str, Any]]:
    return formation_material_definitions()


def _formation_maintenance_defs() -> dict[str, dict[str, Any]]:
    return formation_maintenance_definitions()


def _formation_candidate(source: dict[str, Any], definition: dict[str, Any], source_kind: str, candidate_id: str) -> dict[str, Any]:
    return {
        "id": str(candidate_id), "definition_id": str(definition["id"]),
        "name": str(definition.get("name") or source.get("name", "阵材")),
        "nature": str(definition.get("nature", "neutral")),
        "nature_name": NATURE_NAMES.get(str(definition.get("nature", "neutral")), str(definition.get("nature", "neutral"))),
        "formation_value": float(definition.get("formation_value", 0.0)),
        "acquired_tier": int(source.get("acquired_tier", definition.get("tier", 1))),
        "relation_overrides": copy.deepcopy(definition.get("relation_overrides", {})),
        "field_hook": definition.get("field_hook"),
        "source_kind": source_kind, "source": str(source.get("source", "行囊")),
        "storage_id": str(source.get("id", candidate_id)), "occupied": False,
    }


def _extract_candidate(player: Player, candidate: dict[str, Any]) -> dict[str, Any]:
    source_kind = str(candidate["source_kind"])
    storage_id = str(candidate.get("storage_id", ""))
    snapshot: dict[str, Any]
    if source_kind == "formation_material":
        source = next((row for row in player.formation_materials if str(row.get("id")) == storage_id), None)
        if not source:
            raise ValueError("阵材实例已经不在材料库中")
        snapshot = copy.deepcopy(source)
        player.formation_materials.remove(source)
    elif source_kind == "crafting_material":
        source = next((row for row in player.crafting_materials if str(row.get("id")) == storage_id), None)
        if not source:
            raise ValueError("共用材料实例已经不在材料库中")
        snapshot = copy.deepcopy(source)
        player.crafting_materials.remove(source)
    elif source_kind == "inventory":
        item_id = str(candidate.get("inventory_item_id") or storage_id)
        item = next((row for row in player.inventory if row.id == item_id and row.quantity > 0), None)
        if not item:
            raise ValueError("行囊中的共用阵材已经不存在")
        snapshot = item.to_dict() | {"quantity": 1}
        item.quantity -= 1
        if item.quantity <= 0:
            player.inventory.remove(item)
    else:
        raise ValueError("未知阵材来源")
    return copy.deepcopy(candidate) | {
        "occupied": True, "source_snapshot": snapshot,
        "formation_profile": {
            "formation_value": float(candidate["formation_value"]),
            "nature": str(candidate["nature"]),
            "relation_overrides": copy.deepcopy(candidate.get("relation_overrides", {})),
            "field_hook": candidate.get("field_hook"),
        },
    }


def _release_active_formation(player: Player) -> None:
    FormationSystemMixin._release_bindings(player, player.formation_active_bindings)
    player.active_formation_id = None
    player.formation_active_bindings = []
    player.formation_profile_cache = {}


def _release_bindings(player: Player, bindings: list[dict[str, Any] | None]) -> None:
    for binding in list(bindings):
        if not binding or not isinstance(binding.get("source_snapshot"), dict):
            continue
        snapshot = copy.deepcopy(binding["source_snapshot"])
        source_kind = str(binding.get("source_kind", ""))
        if source_kind == "formation_material":
            if not any(str(row.get("id")) == str(snapshot.get("id")) for row in player.formation_materials):
                player.formation_materials.append(snapshot)
        elif source_kind == "crafting_material":
            if not any(str(row.get("id")) == str(snapshot.get("id")) for row in player.crafting_materials):
                player.crafting_materials.append(snapshot)
        elif source_kind == "inventory":
            item_id = str(snapshot.get("id", ""))
            existing = next((row for row in player.inventory if row.id == item_id), None)
            if existing:
                existing.quantity += int(snapshot.get("quantity", 1))
            else:
                player.inventory.append(Item.from_dict(snapshot))


def _ground_profile(player: Player, array: dict[str, Any]) -> dict[str, Any]:
    return formation_profile_from_bindings(
        list(array.get("bindings", [])), alpha=formation_alpha(player),
        name=str(array.get("name", "无名镇地阵")),
    )


def bind_formation_compatibility(host):
    return bind_formation(
        host,
        _cached_npc_formation_profile=lambda *args, **kwargs: _cached_npc_formation_profile(*args, **kwargs),
        _get_NATURE_NAMES=lambda: NATURE_NAMES,
        _profile_from_bindings=lambda *args, **kwargs: _profile_from_bindings(*args, **kwargs),
        active_formation_profile=lambda *args, **kwargs: active_formation_profile(*args, **kwargs),
        calculate_formation_profile=lambda *args, **kwargs: calculate_formation_profile(*args, **kwargs),
        empty_formation_profile=lambda *args, **kwargs: empty_formation_profile(*args, **kwargs),
        ensure_formation_state=lambda *args, **kwargs: ensure_formation_state(*args, **kwargs),
        formation_alpha=lambda *args, **kwargs: formation_alpha(*args, **kwargs),
        formation_config=lambda *args, **kwargs: formation_config(*args, **kwargs),
        formation_level=lambda *args, **kwargs: formation_level(*args, **kwargs),
        formation_shared_definitions=lambda *args, **kwargs: formation_shared_definitions(*args, **kwargs),
        ground_formation_power=lambda *args, **kwargs: ground_formation_power(*args, **kwargs),
        make_formation_material_instance=lambda *args, **kwargs: make_formation_material_instance(*args, **kwargs),
    )


class FormationSystemMixin:
    @cached_property
    def _formation_dependencies(self):
        return bind_formation_compatibility(self)

    @staticmethod
    def _formation_rules() -> dict[str, Any]:
        return _formation_rules()

    @staticmethod
    def _formation_material_defs() -> dict[str, dict[str, Any]]:
        return _formation_material_defs()

    @staticmethod
    def _formation_maintenance_defs() -> dict[str, dict[str, Any]]:
        return _formation_maintenance_defs()

    def _append_formation_market_offers(
        self, game: GameState, rng: random.Random, offers: list[dict[str, Any]], *,
        tier: int, market_name: str, location_id: str,
    ) -> None:
        return formation_market._append_formation_market_offers(self._formation_dependencies.market, game, rng, offers, tier=tier, market_name=market_name, location_id=location_id)

    def _buy_formation_material_offer(self, game: GameState, offer: dict[str, Any], price: int) -> str:
        return formation_market._buy_formation_material_offer(self._formation_dependencies.market, game, offer, price)

    def _buy_formation_supply_offer(self, game: GameState, offer: dict[str, Any], price: int) -> str:
        return formation_market._buy_formation_supply_offer(self._formation_dependencies.market, game, offer, price)

    def _formation_candidates(
        self, player: Player, *, include_active: bool = True, include_ground: bool = True,
    ) -> list[dict[str, Any]]:
        return formation_loadouts._formation_candidates(self._formation_dependencies.loadouts, player, include_active=include_active, include_ground=include_ground)

    @staticmethod
    def _formation_candidate(source: dict[str, Any], definition: dict[str, Any], source_kind: str, candidate_id: str) -> dict[str, Any]:
        return _formation_candidate(source, definition, source_kind, candidate_id)

    def _nodes_from_candidate_ids(self, player: Player, slot_ids: list[Any]) -> tuple[list[dict[str, Any] | None], list[str | None]]:
        return formation_loadouts._nodes_from_candidate_ids(self._formation_dependencies.loadouts, player, slot_ids)

    def preview_formation(self, game_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return formation_loadouts.preview_formation(self._formation_dependencies.loadouts, game_id, payload)

    def save_formation(self, game_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return formation_loadouts.save_formation(self._formation_dependencies.loadouts, game_id, payload)

    def activate_formation(self, game_id: str, loadout_id: str) -> dict[str, Any]:
        return formation_loadouts.activate_formation(self._formation_dependencies.loadouts, game_id, loadout_id)

    def deactivate_formation(self, game_id: str) -> dict[str, Any]:
        return formation_loadouts.deactivate_formation(self._formation_dependencies.loadouts, game_id)

    def delete_formation(self, game_id: str, loadout_id: str) -> dict[str, Any]:
        return formation_loadouts.delete_formation(self._formation_dependencies.loadouts, game_id, loadout_id)

    def _activate_loadout(self, player: Player, loadout: dict[str, Any]) -> None:
        # First build a virtual pool containing the currently occupied material.
        # This makes switching presets atomic and permits reusing the same rare
        # instance without ever cloning it.
        return formation_loadouts._activate_loadout(self._formation_dependencies.loadouts, player, loadout)

    @staticmethod
    def _extract_candidate(player: Player, candidate: dict[str, Any]) -> dict[str, Any]:
        return _extract_candidate(player, candidate)

    @staticmethod
    def _release_active_formation(player: Player) -> None:
        return _release_active_formation(player)

    @staticmethod
    def _release_bindings(player: Player, bindings: list[dict[str, Any] | None]) -> None:
        return _release_bindings(player, bindings)

    @staticmethod
    def _ground_profile(player: Player, array: dict[str, Any]) -> dict[str, Any]:
        return _ground_profile(player, array)

    def _ground_array_public(self, player: Player, array: dict[str, Any]) -> dict[str, Any]:
        return formation_ground._ground_array_public(self._formation_dependencies.ground, player, array)

    def deploy_ground_formation(self, game_id: str, owner_kind: str = "player") -> dict[str, Any]:
        return formation_ground.deploy_ground_formation(self._formation_dependencies.ground, game_id, owner_kind)

    def _require_ground_array_access(self, game: GameState, ground_id: str) -> dict[str, Any]:
        return formation_ground._require_ground_array_access(self._formation_dependencies.ground, game, ground_id)

    def withdraw_ground_formation(self, game_id: str, ground_id: str) -> dict[str, Any]:
        return formation_ground.withdraw_ground_formation(self._formation_dependencies.ground, game_id, ground_id)

    def repair_ground_formation(self, game_id: str, ground_id: str, supply_id: str, quantity: int = 1) -> dict[str, Any]:
        return formation_ground.repair_ground_formation(self._formation_dependencies.ground, game_id, ground_id, supply_id, quantity)

    def _local_ground_formation(self, game: GameState) -> dict[str, Any] | None:
        return formation_ground._local_ground_formation(self._formation_dependencies.ground, game)

    def _sect_guard_array(self, game: GameState, sect_id: str) -> dict[str, Any] | None:
        return formation_ground._sect_guard_array(self._formation_dependencies.ground, game, sect_id)

    def _sect_guard_power(self, game: GameState, sect_id: str) -> float:
        return formation_ground._sect_guard_power(self._formation_dependencies.ground, game, sect_id)

    def _wear_war_guard_arrays(self, game: GameState, war: dict[str, Any], amount: float | None = None) -> None:
        return formation_ground._wear_war_guard_arrays(self._formation_dependencies.ground, game, war, amount)

    def _npc_formation_profile(
        self, game: GameState, npc_id: str, *, detailed_spectrum: bool = False,
    ) -> dict[str, Any]:
        return formation_npcs._npc_formation_profile(self._formation_dependencies.npcs, game, npc_id, detailed_spectrum=detailed_spectrum)

    def _npc_formation_power_multiplier(self, game: GameState, npc_id: str) -> float:
        return formation_npcs._npc_formation_power_multiplier(self._formation_dependencies.npcs, game, npc_id)

    def _ensure_npc_formations(self, game: GameState) -> bool:
        return formation_npcs._ensure_npc_formations(self._formation_dependencies.npcs, game)

    def _public_formation_system(self, game: GameState) -> dict[str, Any]:
        return formation_presentation._public_formation_system(self._formation_dependencies.presentation, game)
