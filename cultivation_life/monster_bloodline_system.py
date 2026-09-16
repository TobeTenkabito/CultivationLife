from __future__ import annotations

import copy
import uuid
from typing import Any

from .custom_lineage_system import (
    editor_payload, is_self_lineage_node, lineage_deed_budget, normalize_rules,
    public_custom_lineage, self_lineage_stage,
)
from .monster_bloodline_traits import public_bloodline_trait
from .monster_bloodline_rules import (
    MAX_TRAITS, generate_species_bloodline_trait, public_generated_trait,
    validate_generated_collection, validate_generated_trait,
)
from .monster_general_traits import GENERAL_MONSTER_TRAIT_REGISTRY, public_general_monster_trait
from .content_registry import (
    MONSTER_BLOODLINE_SETTINGS, MONSTER_EVOLUTIONS, MONSTER_SPECIES, REALMS,
    TECHNIQUE_CATALOG, WORLD_SYSTEMS,
)
from .models import GameState, HistoryRecord, Player
from .rules import (
    assign_technique, learn_technique, max_hp, max_mp, opportunity_required,
    public_player, qi_level,
)
from .runtime import decode_rng, encode_rng, now_iso


STAT_KEYS = ("might", "guard", "mobility", "sense", "sustain", "breach")
NEUTRAL_PROFILE = {key: 1.0 for key in STAT_KEYS}


def bloodline_content_available() -> bool:
    return bool(MONSTER_SPECIES and MONSTER_EVOLUTIONS)


def resolved_bloodline_traits(node: dict[str, Any]) -> list[str]:
    """Combine branch traits with species traits unlocked by realm.

    Signature traits live in DLC data rather than hard-coded species checks, so
    future species can opt in without changing combat code.
    """
    traits = list(map(str, node.get("traits", [])))
    for unlock in MONSTER_BLOODLINE_SETTINGS.get("species_signature_traits", []):
        if (
            unlock.get("species_id") == node.get("species")
            and int(node.get("realm_index", 0)) >= int(unlock.get("minimum_realm", 0))
        ):
            traits.append(str(unlock["trait_id"]))
    return list(dict.fromkeys(traits))


def acquired_species_bloodline_traits(player: Player) -> list[str]:
    pool = set(map(str, MONSTER_BLOODLINE_SETTINGS.get("species_trait_pools", {}).get(
        str(player.monster_species_id or ""), [],
    )))
    generated_slots = {
        str(rule.get("slot_id")) for rule in player.monster_generated_bloodline_traits
        if isinstance(rule, dict) and rule.get("slot_id")
    }
    return list(dict.fromkeys(
        trait_id for trait_id in map(str, player.monster_acquired_bloodline_traits)
        if trait_id in pool and trait_id not in generated_slots
    ))


def grant_random_species_bloodline_trait(player: Player, rng: Any) -> dict[str, str] | None:
    pool = list(map(str, MONSTER_BLOODLINE_SETTINGS.get("species_trait_pools", {}).get(
        str(player.monster_species_id or ""), [],
    )))
    owned = set(map(str, player.monster_acquired_bloodline_traits))
    remaining = [trait_id for trait_id in pool if trait_id not in owned]
    if player.path != "monster" or not bloodline_content_available() or not remaining:
        return None
    trait_id = rng.choice(remaining)
    player.monster_acquired_bloodline_traits.append(trait_id)
    return public_bloodline_trait(trait_id)


def generated_species_bloodline_traits(player: Player) -> list[dict[str, Any]]:
    return [
        copy.deepcopy(rule) for rule in player.monster_generated_bloodline_traits
        if isinstance(rule, dict)
        and rule.get("species_id") == player.monster_species_id
        and not validate_generated_trait(rule)
    ]


