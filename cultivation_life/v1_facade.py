"""Read-only V1 browser contract over the V2 simulation projections.

The V1 web bundle is a frozen product asset.  It must not know that the
simulation was replaced, so all shape conversion lives at this HTTP boundary.
"""

from __future__ import annotations

import math
from typing import Any


def config_view(document: dict[str, Any]) -> dict[str, Any]:
    result = dict(document)
    roots = dict(document.get("roots", {}))
    result.update({
        "spirit_roots": roots,
        "spirit_root_details": document.get("root_details") or {
            key: {"tier": "灵根", "efficiency": 1.0} for key in roots
        },
        "technique_elements": dict(document.get("technique_elements", {})),
        "factions": dict(document.get("factions", {})),
        "qi_sources": dict(document.get("qi_sources", {})),
        "quick_starts": list(document.get("quick_starts", [])),
        "monster_species": dict(document.get("monster_species", {})),
    })
    result["extensions"] = [
        {
            **row,
            "kind_name": "DLC" if row.get("kind") == "dlc" else "MOD",
            "next_enabled": None,
            "requires": list(row.get("requires", [])),
        }
        for row in document.get("extensions", [])
    ]
    return result


def save_list_view(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"games": [
        {
            **row,
            "id": row.get("id", row.get("game_id")),
            "name": row.get("name", row.get("player_name", "无名散修")),
        }
        for row in rows
    ]}


def achievement_view(rows: list[dict[str, Any]]) -> dict[str, Any]:
    achievements = [
        {**row, "unlocked": False, "unlocked_at": None, "player_name": None}
        for row in rows
    ]
    return {
        "achievements": achievements,
        "unlocked": 0,
        "total": len(achievements),
        "progress_available": False,
    }


def _relation(row: dict[str, Any]) -> dict[str, Any]:
    other = row.get("other") or row.get("character") or row.get("requester") or {}
    return {
        **dict(other),
        **dict(row.get("metadata", {})),
        "relation_id": row.get("relation_id"),
        "kind": row.get("kind"),
        "role": row.get("role"),
        "direction": row.get("direction"),
        "ascension_eligible": row.get("ascension_eligible"),
    }


def _ghost_view(system: dict[str, Any] | None, player: dict[str, Any]) -> dict[str, Any]:
    if not system or not system.get("available"):
        return dict(system or {"available": False})
    soul = dict(system.get("soul", {}))
    hp_current = float(soul.get("intrinsic_hp", 100))
    hp_reference = max(1.0, float(soul.get("intrinsic_hp_reference", hp_current)))
    mp_current = float(soul.get("intrinsic_mp", 100))
    mp_reference = max(1.0, float(soul.get("intrinsic_mp_reference", mp_current)))
    integrity = max(0.0, min(1.0, (hp_current / hp_reference + mp_current / mp_reference) / 2))
    bound = {str(row.get("id")): row for row in system.get("bound_souls", [])}
    imprints = [
        {"realm_name": realm_id, "layer": 1, "count": count}
        for realm_id, count in dict(soul.get("reincarnation_imprints", {})).items()
    ]
    mark_count = sum(int(row["count"]) for row in imprints)
    wangsheng = int(soul.get("wangsheng", 0))
    phase_two = {
        "enabled": True,
        **system,
        "slots": [
            {**slot, "soul": bound.get(str(slot.get("soul_id")))}
            for slot in system.get("slots", [])
        ],
        "attachable_items": list(system.get("attachable_items", [])),
        "bound_souls": list(system.get("bound_souls", [])),
    }
    cultivation = dict(player.get("cultivation", {}))
    return {
        **system,
        "erosion_rate_pp": float(soul.get("erosion_rate_pp", 0)),
        "erosion_time": {
            "elapsed_equivalent_years": float(soul.get("erosion_time_progress", 0)),
            "time_unit_years": 1,
            "progress_ratio": float(soul.get("erosion_time_progress", 0)),
        },
        "wangsheng": wangsheng,
        "wangsheng_cost": 2,
        "wangsheng_reduction_pp": 0.02,
        "wangsheng_available_uses": wangsheng // 2,
        "can_spend_wangsheng": wangsheng >= 2,
        "intrinsic_hp": {
            "current": hp_current, "reference": hp_reference,
            "carry_ratio": hp_current / hp_reference,
            "external_raw": 0, "external_effective": 0,
        },
        "intrinsic_mp": {
            "current": mp_current, "reference": mp_reference,
            "carry_ratio": mp_current / mp_reference,
            "external_raw": 0, "external_effective": 0,
        },
        "soul_integrity": {
            "ratio": integrity,
            "label": "魂基稳固" if integrity >= 0.8 else "魂基有损" if integrity >= 0.5 else "魂基危殆",
        },
        "imprints": imprints,
        "total_imprints": mark_count,
        "effective_marks": mark_count,
        "breakthrough_probability_cap": 0.98,
        "highwater": {
            "name": dict(soul.get("historical_peak", {})).get("realm_id")
            or cultivation.get("realm_name", "未记录")
        },
        "last_anchor": soul.get("last_reincarnation"),
        "phase_two": phase_two,
    }


