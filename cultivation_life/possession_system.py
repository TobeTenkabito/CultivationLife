from __future__ import annotations

import copy
from typing import Any

from .content_registry import PATH_NAMES, REALMS, TECHNIQUE_CATALOG
from .models import Player, Technique


_BODY_FIELDS = (
    "name", "spirit_root", "additional_roots", "acquired_root", "born_rootless",
    "realm_index", "layer", "lifespan", "opportunity",
    "qi_experience", "path", "race", "hp", "mp", "body_training", "body_progress",
    "technique", "support_technique", "combat_techniques", "known_techniques",
    "body_technique", "divine_sense_technique", "transformation_technique",
    "divine_sense_rank", "divine_sense_experience", "awaiting_major_breakthrough",
    "awaiting_minor_breakthrough", "active_breakthrough_aids", "breakthrough_pity",
)


def is_possessed(player: Player) -> bool:
    return isinstance(player.ghost_host_body, dict) and isinstance(player.ghost_core_state, dict)


def has_ghost_core(player: Player) -> bool:
    return player.path == "ghost" or is_possessed(player)


def current_body_age(player: Player) -> int:
    """Return biological age without repurposing the monotonic world clock."""
    if is_possessed(player):
        return max(0, int((player.ghost_host_body or {}).get("age", player.age)))
    return max(0, int(player.age))


def advance_player_age(player: Player, years: int = 1) -> None:
    """Advance world time and, while possessed, the host body in parallel."""
    elapsed = max(0, int(years))
    player.age += elapsed
    if is_possessed(player):
        host = player.ghost_host_body or {}
        host["age"] = max(0, int(host.get("age", player.age - elapsed))) + elapsed


def migrate_possession_timeline(player: Player) -> bool:
    """Separate legacy saves where player.age was overwritten by host age."""
    if not is_possessed(player):
        return False
    host = player.ghost_host_body or {}
    core = player.ghost_core_state or {}
    if int(host.get("timeline_version", 0)) >= 2:
        return False

    # Legacy saves advanced player.age as the host's biological age while the
    # original world coordinate remained in entered_age/core.age.
    legacy_body_age = max(0, int(player.age))
    initial_body_age = max(0, int(host.get("age", legacy_body_age)))
    entered_world_age = max(0, int(host.get("entered_age", core.get("age", legacy_body_age))))
    elapsed = max(0, legacy_body_age - initial_body_age)
    player.age = entered_world_age + elapsed
    host["age"] = legacy_body_age
    host["timeline_version"] = 2
    host["entered_world_age"] = entered_world_age
    core.pop("age", None)
    return True


def _snapshot_body(player: Player) -> dict[str, Any]:
    raw = player.to_dict()
    return {field: copy.deepcopy(raw.get(field)) for field in _BODY_FIELDS}


def _restore_body(player: Player, snapshot: dict[str, Any]) -> None:
    technique_fields = {
        "technique", "support_technique", "body_technique",
        "divine_sense_technique", "transformation_technique",
    }
    for field in _BODY_FIELDS:
        value = copy.deepcopy(snapshot.get(field))
        if field in technique_fields:
            value = Technique(**value) if isinstance(value, dict) else None
        elif field in {"combat_techniques", "known_techniques"}:
            value = [Technique(**row) for row in (value or [])]
        setattr(player, field, value)


def possession_limit(player: Player) -> int | None:
    techniques: list[Technique | None] = [
        player.technique, player.support_technique, player.body_technique,
        player.divine_sense_technique, *player.combat_techniques, *player.known_techniques,
    ]
    if is_possessed(player):
        core = player.ghost_core_state or {}
        saved = [core.get("technique"), core.get("support_technique"), core.get("body_technique"),
                 core.get("divine_sense_technique"), *(core.get("combat_techniques") or []),
                 *(core.get("known_techniques") or [])]
        techniques = [Technique(**row) for row in saved if isinstance(row, dict)]
    if any(entry and entry.ignore_possession_limit for entry in techniques):
        return None
    return 1 + max((int(entry.possession_limit_bonus) for entry in techniques if entry), default=0)