def grant_generated_species_bloodline_trait(player: Player, rng: Any) -> dict[str, Any] | None:
    if player.path != "monster" or not bloodline_content_available():
        return None
    generated = generated_species_bloodline_traits(player)
    legacy_count = len(acquired_species_bloodline_traits(player))
    if legacy_count + len(generated) >= MAX_TRAITS:
        return None
    pool = list(map(str, MONSTER_BLOODLINE_SETTINGS.get("species_trait_pools", {}).get(
        str(player.monster_species_id or ""), [],
    )))
    recorded = set(map(str, player.monster_acquired_bloodline_traits))
    remaining_slots = [trait_id for trait_id in pool if trait_id not in recorded]
    if not remaining_slots:
        return None
    rule = generate_species_bloodline_trait(str(player.monster_species_id or ""), rng, generated)
    if rule is None:
        return None
    rule["slot_id"] = rng.choice(remaining_slots)
    player.monster_generated_bloodline_traits.append(copy.deepcopy(rule))
    # Keep the historical public/save field as the complete list of awakening
    # IDs. acquired_species_bloodline_traits still filters legacy pool IDs, so
    # generated rules are never mistaken for fixed registry entries.
    player.monster_acquired_bloodline_traits.append(str(rule["slot_id"]))
    return public_generated_trait(rule)


def active_bloodline_profile(player: Player) -> dict[str, Any]:
    node = MONSTER_EVOLUTIONS.get(str(player.monster_evolution_id or ""))
    if player.path != "monster" or not bloodline_content_available() or not node:
        return {
            "id": None, "name": "", "stat_multipliers": dict(NEUTRAL_PROFILE),
            "traits": [], "generated_traits": [], "abilities": [], "travel_multiplier": 1.0,
        }
    return {
        "id": node["id"], "name": node["name"],
        "stat_multipliers": dict(node["profile"]),
        "traits": list(dict.fromkeys([
            *resolved_bloodline_traits(node), *acquired_species_bloodline_traits(player),
        ])),
        "generated_traits": generated_species_bloodline_traits(player),
        "abilities": list(node.get("abilities", [])),
        "travel_multiplier": float(node.get("travel_multiplier", 1.0)),
    }


def initialize_monster_bloodline(player: Player, species_id: str | None = None) -> bool:
    if player.path != "monster" or not bloodline_content_available():
        return False
    selected = str(species_id or MONSTER_BLOODLINE_SETTINGS.get("default_species_id") or next(iter(MONSTER_SPECIES)))
    species = MONSTER_SPECIES.get(selected)
    if not species:
        raise ValueError("未知妖修本源种")
    base_id = str(species["base_evolution_id"])
    player.monster_species_id = selected
    player.monster_evolution_id = base_id
    player.monster_evolution_history = [base_id]
    player.monster_adaptations = []
    player.monster_adaptation_progress = {}
    player.monster_bloodline_imprints = list(dict.fromkeys(player.monster_bloodline_imprints))
    return True


def _stable_history_for_realm(species_id: str, realm_index: int) -> list[str]:
    """Build the condition-free route used to migrate pre-DLC monster saves."""
    species = MONSTER_SPECIES[species_id]
    history = [str(species["base_evolution_id"])]
    current_id = history[0]
    for target_realm in range(1, max(0, realm_index) + 1):
        choices = [
            node for node in MONSTER_EVOLUTIONS.values()
            if node.get("species") == species_id
            and current_id in node.get("parents", [])
            and int(node.get("realm_index", -1)) == target_realm
            and int(node.get("monster_qi_level", 0)) == 0
            and not node.get("requirements")
        ]
        if not choices:
            break
        current_id = str(min(choices, key=lambda row: (int(row.get("order", 100)), row["id"]))["id"])
        history.append(current_id)
    return history


