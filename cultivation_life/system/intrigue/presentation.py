from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import copy
    from typing import Any
    from ...content_registry import PATH_NAMES, RACE_DEFINITIONS, REALMS, WORLD_SYSTEMS
    from ...models import GameState, SectNpc
    from ..npc_system import attitude_label
    from .. import intrigue_system as _source
    PLAYER_ID = _source.PLAYER_ID
    PERSONALITY_LABELS = _source.PERSONALITY_LABELS
    STYLE_LABELS = _source.STYLE_LABELS
    RESOLUTION_LABELS = _source.RESOLUTION_LABELS


class IntriguePresentationMethods:
    def _intrigue_public_member(self, game: GameState, npc: SectNpc, record: dict[str, Any]) -> dict[str, Any]:
        personality = self._ensure_intrigue_personality(game, npc)
        position = next((pid for pid, holder in record.get("positions", {}).items() if holder == npc.id), None)
        spec = self._intrigue_position_specs(record["kind"]).get(position or "", {})
        return {
            "id": npc.id, "name": npc.name, "realm_index": npc.realm_index,
            "realm_name": f"{REALMS[npc.realm_index].name}{npc.layer}层" if npc.realm_index else REALMS[0].name,
            "affinity": round(float(npc.affinity or 0), 1), "attitude": attitude_label(float(npc.affinity or 0), 0),
            "primary": PERSONALITY_LABELS[personality["primary"]],
            "secondary": PERSONALITY_LABELS.get(personality.get("secondary"), ""),
            "governance_style": STYLE_LABELS.get(personality.get("governance_style"), ""),
            "position_id": position, "position": spec.get("name", npc.title or "普通成员"),
            "decision_authority": self._intrigue_has_decision_authority(game, record["kind"], record["id"], npc.id),
            "imprisoned": self._intrigue_is_imprisoned(game, npc.id),
            "contribution": int(record.get("member_contribution", {}).get(npc.id, 0)),
        }

    def _public_intrigue_recruitment(
        self, game: GameState, faction_id: str, record: dict[str, Any],
    ) -> dict[str, Any]:
        config = self._intrigue_recruitment_config()
        pending = record.get("pending_recruitment")
        public_pending = None
        if isinstance(pending, dict):
            rows = []
            for candidate in pending.get("candidates", []):
                npc = SectNpc.from_dict(candidate["npc"])
                rows.append({
                    "id": npc.id, "name": npc.name,
                    "realm_index": npc.realm_index,
                    "realm_name": REALMS[npc.realm_index].name if npc.realm_index == 0 else f"{REALMS[npc.realm_index].name}{npc.layer}层",
                    "spirit_root": npc.spirit_root, "spirit_root_name": self._npc_root_name(npc.spirit_root),
                    "path": npc.path, "path_name": PATH_NAMES.get(npc.path, npc.path),
                    "gender": npc.gender, "gender_name": "男" if npc.gender == "male" else "女",
                    "age": npc.age, "lifespan": npc.lifespan,
                    "combat_power": float(candidate.get("combat_power", self._npc_power(npc))),
                    "combat_ratio": float(candidate.get("combat_ratio", 0)),
                })
            public_pending = {
                "id": pending.get("id"), "message": pending.get("message"),
                "filter_summary": pending.get("filter_summary"), "candidates": rows,
            }
        return {
            "available": self._intrigue_has_decision_authority(game, "sect", faction_id),
            "max_candidates": min(5, int(config.get("max_candidates", 5))),
            "pending": public_pending,
            "spirit_root_options": [
                {"id": "any", "name": "不筛选"}, {"id": "heavenly", "name": "天灵根"},
            ],
            "realm_options": [
                {"id": "any", "name": "不筛选"},
                *[{"id": str(index), "name": REALMS[index].name} for index in self._intrigue_recruitment_realm_options(game.player.world)],
            ],
            "path_options": [{"id": "any", "name": "不筛选"}, *[
                {"id": path, "name": name} for path, name in PATH_NAMES.items()
            ]],
            "combat_options": [
                {"id": key, "name": str(value.get("name", key))}
                for key, value in config.get("combat_filters", {}).items()
            ],
            "gender_options": [
                {"id": "any", "name": "不筛选"}, {"id": "male", "name": "男"}, {"id": "female", "name": "女"},
            ],
        }

    def _public_guest_invitation(self, game: GameState) -> dict[str, Any] | None:
        invitation = self._intrigue_state(game).get("pending_guest_invitation")
        if not isinstance(invitation, dict):
            return None
        entity = self._intrigue_entity(
            game, str(invitation.get("kind", "")), str(invitation.get("faction_id", "")),
        )
        if game.debug_world_news or (entity and not entity.extinct and entity.world == game.player.world):
            return copy.deepcopy(invitation)
        return None

    def _public_intrigue_system(self, game: GameState) -> dict[str, Any]:
        if not self._intrigue_enabled():
            return {"enabled": False, "name": "明争暗斗：合纵连横"}
        sections: list[dict[str, Any]] = []
        for kind in ("sect", "family", "race"):
            if kind == "race" and not self._world_supports(game.player.world, "races"):
                continue
            faction_id = self._intrigue_player_faction_id(game, kind)
            if game.debug_world_news and kind == "family" and game.family and not game.family.extinct:
                faction_id = game.family.id
            if not faction_id:
                continue
            entity = self._intrigue_entity(game, kind, faction_id)
            if entity and (entity.extinct or (entity.world != game.player.world and not game.debug_world_news)):
                continue
            record = self._ensure_intrigue_faction(game, kind, faction_id)
            members = [self._intrigue_public_member(game, npc, record) for npc in self._intrigue_members(game, kind, faction_id) if npc.alive]
            if kind == "race" and self._intrigue_has_decision_authority(game, kind, faction_id):
                player_realm, player_layer = self._actual_player_realm(game.player)
                player_position = next(
                    (position_id for position_id, holder_id in record.get("positions", {}).items() if holder_id == PLAYER_ID),
                    None,
                )
                player_position_name = (
                    self._intrigue_position_specs(kind).get(player_position, {}).get("name")
                    if player_position else None
                )
                members.append({
                    "id": PLAYER_ID, "name": game.player.name, "realm_index": player_realm,
                    "realm_name": (
                        f"{REALMS[player_realm].name}{player_layer}层"
                        if player_realm else REALMS[0].name
                    ),
                    "affinity": None, "attitude": "本人", "primary": "玩家本人",
                    "secondary": "", "governance_style": "", "position_id": player_position,
                    "position": player_position_name or ("种族议事成员" if kind == "race" else "普通成员"),
                    "decision_authority": True,
                    "imprisoned": False, "contribution": 0, "is_player": True,
                })
            members.sort(key=lambda row: (-row["realm_index"], -int(row.get("layer", 0)), row["name"]))
            positions = []
            for position_id, spec in self._intrigue_position_specs(kind).items():
                holder_id = record.get("positions", {}).get(position_id)
                if holder_id == PLAYER_ID:
                    holder_name = game.player.name
                else:
                    holder = self._intrigue_find_npc(game, str(holder_id or ""))
                    holder_name = holder.name if holder else "空缺"
                positions.append({"id": position_id, **copy.deepcopy(spec), "holder_id": holder_id, "holder_name": holder_name})
            guests = []
            for guest in record.get("guests", []):
                npc = self._intrigue_find_npc(game, str(guest.get("npc_id", "")))
                name = game.player.name if guest.get("npc_id") == PLAYER_ID else npc.name if npc else str(guest.get("name", "失联客卿"))
                guests.append({**copy.deepcopy(guest), "name": name})
            candidates = []
            if kind != "race" and self._intrigue_has_control(game, kind, faction_id):
                sources: dict[str, Any] = {npc.id: npc for npc in self._all_world_npcs(game)}
                for relation in [
                    game.player.master, game.player.dao_companion,
                    *game.player.dao_friends, *game.player.disciples,
                ]:
                    if relation:
                        sources.setdefault(str(relation.get("id", "")), relation)
                for npc_id, source in sources.items():
                    if not self._intrigue_can_invite_guest(game, npc_id, kind):
                        continue
                    relation = self._intrigue_player_relation(game, npc_id)
                    if isinstance(source, SectNpc):
                        name, realm_index = source.name, source.realm_index
                        affinity = float(source.affinity or 0)
                    else:
                        name = str(source.get("name", "无名修士"))
                        realm_index = int(source.get("realm_index", 0))
                        affinity = float(source.get("affinity", 0))
                    if relation:
                        affinity = max(affinity, float(relation.get("affinity", 0)))
                    candidates.append({
                        "id": npc_id, "name": name, "affinity": round(affinity, 1),
                        "realm_index": realm_index,
                        "relationship": "道友" if any(str(row.get("id", "")) == npc_id for row in game.player.dao_friends) else "故交",
                    })
                candidates.sort(key=lambda row: (-row["affinity"], -row["realm_index"]))
            sections.append({
                "kind": kind, "kind_name": {"sect": "宗门", "family": "家族", "race": "种族"}[kind],
                "id": faction_id, "name": self._intrigue_faction_name(game, kind, faction_id),
                "control_authority": self._intrigue_has_control(game, kind, faction_id),
                "decision_authority": self._intrigue_has_decision_authority(game, kind, faction_id),
                "decision_threshold": self._intrigue_decision_threshold(kind),
                "controller_name": game.player.name if record.get("controller_id") == PLAYER_ID else next((row["name"] for row in members if row["id"] == record.get("controller_id")), "无"),
                "policy": STYLE_LABELS.get(record.get("policy"), "平衡型"), "policy_id": record.get("policy", "balance"),
                "unrest": round(float(record.get("unrest", 0)), 1), "fear": round(float(record.get("fear", 0)), 1),
                "positions": positions, "members": members, "guests": guests,
                "player_power_rank": record.get("player_power_rank"),
                "player_office_id": record.get("player_auto_office"),
                "guest_candidates": candidates[:16], "prison": copy.deepcopy(record.get("prison", [])),
                "positionless_race": kind == "race",
                "resolution_targets": (
                    [{"id": row.id, "name": row.name} for row in game.sects.values()
                     if not row.extinct and row.id != faction_id and row.world == game.player.world]
                    if kind == "sect" else
                    [{"id": race_id, "name": definition.get("name", race_id)}
                     for race_id, definition in RACE_DEFINITIONS.items()
                     if race_id != faction_id and game.player.world in definition.get("worlds", [])]
                    if kind == "race" else []
                ),
                "war_targets": [
                    {"id": str(war.get("id", "")), "name": f"{war.get('attacker_id')} 对 {war.get('defender_id')}"}
                    for war in game.wars if war.get("status") in {"active", "peace_ready"}
                ],
                "disciple_recruitment": (
                    self._public_intrigue_recruitment(game, faction_id, record)
                    if kind == "sect" else None
                ),
            })
        recent = []
        for row in reversed(self._intrigue_state(game).get("resolutions", [])[-48:]):
            entity = self._intrigue_entity(game, str(row.get("kind", "")), str(row.get("faction_id", "")))
            if game.debug_world_news or not entity or entity.world == game.player.world:
                recent.append(copy.deepcopy(row))
            if len(recent) >= 16:
                break
        player_guest_roles = []
        for record in self._intrigue_state(game).get("factions", {}).values():
            if any(row.get("npc_id") == PLAYER_ID for row in record.get("guests", [])):
                entity = self._intrigue_entity(game, str(record.get("kind", "")), str(record.get("id", "")))
                if not game.debug_world_news and entity and entity.world != game.player.world:
                    continue
                player_guest_roles.append({
                    "kind": record.get("kind"), "faction_id": record.get("id"),
                    "faction_name": self._intrigue_faction_name(game, str(record.get("kind")), str(record.get("id"))),
                    "title": "卿族" if record.get("kind") == "race" else "供奉" if record.get("kind") == "family" else "客卿长老",
                })
        return {
            "enabled": True, "name": "明争暗斗：合纵连横", "sections": sections,
            "resolutions": recent,
            "pending_guest_invitation": self._public_guest_invitation(game),
            "player_guest_roles": player_guest_roles,
            "resolution_types": RESOLUTION_LABELS, "styles": STYLE_LABELS,
            "available_worlds": [
                {"id": world_id, "name": WORLD_SYSTEMS.get("world_names", {}).get(world_id, world_id)}
                for world_id, profile in WORLD_SYSTEMS.get("world_profiles", {}).items() if profile.get("enabled", True)
            ],
        }