def can_possess(player: Player, target: dict[str, Any]) -> tuple[bool, str]:
    if not has_ghost_core(player) or is_possessed(player):
        return False, "只有未寄身的鬼修可以夺舍"
    if str(target.get("race", "human")) not in {"human", "demon", "immortal"}:
        return False, "目标并非可夺舍的人形生灵"
    if int(target.get("realm_index", 0)) > int(player.realm_index):
        return False, "不能夺舍境界高于自身的目标"
    limit = possession_limit(player)
    if limit is not None and player.possession_count >= limit:
        return False, f"本魂最多成功夺舍 {limit} 次"
    return True, ""


def enter_host_body(player: Player, target: dict[str, Any]) -> dict[str, Any]:
    allowed, reason = can_possess(player, target)
    if not allowed:
        raise ValueError(reason)
    core = _snapshot_body(player)
    original_name = str(core["name"])
    realm_index = max(0, min(len(REALMS) - 1, int(target.get("realm_index", 0))))
    layer = max(1, min(REALMS[realm_index].layers, int(target.get("layer", 1))))
    target_path = str(target.get("path", "dao"))
    target_name = str(target.get("name", "无名宿主"))
    target_technique = None
    technique_id = target.get("main_technique_id")
    if technique_id in TECHNIQUE_CATALOG:
        target_technique = copy.deepcopy(TECHNIQUE_CATALOG[str(technique_id)])
    player.ghost_core_state = core
    world_age = player.age
    target_age = max(0, int(target.get("age", world_age)))
    player.ghost_host_body = {
        "id": str(target.get("id") or target.get("npc_id") or "host"),
        "npc_id": target.get("npc_id"), "name": target_name,
        "original_ghost_name": original_name, "entered_age": world_age,
        "entered_world_age": world_age, "timeline_version": 2,
        "age": target_age, "lifespan": target.get("lifespan"),
        "source": str(target.get("source", "captive")),
        "path": target_path, "path_name": PATH_NAMES.get(target_path, target_path),
        "realm_index": realm_index, "layer": layer,
    }
    player.name = f"{target_name}（{original_name}）"
    player.spirit_root = str(target.get("spirit_root", "none"))
    player.additional_roots = list(target.get("additional_roots", []))
    player.acquired_root = bool(target.get("acquired_root", False))
    player.born_rootless = player.spirit_root == "none"
    player.realm_index = realm_index
    player.layer = layer
    player.path = target_path
    player.race = str(target.get("race", "human"))
    player.lifespan = target.get("lifespan")
    if player.lifespan is None:
        realm_lifespan = REALMS[realm_index].lifespan
        player.lifespan = (
            max(target_age + 1, int(realm_lifespan[1]))
            if realm_lifespan else None
        )
    player.opportunity = float(target.get("opportunity", 0.0))
    player.qi_experience = {"spirit": 0.0, "demon": 0.0, "monster": 0.0, "yin": 0.0}
    player.body_training = max(0, int(target.get("body_training", realm_index * 2)))
    player.body_progress = 0.0
    player.technique = target_technique
    player.support_technique = None
    player.combat_techniques = []
    player.known_techniques = [copy.deepcopy(target_technique)] if target_technique else []
    player.body_technique = None
    player.divine_sense_technique = None
    player.transformation_technique = None
    player.awaiting_major_breakthrough = False
    player.awaiting_minor_breakthrough = False
    player.active_breakthrough_aids = []
    player.breakthrough_pity = {}
    player.ghost_attachment = None
    player.ghost_captor = None
    player.possession_count += 1
    player.milestones["ghost_possessions"] = int(player.milestones.get("ghost_possessions", 0)) + 1
    # The host starts wounded after the soul struggle, but alive.
    expected = max(30.0, REALMS[realm_index].base_power ** 0.5 * 16 + layer * 8)
    player.hp = max(1.0, expected * 0.7)
    player.mp = max(0.0, (40 + REALMS[realm_index].base_power ** 0.5 * 20 + layer * 11) * 0.7)
    return copy.deepcopy(player.ghost_host_body)


def leave_host_body(player: Player) -> dict[str, Any]:
    if not is_possessed(player):
        raise ValueError("当前并未夺舍寄身")
    host = copy.deepcopy(player.ghost_host_body or {})
    core = copy.deepcopy(player.ghost_core_state or {})
    count = player.possession_count
    _restore_body(player, core)
    player.ghost_core_state = None
    player.ghost_host_body = None
    player.possession_count = count
    player.alive = True
    player.death_reason = None
    return host