def ensure_monster_bloodline_state(player: Player) -> bool:
    if player.path != "monster" or not bloodline_content_available():
        return False
    changed = False
    if player.monster_species_id not in MONSTER_SPECIES:
        initialize_monster_bloodline(player)
        history = _stable_history_for_realm(str(player.monster_species_id), player.realm_index)
        player.monster_evolution_history = history
        player.monster_evolution_id = history[-1]
        changed = True
    species = MONSTER_SPECIES[player.monster_species_id]
    node = MONSTER_EVOLUTIONS.get(str(player.monster_evolution_id or ""))
    if not node or node.get("species") != player.monster_species_id:
        history = _stable_history_for_realm(str(player.monster_species_id), player.realm_index)
        player.monster_evolution_history = history
        player.monster_evolution_id = history[-1]
        changed = True
    if not player.monster_evolution_history:
        player.monster_evolution_history = [str(player.monster_evolution_id)]
        changed = True
    elif player.monster_evolution_history[-1] != player.monster_evolution_id:
        player.monster_evolution_history.append(str(player.monster_evolution_id))
        changed = True
    player.monster_evolution_history = list(dict.fromkeys(map(str, player.monster_evolution_history)))
    player.monster_adaptations = list(dict.fromkeys(
        adaptation for adaptation in map(str, player.monster_adaptations)
        if adaptation in MONSTER_BLOODLINE_SETTINGS.get("adaptations", {})
    ))
    player.monster_bloodline_imprints = list(dict.fromkeys(
        imprint for imprint in map(str, player.monster_bloodline_imprints)
        if imprint in MONSTER_BLOODLINE_SETTINGS.get("imprints", {})
    ))
    valid_generated = generated_species_bloodline_traits(player)
    if (
        len(valid_generated) != len(player.monster_generated_bloodline_traits)
        or validate_generated_collection(valid_generated)
    ):
        # Invalid/tampered snapshots never execute. Preserve valid rules up to
        # the first collection conflict rather than allowing a broken save to
        # poison combat resolution.
        raw_generated_slots = {
            str(rule.get("slot_id")) for rule in player.monster_generated_bloodline_traits
            if isinstance(rule, dict) and rule.get("slot_id")
        }
        repaired: list[dict[str, Any]] = []
        for rule in valid_generated:
            if not validate_generated_collection([*repaired, rule]):
                repaired.append(rule)
        player.monster_generated_bloodline_traits = repaired
        repaired_slots = {str(rule.get("slot_id")) for rule in repaired if rule.get("slot_id")}
        discarded_slots = raw_generated_slots - repaired_slots
        if discarded_slots:
            player.monster_acquired_bloodline_traits = [
                trait_id for trait_id in player.monster_acquired_bloodline_traits
                if trait_id not in discarded_slots
            ]
        changed = True
    if isinstance(player.monster_custom_lineage, dict):
        lineage_id = str(
            player.monster_custom_lineage.get("id")
            or player.monster_custom_lineage_id
            or f"custom-lineage-{uuid.uuid4().hex}"
        )
        if player.monster_custom_lineage.get("id") != lineage_id:
            player.monster_custom_lineage["id"] = lineage_id
            changed = True
        if player.monster_custom_lineage_id != lineage_id:
            player.monster_custom_lineage_id = lineage_id
            changed = True
    elif player.monster_custom_lineage_id is not None:
        player.monster_custom_lineage_id = None
        changed = True
    return changed


def _path_value(player: Player, path: str) -> Any:
    mapping = {
        "player.realm_index": player.realm_index,
        "player.layer": player.layer,
        "player.world": player.world,
        "player.monster_species_id": player.monster_species_id,
        "player.monster.evolution_id": player.monster_evolution_id,
        "player.monster.adaptations": player.monster_adaptations,
        "player.monster.imprints": player.monster_bloodline_imprints,
        "player.monster.history": player.monster_evolution_history,
        "player.monster.qi_level": qi_level(player.qi_experience.get("monster", 0.0)),
    }
    if path not in mapping:
        raise ValueError(f"未知血脉条件路径：{path}")
    return mapping[path]