def _number(value: Any, default: float = 0.0) -> float:
    """Return a JSON-safe finite number for the legacy browser contract."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _battle_unit(snapshot: dict[str, Any], *, kind_name: str) -> dict[str, Any]:
    power = _number(snapshot.get("power"))
    return {
        **snapshot,
        "id": snapshot.get("entity_id", snapshot.get("id")),
        "name": str(snapshot.get("name") or "无名修士"),
        "kind_name": kind_name,
        "power": power,
        "engaged_power": power,
        "commitment": _number(snapshot.get("commitment"), 1.0),
    }


def _combat_report_view(
    report: dict[str, Any] | None, actor_id: str,
) -> dict[str, Any] | None:
    """Translate a canonical V2 combat record into the frozen V1 report schema.

    The conversion deliberately consumes the historical per-round snapshots.  It
    never reads the character's current HP/MP, so reopening an old report remains
    deterministic after healing, travelling, saving, or loading.
    """
    if not report:
        return None
    attacker_id = str(report.get("attacker_id", ""))
    target_id = str(report.get("target_id", ""))
    actor_is_attacker = actor_id != target_id
    player_id = attacker_id if actor_is_attacker else target_id
    enemy_id = target_id if actor_is_attacker else attacker_id
    attacker = dict(report.get("attacker") or {})
    target = dict(report.get("target") or {})
    player = attacker if actor_is_attacker else target
    enemy = target if actor_is_attacker else attacker
    mode = str(report.get("mode") or "standard")

    player_members = list(player.get("party_members", []))
    enemy_members = list(enemy.get("members", []))
    player_roster = [_battle_unit(player, kind_name="主将")]
    player_roster.extend(
        _battle_unit(dict(row), kind_name="同伴") for row in player_members
    )
    enemy_roster = (
        [_battle_unit(dict(row), kind_name="敌方成员") for row in enemy_members]
        if enemy_members else [_battle_unit(enemy, kind_name="敌手")]
    )

    names = {
        attacker_id: str(attacker.get("name") or "进攻方"),
        target_id: str(target.get("name") or "防守方"),
    }
    stat_names = {
        "might": "威能", "guard": "防御", "mobility": "身法",
        "sense": "神识", "sustain": "续战", "breach": "破法",
    }
    player_stats = dict(player.get("stats") or {})
    enemy_stats = dict(enemy.get("stats") or {})
    stat_comparison = [
        {
            "name": label,
            "player": _number(player_stats.get(key)),
            "enemy": _number(enemy_stats.get(key)),
        }
        for key, label in stat_names.items()
    ]

    rounds: list[dict[str, Any]] = []
    prior_hp = {
        attacker_id: _number(attacker.get("max_hp")) * _number(attacker.get("hp_ratio"), 1),
        target_id: _number(target.get("max_hp")) * _number(target.get("hp_ratio"), 1),
    }
    prior_mp = {
        attacker_id: _number(attacker.get("mp_ratio"), 1),
        target_id: _number(target.get("mp_ratio"), 1),
    }
    for index, raw_round in enumerate(report.get("rounds") or [], 1):
        battle_round = dict(raw_round)
        exchanges = list(battle_round.get("exchanges") or [])
        hp = {str(key): _number(value) for key, value in dict(battle_round.get("hp") or {}).items()}
        hp_ratios = {
            str(key): _number(value)
            for key, value in dict(battle_round.get("hp_ratios") or {}).items()
        }
        mp_ratios = {
            str(key): _number(value)
            for key, value in dict(battle_round.get("mp_ratios") or {}).items()
        }
        # Reports written before full round snapshots existed are reconstructed
        # once from their damage ledger, allowing old V2 saves to remain readable.
        if not hp:
            hp = dict(prior_hp)
            for exchange in exchanges:
                defender_id = str(exchange.get("defender_id", ""))
                if defender_id in hp:
                    hp[defender_id] = max(
                        0.0, hp[defender_id] - _number(exchange.get("damage"))
                    )
        for entity_id, snapshot in ((attacker_id, attacker), (target_id, target)):
            maximum = max(1.0, _number(snapshot.get("max_hp"), 1))
            if entity_id not in hp:
                hp[entity_id] = maximum * hp_ratios.get(entity_id, 0.0)
            hp_ratios.setdefault(entity_id, hp[entity_id] / maximum)
            mp_ratios.setdefault(entity_id, prior_mp.get(entity_id, 0.0))
        first_exchange = dict(exchanges[0]) if exchanges else {}
        first_id = str(first_exchange.get("attacker_id", ""))
        if not first_id:
            initiative = str(battle_round.get("initiative", "attacker"))
            first_id = attacker_id if initiative == "attacker" else target_id
        events = [
            f"{names.get(str(exchange.get('attacker_id')), '一方')}出手，"
            f"{names.get(str(exchange.get('defender_id')), '对手')}损失"
            f" {_number(exchange.get('damage')):.1f} 战斗态势。"
            for exchange in exchanges
        ]
        for lineage_event in battle_round.get("lineage_events") or []:
            if isinstance(lineage_event, str):
                events.append(lineage_event)
            elif isinstance(lineage_event, dict):
                events.append(str(
                    lineage_event.get("summary")
                    or lineage_event.get("description")
                    or lineage_event.get("name")
                    or "血脉特性在本轮生效。"
                ))
        if not events:
            events.append("双方在本轮相互试探，未形成有效杀伤。")
        morale = {
            str(key): _number(value, 50.0)
            for key, value in dict(battle_round.get("morale") or {}).items()
        }
        rounds.append({
            "round": int(battle_round.get("round", index)),
            "initiative": "player" if first_id == player_id else "enemy",
            "events": events,
            "player_hp_ratio": hp_ratios[player_id],
            "enemy_hp_ratio": hp_ratios[enemy_id],
            "player_mp_ratio": mp_ratios[player_id],
            "player_combat_state": hp[player_id],
            "player_combat_state_max": max(1.0, _number(player.get("max_hp"), 1)),
            "enemy_combat_state": hp[enemy_id],
            "enemy_combat_state_max": max(1.0, _number(enemy.get("max_hp"), 1)),
            "player_morale": morale.get(player_id, 50.0),
            "enemy_morale": morale.get(enemy_id, 50.0),
        })
        prior_hp, prior_mp = hp, mp_ratios

    # Team combat is intentionally resolved as one aggregate contest in V2.
    # Represent that canonical resolution as one complete legacy round.
    if not rounds:
        final_ratios = {
            str(key): _number(value, 1.0)
            for key, value in dict(report.get("final_hp_ratios") or {}).items()
        }
        player_hp_ratio = final_ratios.get(player_id, _number(player.get("hp_ratio"), 1))
        enemy_hp_ratio = final_ratios.get(enemy_id, _number(enemy.get("hp_ratio"), 1))
        player_max = max(1.0, _number(player.get("max_hp"), _number(player.get("power"), 1)))
        enemy_max = max(1.0, _number(enemy.get("max_hp"), _number(enemy.get("power"), 1)))
        rounds.append({
            "round": 1, "initiative": "player",
            "events": ["双方队伍完成一次正面交锋，战局已定。"],
            "player_hp_ratio": player_hp_ratio,
            "enemy_hp_ratio": enemy_hp_ratio,
            "player_mp_ratio": _number(player.get("mp_ratio"), 1),
            "player_combat_state": player_max * player_hp_ratio,
            "player_combat_state_max": player_max,
            "enemy_combat_state": enemy_max * enemy_hp_ratio,
            "enemy_combat_state_max": enemy_max,
            "player_morale": _number(dict(report.get("final_morale") or {}).get(player_id), 50),
            "enemy_morale": _number(dict(report.get("final_morale") or {}).get(enemy_id), 50),
        })

    raw_outcome = str(report.get("outcome") or "stalemate")
    player_won = (
        raw_outcome == ("victory" if actor_is_attacker else "defeat")
    )
    objective = str(report.get("objective") or "duel")
    if raw_outcome == "stalemate":
        result = "victory_escape"
    elif player_won and bool(report.get("captured")):
        result = "captured"
    elif player_won and objective == "kill":
        result = "killed"
    else:
        result = "victory" if player_won else "defeat"
    player_power = _number(player.get("power"))
    enemy_power = max(1.0, _number(enemy.get("power"), 1))
    ratio = player_power / enemy_power
    assessment = (
        "碾压" if ratio >= 2 else "优势" if ratio >= 1.25
        else "势均力敌" if ratio >= 0.8 else "劣势" if ratio >= 0.5 else "绝境"
    )
    formations = dict(report.get("formations") or {})
    player_formation = formations.get(player_id)
    enemy_formation = formations.get(enemy_id)
    terrain = dict(report.get("terrain") or {})
    return {
        "id": report.get("id"),
        "age": int(report.get("ended_year", report.get("started_year", 0))),
        "title": f"与{enemy.get('name') or '敌方'}斗法",
        "result": result,
        "result_grade": "胜" if player_won else "平" if raw_outcome == "stalemate" else "败",
        "mode": "队伍战斗" if mode == "team" else "标准自动战斗",
        "objective": {"duel": "切磋", "kill": "击杀", "capture": "擒拿", "repel": "击退"}.get(objective, objective),
        "assessment": assessment,
        "battlefield_tags": [str(terrain.get("name") or "寻常地势")],
        "natural_terrain": str(terrain.get("name") or "寻常地势"),
        "artificial_conditions": [],
        "formation_profile": player_formation,
        "formation_integrity_end": _number(dict(player_formation or {}).get("integrity"), 1),
        "enemy_formation_profile": enemy_formation,
        "enemy_formation_integrity_end": _number(dict(enemy_formation or {}).get("integrity"), 1),
        "player_roster": player_roster,
        "enemy_roster": enemy_roster,
        "key_events": [rounds[-1]["events"][-1]],
        "stat_comparison": stat_comparison,
        "rounds": rounds,
    }


def _world_travel_view(
    player: dict[str, Any], world: dict[str, Any], data: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    world_id = str(world.get("world_id", ""))
    transition = dict(world.get("transition") or {})
    sealed = transition.get("sealed_cultivation")
    cultivation = dict(player.get("cultivation") or {})
    realm_index = int(cultivation.get("realm_index", 0))
    layer = int(cultivation.get("layer", 1))
    path = str(cultivation.get("path", ""))
    opportunity = _number(cultivation.get("opportunity"))
    required_opportunity = _number(cultivation.get("opportunity_required"), 1)
    alive = bool(player.get("alive"))
    trial_active = dict(data.get("trial") or {}).get("active") is not None
    interaction_open = data.get("pending_event") is not None
    ready = alive and not sealed and not trial_active and not interaction_open
    rules = dict(config.get("world_travel_rules") or {})
    required_realm = int(rules.get("required_realm", 8))
    celestial_realm = int(rules.get("celestial_required_realm", 9))
    sealed_upper = str(dict(sealed or {}).get("upper_world", ""))
    return {
        "can_ascend_celestial": bool(
            ready and world_id == "spirit" and realm_index == 8 and layer == 9
            and path in {"dao", "buddhist", "confucian"}
            and opportunity >= required_opportunity
        ),
        "can_ascend_asura": bool(
            ready and world_id == "true_demon" and realm_index == 8 and layer == 9
            and path == "demonic" and opportunity >= required_opportunity
        ),
        "can_return_human": bool(
            ready and world_id in {"spirit", "hell"}
            and realm_index >= required_realm
        ),
        "can_return_spirit": bool(
            alive and world_id == "human" and sealed_upper == "spirit"
        ),
        "can_return_hell": bool(
            alive and world_id == "human" and sealed_upper == "hell"
        ),
        "can_return_demon": bool(
            ready and world_id == "true_demon" and realm_index >= required_realm
        ),
        "can_return_true_demon": bool(
            alive and world_id == "demon" and sealed_upper == "true_demon"
        ),
        "can_descend_spirit": bool(
            ready and world_id == "celestial" and realm_index >= celestial_realm
        ),
        "can_return_celestial": bool(
            alive and world_id == "spirit" and sealed_upper == "celestial"
        ),
        "can_descend_true_demon": bool(
            ready and world_id == "asura" and realm_index >= celestial_realm
        ),
        "can_return_asura": bool(
            alive and world_id == "true_demon" and sealed_upper == "asura"
        ),
        "can_descend_phantom": bool(
            ready and world_id == "nether" and realm_index >= celestial_realm
        ),
        "can_descend_monster": bool(
            ready and world_id == "nether" and realm_index >= celestial_realm
        ),
        "can_return_nether": bool(
            alive and world_id in {"monster_realm", "phantom_underworld"}
            and sealed_upper == "nether"
        ),
        "suppressed": sealed is not None,
    }


def _ranking_view(
    player: dict[str, Any], characters: list[dict[str, Any]],
    world: dict[str, Any], config: dict[str, Any],
) -> dict[str, Any]:
    world_id = str(world.get("world_id", ""))
    if world_id not in {"spirit", "true_demon", "hell"}:
        return {"available": False, "entries": [], "player_rank": None}
    race_definitions = dict(config.get("race_details") or {})

    def entry(row: dict[str, Any], is_player: bool) -> dict[str, Any]:
        race_id = str(row.get("race", "human"))
        race = race_definitions.get(race_id, {})
        race_name = race.get("name", race_id) if isinstance(race, dict) else race
        return {
            "id": row.get("id"), "name": row.get("name", "无名修士"),
            "title": "玩家" if is_player else row.get("title", "上界修士"),
            "realm_index": int(row.get("realm_index", 0)),
            "layer": int(row.get("layer", 1)),
            "realm_name": row.get("realm_name", "修为未明"),
            "race": race_id, "race_name": str(race_name),
            "combat_power": _number(row.get("combat_power")),
            "is_player": is_player,
        }

    rows = [entry(row, False) for row in characters]
    rows.append(entry(player, True))
    rows.sort(key=lambda row: (
        -_number(row["combat_power"]), -int(row["realm_index"]),
        -int(row["layer"]), str(row["name"]),
    ))
    player_rank = next(
        index for index, row in enumerate(rows, 1) if row["is_player"]
    )
    entries = [{**row, "rank": index} for index, row in enumerate(rows[:20], 1)]
    world_name = str(world.get("world_name", world_id))
    return {
        "available": True, "entries": entries, "player_rank": player_rank,
        "on_board": player_rank <= 20, "world": world_id,
        "world_name": world_name, "title": f"{world_name}天榜前二十",
    }


def _race_system_view(
    player: dict[str, Any], characters: list[dict[str, Any]],
    world: dict[str, Any], governance: dict[str, Any], config: dict[str, Any],
) -> dict[str, Any]:
    world_id = str(world.get("world_id", ""))
    race_definitions = dict(config.get("race_details") or {})
    lineage_race = str(player.get("lineage_race") or player.get("race", "human"))
    player_race = str(player.get("allegiance_race") or lineage_race)
    if world_id not in {"spirit", "true_demon"}:
        return {
            "available": False, "implemented": True,
            "player_race": player_race,
            "player_race_name": str(dict(race_definitions.get(player_race) or {}).get("name", player_race)),
            "races": {}, "alliances": [],
        }
    present_races = {
        str(row.get("race")) for row in characters
        if row.get("race")
    } | {player_race}
    present_races |= {
        race_id for race_id, definition in race_definitions.items()
        if world_id in list(dict(definition).get("worlds", []))
    }
    status_names = {
        "war": "战争", "alliance": "同盟", "truce": "停战",
        "vassal": "依附", "neutral": "中立",
    }
    relation_rows = [
        dict(row) for row in governance.get("relations", [])
        if row.get("kind") == "race"
    ]
    races: dict[str, Any] = {}
    status_verbs = {
        "war": "宣战", "alliance": "结盟", "truce": "停战",
        "vassal": "依附", "neutral": "恢复中立",
    }
    for race_id in sorted(present_races):
        definition = dict(race_definitions.get(race_id) or {})
        relations = []
        for relation in relation_rows:
            sides = {str(relation.get("first_id")), str(relation.get("second_id"))}
            if race_id not in sides:
                continue
            other_id = next((side for side in sides if side != race_id), race_id)
            other = dict(race_definitions.get(other_id) or {})
            status = str(relation.get("status", "neutral"))
            relations.append({
                "race": other_id, "race_name": other.get("name", other_id),
                "status": status, "status_name": status_names.get(status, status),
                "affinity": _number(relation.get("affinity")),
            })
        recent_events = []
        for relation in relation_rows:
            if race_id not in {
                str(relation.get("first_id")), str(relation.get("second_id")),
            }:
                continue
            vote = dict(relation.get("last_vote") or {})
            if not vote:
                continue
            proposal = str(vote.get("proposal", relation.get("status", "neutral")))
            recent_events.append({
                "age": vote.get("year", relation.get("since_year", 0)),
                "summary": (
                    f"{status_verbs.get(proposal, proposal)}决议"
                    f"{'通过' if vote.get('passed') else '未通过'}"
                ),
            })
        faction_details = dict(config.get("faction_details") or {})
        faction_presets = [
            dict(row)
            for row in dict(config.get("race_faction_presets") or {}).get(
                race_id, []
            )
            if str(dict(row).get("world", "")) == world_id
        ]
        active_factions = [
            {
                "id": faction_id, "name": faction.get("name", faction_id),
                "active": any(
                    row.get("faction_id") == faction_id
                    or row.get("faction_external_id") == faction_id
                    for row in characters
                ),
                "elders": [
                    str(row.get("name", "无名修士"))
                    for row in characters
                    if row.get("faction_external_id") == faction_id
                    and int(row.get("realm_index", 0)) >= 4
                ][:6],
            }
            for faction_id, faction in faction_details.items()
            if faction.get("world") == world_id
            and faction.get("allegiance_race") == race_id
        ]
        active_ids = {str(row["id"]) for row in active_factions}
        races[race_id] = {
            "id": race_id, "name": definition.get("name", race_id),
            "description": definition.get("description", ""),
            "relations": relations, "recent_events": recent_events[-10:],
            "supported_factions": [
                *active_factions,
                *[
                    {
                        "id": str(row.get("id", "")),
                        "name": str(row.get("name", row.get("id", ""))),
                        "active": False,
                        "elders": list(map(str, row.get("elders", []))),
                    }
                    for row in faction_presets
                    if str(row.get("id", "")) not in active_ids
                ],
            ],
        }
    alliances = []
    for index, relation in enumerate(relation_rows):
        status = str(relation.get("status", "neutral"))
        if status not in {"alliance", "vassal"}:
            continue
        members = [str(relation.get("first_id")), str(relation.get("second_id"))]
        alliances.append({
            "id": f"relation:{index}",
            "name": relation.get("name") or status_names[status],
            "status": status, "members": members,
        })
    realm_index = int(dict(player.get("cultivation") or {}).get("realm_index", 0))
    player_rank = (realm_index, int(dict(player.get("cultivation") or {}).get("layer", 1)))
    vassal_transfers = []
    for relation in relation_rows:
        if (
            relation.get("status") != "vassal"
            or str(relation.get("overlord")) != player_race
        ):
            continue
        subject = str(relation.get("subject", ""))
        candidates = [
            row for row in characters
            if str(row.get("race")) == subject
            and bool(row.get("alive", True))
            and (
                int(row.get("realm_index", 0)), int(row.get("layer", 1))
            ) <= player_rank
        ]
        if candidates:
            vassal_transfers.append({
                "target_id": subject,
                "target_name": races.get(subject, {}).get("name", subject),
                "candidates": candidates,
            })
    return {
        "available": True, "implemented": True, "world": world_id,
        "world_name": world.get("world_name", world_id),
        "player_race": player_race,
        "player_race_name": races[player_race]["name"],
        "lineage_race": lineage_race,
        "lineage_race_name": str(dict(
            race_definitions.get(lineage_race) or {}
        ).get("name", lineage_race)),
        "has_diplomatic_voice": player_race == "human" and realm_index >= 8,
        "races": races, "alliances": alliances,
        "vassal_transfers": vassal_transfers,
    }
def game_view(data: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    if data.get("format") != "cultivation-life-v2":
        return data
    raw_player = dict(data.get("player", {}))
    cultivation = dict(raw_player.get("cultivation", {}))
    body = dict(raw_player.get("body", {}))
    sense = dict(raw_player.get("divine_sense", {}))
    combat = dict(dict(data.get("combat", {})).get("snapshot", {}))
    world = dict(data.get("world", {}))
    relationships = [_relation(row) for row in data.get("relationships", [])]
    companion = next((row for row in relationships if row.get("kind") == "dao_companion"), None)
    friends = [row for row in relationships if row.get("kind") == "friend"]
    master = next((
        row for row in relationships
        if row.get("kind") == "master_disciple" and row.get("direction") == "target"
    ), None)
    disciples = [
        row for row in relationships
        if row.get("kind") == "master_disciple" and row.get("direction") == "source"
    ]
    harvested = [
        {
            "id": asset.get("id"), "name": asset.get("name"),
            "description": "灵田采收所得，可炼丹、出售或在满足年份后直接使用。",
            "tags": ["spirit_plant", "herb"], "quantity": 1, "available": 1,
            "plant_id": dict(asset.get("metadata", {})).get("plant_id"),
            "plant_years": float(dict(asset.get("metadata", {})).get("years", 0)),
            "plant_quality": float(dict(asset.get("metadata", {})).get("quality", 0)),
        }
        for asset in dict(data.get("assets", {})).get("instances", [])
        if asset.get("kind") == "harvested_spirit_plant" and not asset.get("reservation_id")
    ]
    crafted = [
        {
            "id": artifact.get("id"), "name": artifact.get("name"),
            "description": artifact.get("description", "组合式炼器法宝"),
            "tags": ["artifact", "equipment", "crafted_artifact"],
            "quantity": 1, "available": 1,
            "crafted_artifact_id": artifact.get("id"),
            "is_natal_artifact": bool(artifact.get("is_natal")),
            "combat_bonus": float(
                dict(artifact.get("actual_stats", {})).get("combat_power", 0)
            ),
        }
        for artifact in dict(data.get("crafting", {})).get("artifacts", [])
    ]
    natal = dict(data.get("natal_artifact", {}))
    natal_inventory = []
    if natal.get("bound") and not natal.get("crafted_artifact_id"):
        natal_inventory.append({
            "id": natal.get("item_id"), "name": natal.get("name"),
            "description": (
                f"本命法宝 · {natal.get('level', 1)}级。"
                "已收入丹田，不可交易。"
            ),
            "tags": ["artifact", "equipment", "natal_artifact"],
            "quantity": 1, "available": 0, "is_natal_artifact": True,
            "combat_bonus": float(
                dict(natal.get("bonuses", {})).get("combat_bonus", 0)
            ),
        })
    inventory = [
        *data.get("inventory", []), *harvested, *crafted, *natal_inventory,
    ]
    known_techniques = list(cultivation.get("known_techniques", []))
    technique_by_id = {str(row.get("id")): row for row in known_techniques}

    def technique(technique_id: Any) -> dict[str, Any] | None:
        if not technique_id:
            return None
        return dict(technique_by_id.get(str(technique_id), {"id": technique_id, "name": technique_id}))

    def race_name(race_id: str) -> str:
        value = dict(config.get("races", {})).get(race_id, race_id)
        return str(value.get("name", race_id) if isinstance(value, dict) else value)

    story_attributes = dict(dict(data.get("story", {})).get("attributes", {}))
    spirit_crossing = dict(dict(data.get("story", {})).get("spirit_crossing", {}))
    karma_factor = float(cultivation.get("karma_factor", 1))
    hp_max = float(combat.get("max_hp", 1))
    mp_max = float(combat.get("max_mp", 1))
    transformations = dict(raw_player.get("transformations", {}))
    clock_year = dict(data.get("clock", {})).get("year", raw_player.get("age", 0))
    player = {
        **raw_player,
        **cultivation,
        "world": world.get("world_id"), "world_name": world.get("world_name"),
        "location": world.get("location_id"), "location_name": world.get("location_name"),
        "world_age": clock_year,
        "opportunity": float(cultivation.get("opportunity", 0)),
        "opportunity_required": float(cultivation.get("opportunity_required", 1)),
        "spirit_root_display": cultivation.get("spirit_root_name"),
        "spirit_root_efficiency": float(cultivation.get("spirit_root_efficiency", 0)),
        "cultivation_efficiency": float(cultivation.get("cultivation_efficiency", 0)),
        "time_unit_years": float(cultivation.get("time_unit_years", 1)),
        "resource_name": cultivation.get("resource_name", "MP"),
        "resource_kind": cultivation.get("resource_kind", "mana"),
        "immortal_power": dict(cultivation.get("immortal_power", {})),
        "hp": hp_max * float(combat.get("hp_ratio", 1)), "max_hp": hp_max,
        "mp": mp_max * float(combat.get("mp_ratio", 1)), "max_mp": mp_max,
        "combat_power": float(combat.get("power", 0)),
        "battle_power": float(combat.get("power", 0)),
        "expected_combat_power": float(cultivation.get(
            "expected_combat_power", combat.get("power", 0)
        )),
        "combat_power_assessment": "按当前境界与层数的标准战力核验。",
        "spirit_realm_attempted": bool(spirit_crossing.get("attempted")),
        "awaiting_spirit_realm_crossing": bool(spirit_crossing.get("active")),
        "karma": float(story_attributes.get("karma", 0)),
        "effective_karma": float(story_attributes.get(
            "effective_karma", max(0, float(story_attributes.get("karma", 0))) * karma_factor
        )),
        "karma_factor": karma_factor,
        "heart_demon": float(cultivation.get("heart_demon", 0)),
        "fame": float(story_attributes.get("fame", 0)),
        "spirit_stones": float(dict(data.get("market", {})).get("spirit_stones", 0)),
        "technique": cultivation.get("main_technique"),
        "technique_slots": {
            "main": cultivation.get("main_technique"),
            "support": cultivation.get("support_technique"),
            "body": technique(body.get("technique_id")),
            "divine_sense": technique(sense.get("technique_id")),
            "transformation": technique(transformations.get("technique_id")),
            "combat": list(cultivation.get("combat_techniques", [])),
        },
        "known_techniques": known_techniques,
        "inventory": inventory,
        "qi_mastery": cultivation.get("qi_mastery") or [
            {
                "id": source, "source": source,
                "name": {"spirit": "灵气", "demon": "魔气", "monster": "妖气", "yin": "阴气"}.get(source, source),
                "level": int((float(experience) / float(config.get("qi_experience_base", 25))) ** 0.5),
                "experience": float(experience), "level_experience": float(experience),
                "next_level_experience": float(config.get("qi_experience_base", 25)),
            }
            for source, experience in dict(cultivation.get("qi_experience", {})).items()
        ],
        "qi_gain_efficiencies": dict(cultivation.get("qi_gain_efficiencies", {})),
        "qi_environment": cultivation.get("qi_environment") or {"display": [], "main_multiplier": None},
        "body_training": int(body.get("layer", 0)),
        "divine_sense": {
            "level": int(sense.get("rank", 0)),
            "level_experience": float(sense.get("experience", 0)),
            "next_level_experience": float(sense.get("breakthrough_cost", 0)),
            "breakthrough_ready": bool(
                sense.get("technique_id")
                and float(sense.get("experience", 0))
                >= float(sense.get("breakthrough_cost", 0))
            ),
            "capacity": int(dict(data.get("demonic_system", {})).get("capacity", 0)),
            "used": int(dict(data.get("demonic_system", {})).get("used", 0)),
            "technique": technique(sense.get("technique_id")),
        },
        "lineage_race_name": race_name(str(
            raw_player.get("lineage_race") or raw_player.get("race", "human")
        )),
        "allegiance_race_name": race_name(str(
            raw_player.get("allegiance_race")
            or raw_player.get("lineage_race")
            or raw_player.get("race", "human")
        )),
        "master": master, "disciples": disciples,
        "disciple_requests": [
            {**_relation(row), "id": row.get("request_id")}
            for row in data.get("disciple_requests", [])
        ],
    }
    destination_names = {
        str(row.get("id")): row.get("name") for row in world.get("destinations", [])
    }
    formation_public = dict(data.get("formation_system", {}))
    ghost_public = dict(data.get("ghost_system", {}))
    ghost_parade = ghost_public.get("parade")
    map_view = {
        "world": world.get("world_id"), "world_name": world.get("world_name"),
        "current_location": world.get("location_id"),
        "current_name": world.get("location_name"),
        "current_location_name": world.get("location_name"),
        "locations": [
            {
                **location,
                "description": location.get("description")
                or location.get("warning") or (
                    "你当前驻足之地。" if location.get("current") else "沿界内道路可抵达此地。"
                ),
                "themes": list(location.get("themes", [])),
                "qi_gain_efficiencies": dict(location.get("qi_gain_efficiencies", {})),
                "route_names": [destination_names.get(str(item), item) for item in location.get("route", [])],
                "travel_status": "current" if location.get("current") else "lethal" if location.get("accessible") is False else "safe",
                "ground_formations": [
                    row for row in formation_public.get("ground_arrays", [])
                    if row.get("world") == world.get("world_id")
                    and row.get("location_id") == location.get("id")
                ],
                "ghost_parade": (
                    {
                        **dict(ghost_parade),
                        "start_age": dict(ghost_parade).get("start_year"),
                    }
                    if isinstance(ghost_parade, dict)
                    and ghost_parade.get("announced")
                    and ghost_parade.get("world_id") == world.get("world_id")
                    and ghost_parade.get("location_id") == location.get("id")
                    else None
                ),
            }
            for location in world.get("destinations", [])
        ],
    }
    intrigue_raw = dict(data.get("intrigue_system", {}))
    intrigue = {
        **intrigue_raw,
        "player_guest_roles": list(intrigue_raw.get("player_guest_roles", [])),
        "sections": [
            {
                "kind_name": section.get("kind_name") or {
                    "race": "族群", "sect": "宗门", "family": "家族"
                }.get(section.get("kind"), "势力"),
                "controller_name": section.get("controller_name", "暂无"),
                "policy": section.get("policy", "守成"),
                "unrest": float(section.get("unrest", 0)),
                "fear": float(section.get("fear", 0)),
                "control_authority": bool(section.get("control_authority")),
                "positionless_race": section.get("positionless_race", section.get("kind") == "race"),
                "positions": list(section.get("positions", [])),
                "members": list(section.get("members", [])),
                "guests": list(section.get("guests", [])),
                "guest_candidates": list(section.get("guest_candidates", [])),
                "resolutions": list(section.get("resolutions", [])),
                **section,
            }
            for section in intrigue_raw.get("sections", [])
        ],
    }
    faction = data.get("faction") or {
        "member": False,
        "available": list(data.get("available_factions", [])),
        "can_found": True,
        "system_available": True,
        "world_name": world.get("world_name"),
    }
    bottleneck = cultivation.get("bottleneck")
    capability = dict(dict(data.get("capabilities", {})).get("cultivation.breakthrough", {}))
    breakthrough = dict(data.get("breakthrough") or {
        "ready": bottleneck in {"minor", "major"}, "target_realm": None,
        "action_label": "突破瓶颈", "chance": None,
        "active_aids": list(cultivation.get("active_breakthrough_aids", [])), "met": True,
    })
    breakthrough["enabled"] = bool(breakthrough.get("enabled", True) and capability.get("enabled"))
    breakthrough.setdefault("reason", capability.get("reason", ""))
    monster = dict(data.get("monster_system", {}))
    if monster.get("visible") and (not monster.get("species") or not monster.get("current")):
        monster.update({
            "available": False,
            "reason": "当前角色尚未形成可展示的本源血脉。",
            "general_traits": list(monster.get("general_traits", [])),
        })
    characters = list(data.get("characters", []))
    governance = dict(data.get("governance", {}))
    war_system = dict(data.get("war_system", {}))
    active_bounty_targets = {
        str(row.get("target_id"))
        for row in war_system.get("bounties", [])
        if row.get("status") == "active"
    }
    personal_high = [
        {**row, "relationship": "颇有好感"}
        for row in characters if _number(row.get("affinity")) >= 30
    ]
    personal_low = [
        {**row, "relationship": "敌视"}
        for row in characters if _number(row.get("affinity")) <= -25
    ]
    raw_trial = dict(data.get("trial") or {})
    active_trial = raw_trial.get("active")
    active_trial_data = dict(active_trial) if isinstance(active_trial, dict) else {}
    trial = {
        **raw_trial,
        "active": bool(active_trial),
        "kind": active_trial_data.get("kind"),
        "step": (
            int(active_trial_data.get("step_index", 0)) + 1
            if active_trial else None
        ),
        "total_steps": (
            len(active_trial_data.get("event_ids", []))
            if active_trial else None
        ),
        "allows_recovery_items": bool(active_trial),
    }
    market = dict(data.get("market", {}))
    market["offers"] = [
        row for row in market.get("offers", [])
        if row.get("market_group", "general") == "general"
    ]
    market.setdefault("material_offers", [
        *market.get("crafting_material_offers", []),
        *market.get("formation_material_offers", []),
    ])
    history = [*data.get("world_news", []), *dict(data.get("story", {})).get("history", [])]
    family_raw = dict(data.get("family", {}))
    family_role_names = {
        "lineal_heir": "嫡系后裔",
        "external_member": "外姓供奉",
        "member": "族人",
    }
    family = {
        **family_raw,
        "description": family_raw.get("description") or (
            "由血脉后裔与招揽修士共同维系的修仙家族。"
            if family_raw.get("exists") else ""
        ),
        "extinct": bool(
            family_raw.get("exists")
            and not family_raw.get("active", True)
        ),
        "roster": [
            {
                **member,
                "member_type": family_role_names.get(
                    str(member.get("role", "member")),
                    str(member.get("role_name") or member.get("role") or "族人"),
                ),
            }
            for member in family_raw.get("roster", [])
        ],
    }
    characters_by_id = {
        str(row.get("id")): row for row in characters
    }
    concubine_raw = dict(data.get("concubine_system", {}))
    concubine_status = concubine_raw.get("status")
    if isinstance(concubine_status, dict):
        owner = dict(concubine_status.get("owner", {}))
        concubine_status = {
            **concubine_status,
            "owner_name": concubine_status.get("owner_name")
            or owner.get("name", "名分之主"),
            "owner_realm_name": concubine_status.get("owner_realm_name")
            or owner.get("realm_name", "境界未明"),
        }
    concubine_system = {
        **concubine_raw,
        "status": concubine_status,
        "concubines": [
            {
                **dict(characters_by_id.get(str(row.get("id")), {})),
                **row,
                **dict(row.get("metadata", {})),
            }
            for row in concubine_raw.get("concubines", [])
        ],
    }
    court_raw = dict(data.get("heavenly_court", {}))
    court = {
        **court_raw,
        "offices": [
            {
                **office,
                "holder": (
                    {
                        **dict(office["holder"]),
                        "entity_id": office["holder"].get("holder_id"),
                        "holder_id": (
                            "player"
                            if str(office["holder"].get("holder_id"))
                            == str(raw_player.get("id"))
                            else office["holder"].get("holder_id")
                        ),
                    }
                    if isinstance(office.get("holder"), dict) else None
                ),
            }
            for office in court_raw.get("offices", [])
        ],
        "election": (
            {
                **dict(court_raw["election"]),
                "candidates": [
                    {
                        **candidate,
                        "entity_id": candidate.get("id"),
                        "id": (
                            "player"
                            if str(candidate.get("id"))
                            == str(raw_player.get("id"))
                            else candidate.get("id")
                        ),
                    }
                    for candidate in dict(court_raw["election"]).get(
                        "candidates", []
                    )
                ],
            }
            if isinstance(court_raw.get("election"), dict) else None
        ),
    }
    pending_event = data.get("pending_event")
    demonic_public = dict(data.get("demonic_system", {}))
    post_battle = dict(
        demonic_public.get("pending_post_battle_possession") or {}
    )
    if pending_event is None and not bool(player.get("alive")) and post_battle:
        candidate_ids = set(map(str, post_battle.get("candidate_ids", [])))
        prisoners = {
            str(row.get("id")): row
            for row in demonic_public.get("prisoners", [])
            if str(row.get("id")) in candidate_ids
        }
        choices = []
        for candidate_id in map(str, post_battle.get("candidate_ids", [])):
            candidate = dict(prisoners.get(candidate_id) or {})
            if not candidate:
                continue
            choices.append({
                "id": candidate_id,
                "text": (
                    f"夺舍 {candidate.get('name', '无名俘虏')} · "
                    f"{candidate.get('realm_name', '境界未明')} · "
                    f"{int(candidate.get('age', 0))}岁"
                ),
                "enabled": True,
            })
        if choices:
            pending_event = {
                "id": "SYS_POST_BATTLE_POSSESSION",
                "version": 1,
                "title": "战陨夺舍",
                "body": (
                    "肉身已在非剧情战中陨灭，但本魂尚有一线余地。"
                    "你可以占据一名不高于自身境界的俘虏。"
                ),
                "choices": choices,
                "runtime": {
                    "source_event": post_battle.get("report_id"),
                    "prisoner_ids": [row["id"] for row in choices],
                },
            }
    result = {
        **data,
        "pending_event": pending_event,
        "player": player,
        "seed": int(data.get("seed", 0)),
        "actions": dict(config.get("actions", {})),
        "rules": {"karma_factors": dict(config.get("karma_factors", {}))},
        "new_achievements": list(data.get("new_achievements", [])),
        "transformation_system": {"available": True, **transformations},
        "monster_bloodline": monster,
        "dao_companion": companion, "dao_friends": friends,
        "personal_relations": {"high": personal_high, "low": personal_low},
        "party": [
            {
                **member,
                "can_cross_spirit": bool(member.get("crossing_eligible")),
                "selected_for_crossing": bool(member.get("crossing_selected")),
                "in_party": True,
            }
            for member in dict(data.get("party", {})).get("members", [])
        ],
        "wanted": list(war_system.get("wanted_by", [])),
        "imprisonment": dict(data.get("demonic_system", {})).get("imprisonment"),
        "body_cultivation": {
            "layer": int(body.get("layer", 0)),
            "max_layer": int(body.get("max_layer", 100)),
            "progress": float(body.get("progress", 0)), "required": float(body.get("required", 0)),
            "ready": bool(body.get("ready")), "chance": body.get("chance"),
            "target_layer": body.get("target_layer"),
            "technique": technique(body.get("technique_id")),
            "training_speed_multiplier": float(
                body.get("training_speed_multiplier", 1)
            ),
            "tribulation_damage_reduction": float(
                body.get("tribulation_damage_reduction", 0)
            ),
            "cultivation_breakthrough_bonus": float(
                body.get("cultivation_breakthrough_bonus", 0)
            ),
        },
        "breakthrough": breakthrough,
        "market": market,
        "map": map_view,
        "world_travel": _world_travel_view(raw_player, world, data, config),
        "spirit_field": dict(data.get("production", {})),
        "art_skills": list(dict(data.get("production", {})).get("art_skills", [])),
        "auction_system": dict(data.get("auction", {})),
        "crafting_system": dict(data.get("crafting", {})),
        "formation_system": formation_public,
        "natal_artifact": {
            **natal,
            "slots": natal.get("slot_details", natal.get("slots", [])),
        },
        "last_combat_report": _combat_report_view(
            dict(data.get("combat", {})).get("last_report"),
            str(raw_player.get("id", "")),
        ),
        "history": [
            {**record, "age": record.get("age", record.get("year", clock_year))}
            for record in history
        ],
        "world_npcs": characters,
        "spirit_ranking": _ranking_view(player, characters, world, config),
        "race_system": _race_system_view(
            raw_player, characters, world, governance, config
        ),
        "family": family,
        "concubine_system": concubine_system,
        "heavenly_court": court,
        "world_route": {
            "route_id": cultivation.get("path"), "name": cultivation.get("path_name"),
            "path": cultivation.get("path"), "path_name": cultivation.get("path_name"),
            "current_world": world.get("world_id"), "current_world_name": world.get("world_name"),
            "lineage_race_name": race_name(str(
                raw_player.get("lineage_race") or raw_player.get("race", "human")
            )),
            "allegiance_race_name": race_name(str(
                raw_player.get("allegiance_race")
                or raw_player.get("lineage_race")
                or raw_player.get("race", "human")
            )),
            "stages": [
                {
                    "id": world_id, "label": name, "current": world_id == world.get("world_id"),
                    "enabled": True, "kind": "world", "description": "V2 领域世界",
                }
                for world_id, name in dict(config.get("worlds", {})).items()
            ],
        },
        "faction": faction,
        "governance": {
            **governance,
            "can_issue_bounty": bool(war_system.get("can_issue_bounty")),
            "bounties": list(war_system.get("bounties", [])),
            "bounty_candidates": [
                row for row in characters
                if str(row.get("id")) not in active_bounty_targets
            ],
            "bounty_authorities": list(war_system.get("bounty_authorities", [])),
        },
        "intrigue_system": intrigue,
        "ghost_system": _ghost_view(data.get("ghost_system"), raw_player),
        "trial": trial,
        "tribulation": dict(data.get("tribulation", {})),
    }
    return result