def requirement_met(requirement: dict[str, Any], player: Player) -> bool:
    if not requirement:
        return True
    if "all" in requirement:
        return all(requirement_met(child, player) for child in requirement["all"])
    if "any" in requirement:
        return any(requirement_met(child, player) for child in requirement["any"])
    if "not" in requirement:
        return not requirement_met(requirement["not"], player)
    left = _path_value(player, str(requirement["path"]))
    right = requirement.get("value")
    op = str(requirement.get("op", "eq"))
    operations = {
        "eq": lambda a, b: a == b, "neq": lambda a, b: a != b,
        "gt": lambda a, b: a > b, "gte": lambda a, b: a >= b,
        "lt": lambda a, b: a < b, "lte": lambda a, b: a <= b,
        "contains": lambda a, b: b in a, "in": lambda a, b: a in b,
    }
    return bool(operations[op](left, right))


def _requirement_display(requirement: dict[str, Any], player: Player) -> dict[str, Any]:
    if "all" in requirement or "any" in requirement:
        kind = "all" if "all" in requirement else "any"
        children = [_requirement_display(child, player) for child in requirement[kind]]
        return {
            "kind": kind, "met": all(child["met"] for child in children) if kind == "all" else any(child["met"] for child in children),
            "children": children,
        }
    if "not" in requirement:
        child = _requirement_display(requirement["not"], player)
        return {"kind": "not", "met": not child["met"], "children": [child]}
    path, value = str(requirement["path"]), requirement.get("value")
    names = MONSTER_BLOODLINE_SETTINGS
    value_name = str(value)
    if path == "player.monster.adaptations":
        value_name = names.get("adaptations", {}).get(str(value), {}).get("name", value_name)
    elif path == "player.monster.imprints":
        value_name = names.get("imprints", {}).get(str(value), {}).get("name", value_name)
    labels = {
        "player.realm_index": "境界序号", "player.layer": "当前层级", "player.world": "所在界面",
        "player.monster_species_id": "本源谱系", "player.monster.evolution_id": "当前形态",
        "player.monster.adaptations": "适应印记", "player.monster.imprints": "血脉印记",
        "player.monster.history": "进化历史", "player.monster.qi_level": "妖气等级",
    }
    op_names = {"eq": "为", "neq": "不为", "gte": "至少", "gt": "高于", "lte": "至多", "lt": "低于", "contains": "拥有", "in": "属于"}
    return {
        "kind": "leaf", "met": requirement_met(requirement, player),
        "text": f"{labels.get(path, path)}{op_names.get(str(requirement.get('op', 'eq')), '满足')}{value_name}",
    }


def evolution_candidates(player: Player) -> list[dict[str, Any]]:
    target_realm = player.realm_index + 1
    current_id = str(player.monster_evolution_id or "")
    rows = [
        node for node in MONSTER_EVOLUTIONS.values()
        if node.get("species") == player.monster_species_id
        and current_id in node.get("parents", [])
        and int(node.get("realm_index", -1)) == target_realm
    ]
    result: list[dict[str, Any]] = []
    for node in sorted(rows, key=lambda row: (int(row.get("order", 100)), row["id"])):
        requirement = node.get("requirements", {})
        checks = _requirement_display(requirement, player) if requirement else {"kind": "all", "met": True, "children": []}
        qi_required = int(node.get("monster_qi_level", 0))
        qi_current = qi_level(player.qi_experience.get("monster", 0.0))
        enabled = checks["met"] and qi_current >= qi_required
        result.append({
            "id": node["id"], "name": node["name"], "description": node.get("description", ""),
            "enabled": enabled, "profile": dict(node["profile"]),
            "traits": [public_bloodline_trait(trait) for trait in resolved_bloodline_traits(node)],
            "abilities": list(node.get("abilities", [])),
            "lifespan_gain": int(node.get("lifespan_gain", 0)),
            "monster_qi_level": {"current": qi_current, "required": qi_required, "met": qi_current >= qi_required},
            "requirements": checks,
            "custom_lineage": is_self_lineage_node(str(node["id"])),
            "custom_lineage_stage": self_lineage_stage(str(node["id"])),
        })
    if not result and current_id in MONSTER_EVOLUTIONS:
        current = MONSTER_EVOLUTIONS[current_id]
        result.append({
            "id": "__stable__", "name": f"稳固{current['name']}",
            "description": "当前 DLC 的进化树已抵达边界；保持本相继续成长，不会阻断后续境界。",
            "enabled": True, "profile": dict(current["profile"]),
            "traits": [public_bloodline_trait(trait) for trait in resolved_bloodline_traits(current)],
            "abilities": list(current.get("abilities", [])), "lifespan_gain": 0,
            "monster_qi_level": {"current": qi_level(player.qi_experience.get("monster", 0.0)), "required": 0, "met": True},
            "requirements": {"kind": "all", "met": True, "children": []},
            "stable_continuation": True,
        })
    return result


def public_monster_bloodline(player: Player) -> dict[str, Any]:
    visible = player.path == "monster"
    if not visible:
        return {"visible": False, "available": bloodline_content_available()}
    if not bloodline_content_available():
        return {
            "visible": True, "available": False,
            "reason": "血脉、进化与祖血内容已冻结；妖修改走本体普通突破，成功突破大境界时随机获得一项较弱的通用特质。",
            "general_traits_active": True,
            "general_traits": [
                public_general_monster_trait(trait_id)
                for trait_id in dict.fromkeys(map(str, player.monster_general_traits))
                if trait_id in GENERAL_MONSTER_TRAIT_REGISTRY
            ],
            "general_trait_pool_size": len(GENERAL_MONSTER_TRAIT_REGISTRY),
        }
    ensure_monster_bloodline_state(player)
    species = MONSTER_SPECIES[player.monster_species_id]
    node = MONSTER_EVOLUTIONS[player.monster_evolution_id]
    adaptations = MONSTER_BLOODLINE_SETTINGS.get("adaptations", {})
    imprints = MONSTER_BLOODLINE_SETTINGS.get("imprints", {})
    at_major = player.layer >= REALMS[player.realm_index].layers
    awaiting = bool(player.awaiting_major_breakthrough and at_major and player.opportunity >= opportunity_required(player))
    custom_config = MONSTER_BLOODLINE_SETTINGS.get("custom_lineage", {})
    current_self_stage = self_lineage_stage(str(player.monster_evolution_id))
    return {
        "visible": True, "available": True,
        "species": {"id": player.monster_species_id, **species},
        "current": {
            "id": node["id"], "name": node["name"], "description": node.get("description", ""),
            "profile": dict(node["profile"]),
            "traits": [public_bloodline_trait(trait) for trait in resolved_bloodline_traits(node)],
            "abilities": list(node.get("abilities", [])),
        },
        "acquired_traits": [
            *[public_bloodline_trait(trait_id) for trait_id in acquired_species_bloodline_traits(player)],
            *[public_generated_trait(rule) for rule in generated_species_bloodline_traits(player)],
        ],
        "species_trait_pool": {
            "acquired": len(acquired_species_bloodline_traits(player)) + len(generated_species_bloodline_traits(player)),
            "total": MAX_TRAITS,
        },
        "history": [
            {"id": node_id, "name": MONSTER_EVOLUTIONS.get(node_id, {"name": node_id})["name"]}
            for node_id in player.monster_evolution_history
        ],
        "adaptations": [{"id": item, **adaptations[item]} for item in player.monster_adaptations if item in adaptations],
        "imprints": [{"id": item, **imprints[item]} for item in player.monster_bloodline_imprints if item in imprints],
        "general_traits_active": False,
        "general_traits": [
            public_general_monster_trait(trait_id)
            for trait_id in dict.fromkeys(map(str, player.monster_general_traits))
            if trait_id in GENERAL_MONSTER_TRAIT_REGISTRY
        ],
        "awaiting_evolution": awaiting,
        "candidates": evolution_candidates(player) if awaiting else [],
        "custom_lineage": public_custom_lineage(player, custom_config),
        "custom_lineage_retroactive_available": bool(current_self_stage and not player.monster_custom_lineage),
        "irreversible": True,
    }


class MonsterBloodlineSystemMixin:
    def _advance_monster_bloodline_year(self, game: GameState) -> None:
        player = game.player
        if player.path != "monster" or not bloodline_content_available():
            return
        ensure_monster_bloodline_state(player)
        location = self.maps.location(player.world, self.maps.normalize_location(player.world, player.location_id))
        themes = set(map(str, location.get("themes", [])))
        location_id = str(location.get("id", ""))
        for adaptation_id, definition in MONSTER_BLOODLINE_SETTINGS.get("adaptations", {}).items():
            if adaptation_id in player.monster_adaptations:
                continue
            matching = bool(themes & set(map(str, definition.get("themes", [])))) or location_id in definition.get("locations", [])
            if not matching:
                continue
            progress = int(player.monster_adaptation_progress.get(adaptation_id, 0)) + 1
            player.monster_adaptation_progress[adaptation_id] = progress
            threshold = int(definition.get("years", 10))
            if progress >= threshold:
                player.monster_adaptations.append(adaptation_id)
                game.history.append(HistoryRecord(
                    f"SYS_MONSTER_ADAPT_{adaptation_id.upper()}", 1, player.age, "生命适应", adaptation_id, "acquired",
                    f"你在{location['name']}的漫长生活改变了本体，获得适应印记【{definition['name']}】。",
                    {"monster_adaptation": adaptation_id}, ["system", "monster", "bloodline", "adaptation", "milestone"],
                ))

    def _monster_travel_multiplier(self, player: Player, destination: str) -> float:
        profile = active_bloodline_profile(player)
        node = MONSTER_EVOLUTIONS.get(str(profile.get("id") or ""), {})
        multiplier = float(profile.get("travel_multiplier", 1.0))
        required_themes = set(map(str, node.get("travel_themes", [])))
        if not required_themes:
            return multiplier
        origin = self.maps.location(player.world, self.maps.normalize_location(player.world, player.location_id))
        target = self.maps.location(player.world, destination)
        return multiplier if required_themes & (set(origin.get("themes", [])) | set(target.get("themes", []))) else 1.0

    def _validate_monster_evolution(self, game: GameState, evolution_id: str) -> dict[str, Any]:
        player = game.player
        if player.path != "monster" or not bloodline_content_available():
            raise ValueError("当前角色没有可用的妖修血脉体系")
        if game.pending_event or game.active_trial:
            raise ValueError("请先处理当前事件或渡劫")
        if self._manual_breakthrough_kind(player) != "major" or not player.awaiting_major_breakthrough:
            raise ValueError("尚未抵达需要蜕变的大境界瓶颈")
        required = opportunity_required(player)
        if player.opportunity < required:
            raise ValueError("机缘尚未圆满")
        candidate = next((row for row in evolution_candidates(player) if row["id"] == evolution_id), None)
        if not candidate:
            raise ValueError("所选形态不属于当前进化支系")
        if not candidate["enabled"]:
            raise ValueError("尚未满足这一形态的进化条件")
        return candidate

    def _complete_monster_evolution(
        self, game: GameState, evolution_id: str, candidate: dict[str, Any],
    ) -> dict[str, Any]:
        player = game.player
        required = opportunity_required(player)
        rng = decode_rng(game.seed, game.rng_state)
        old_label = public_player(player)["realm_name"]
        old_node = MONSTER_EVOLUTIONS[player.monster_evolution_id]
        old_realm_index = player.realm_index
        old_world = player.world
        player.opportunity = max(0.0, player.opportunity - required)
        self._consume_breakthrough_aids(player, f"major:{player.realm_index}")
        if evolution_id != "__stable__":
            player.monster_evolution_id = evolution_id
            player.monster_evolution_history.append(evolution_id)
        self._complete_major_breakthrough(game, rng, old_label)
        awakened_trait = grant_generated_species_bloodline_trait(player, rng)
        if awakened_trait:
            game.history.append(HistoryRecord(
                "SYS_MONSTER_SPECIES_TRAIT", 1, player.age, "族血觉醒",
                awakened_trait["id"], "acquired",
                f"大境界蜕变唤醒了本族血脉特质【{awakened_trait['name']}】：{awakened_trait['description']}",
                {
                    "species_id": player.monster_species_id,
                    "trait_id": awakened_trait["id"],
                    "generated_rule": True,
                    "realm_index": player.realm_index,
                },
                ["system", "monster", "bloodline", "trait", "major", "milestone"],
            ))
        if old_realm_index == 8 and player.realm_index == 9:
            self._prepare_permanent_world_transition(game)
            player.world = "nether"
            player.location_id = self.maps.default_location("nether")
            self._clear_market(game)
            game.history.append(HistoryRecord(
                "SYS_MONSTER_NETHER_ASCENSION", 1, player.age, "飞升幽冥界", evolution_id, "ascended",
                f"血脉蜕变撕开上界祖路，你从{WORLD_SYSTEMS['world_names'][old_world]}飞升幽冥界。",
                {"world": [old_world, "nether"], "realm_index": [8, 9]},
                ["system", "monster", "bloodline", "ascension", "nether", "milestone"],
            ))
        lifespan_gain = int(candidate.get("lifespan_gain", 0))
        if lifespan_gain and player.lifespan is not None:
            player.lifespan += lifespan_gain
        player.hp, player.mp = max_hp(player), max_mp(player)
        new_node = MONSTER_EVOLUTIONS[player.monster_evolution_id]
        game.history.append(HistoryRecord(
            "SYS_MONSTER_EVOLUTION", 1, player.age, "血脉蜕变", evolution_id, "evolved",
            (
                f"你舍弃其他生命可能，从【{old_node['name']}】不可逆地蜕变为【{new_node['name']}】。"
                if evolution_id != "__stable__" else f"你稳固【{old_node['name']}】本相，以既有生命形态继续前行。"
            ) + (f" 此次蜕变令寿元增长 {lifespan_gain} 年。" if lifespan_gain else ""),
            {"from": old_node["id"], "to": new_node["id"], "lifespan_gain": lifespan_gain},
            ["system", "monster", "bloodline", "evolution", "major", "milestone"],
        ))
        self._ensure_market(game, rng)
        game.rng_state = encode_rng(rng)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def evolve_monster(self, game_id: str, evolution_id: str) -> dict[str, Any]:
        game = self._load(game_id)
        candidate = self._validate_monster_evolution(game, evolution_id)
        if is_self_lineage_node(evolution_id):
            raise ValueError("自成血脉必须先进入立祖界面，核对功业并确认祖血规则")
        return self._complete_monster_evolution(game, evolution_id, candidate)

    def prepare_custom_lineage(self, game_id: str, evolution_id: str) -> dict[str, Any]:
        """Open the editor without mutating or saving the game."""
        game = self._load(game_id)
        player = game.player
        config = MONSTER_BLOODLINE_SETTINGS.get("custom_lineage", {})
        retroactive = evolution_id == "__retroactive__"
        if retroactive:
            stage = self_lineage_stage(player.monster_evolution_id)
            if not stage or player.monster_custom_lineage:
                raise ValueError("当前存档不需要补刻祖血")
        else:
            self._validate_monster_evolution(game, evolution_id)
            stage = self_lineage_stage(evolution_id)
            if not stage:
                raise ValueError("所选进化不是自成血脉路线")
            if stage > 1 and not player.monster_custom_lineage:
                raise ValueError("旧版自立血脉须先完成一次补刻祖血")
        shown = self.present(game)
        shown["monster_bloodline"]["custom_lineage_editor"] = editor_payload(
            game, config, stage=stage, evolution_id=evolution_id, retroactive=retroactive,
        )
        return shown

    def confirm_custom_lineage(
        self, game_id: str, evolution_id: str, name: str, rules: Any,
    ) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        config = MONSTER_BLOODLINE_SETTINGS.get("custom_lineage", {})
        retroactive = evolution_id == "__retroactive__"
        candidate: dict[str, Any] | None = None
        if retroactive:
            stage = self_lineage_stage(player.monster_evolution_id)
            if not stage or player.monster_custom_lineage:
                raise ValueError("当前存档不需要补刻祖血")
        else:
            candidate = self._validate_monster_evolution(game, evolution_id)
            stage = self_lineage_stage(evolution_id)
            if not stage:
                raise ValueError("所选进化不是自成血脉路线")
            if stage > 1 and not player.monster_custom_lineage:
                raise ValueError("旧版自立血脉须先完成一次补刻祖血")
        clean_name = " ".join(str(name or "").strip().split())
        if not 2 <= len(clean_name) <= 16 or any(ord(char) < 32 for char in clean_name):
            raise ValueError("祖血名称须为 2 至 16 个可显示字符")
        existing = player.monster_custom_lineage if isinstance(player.monster_custom_lineage, dict) else None
        if existing and clean_name != existing.get("name"):
            raise ValueError("立祖后不能改名")
        deeds = lineage_deed_budget(game, config)
        slots = int(config.get("rule_slots", {}).get(str(stage), 0))
        normalized, spent = normalize_rules(
            rules, config, slots=slots, budget=int(deeds["total"]),
            existing_rules=list(existing.get("rules", [])) if existing else None,
        )
        if not existing and not normalized:
            raise ValueError("立祖或补刻祖血时至少需要铭刻一条规则")
        lineage = copy.deepcopy(existing) if existing else {
            "id": f"custom-lineage-{uuid.uuid4().hex}",
            "founder_age": player.age,
            "founder_species_id": player.monster_species_id,
            "created_realm_index": 9,
        }
        lineage.update({
            "name": clean_name, "rules": normalized, "spent_points": spent,
            "finalized_stage": stage,
        })
        player.monster_custom_lineage = lineage
        player.monster_custom_lineage_id = str(lineage["id"])
        game.history.append(HistoryRecord(
            "SYS_CUSTOM_LINEAGE_RETROACTIVE" if retroactive else "SYS_CUSTOM_LINEAGE",
            1, player.age, "补刻祖血" if retroactive else config.get("stage_names", {}).get(str(stage), "立祖"),
            evolution_id, "inscribed",
            (
                f"你为旧版自立血脉补刻祖谱【{clean_name}】，铭定 {len(normalized)} 条祖血规则。"
                if retroactive else f"你将【{clean_name}】推进至{config.get('stage_names', {}).get(str(stage), '立祖')}，现有 {len(normalized)} 条祖血规则。"
            ),
            {"custom_lineage_id": lineage["id"], "stage": stage, "spent_points": spent},
            ["system", "monster", "bloodline", "custom_lineage", "milestone"],
        ))
        if retroactive:
            game.updated_at = now_iso()
            self.store.save(game)
            return self.present(game)
        assert candidate is not None
        return self._complete_monster_evolution(game, evolution_id, candidate)

    def grant_monster_imprint(self, player: Player, imprint_id: str) -> bool:
        if imprint_id not in MONSTER_BLOODLINE_SETTINGS.get("imprints", {}):
            raise ValueError("未知血脉印记")
        if imprint_id in player.monster_bloodline_imprints:
            return False
        player.monster_bloodline_imprints.append(imprint_id)
        return True
