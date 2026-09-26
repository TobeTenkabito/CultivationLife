from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import random
    from ...content_registry import RACE_DEFINITIONS
    from ...models import GameState
    from .. import intrigue_system as _source
    PLAYER_ID = _source.PLAYER_ID
    STYLE_LABELS = _source.STYLE_LABELS
    RESOLUTION_LABELS = _source.RESOLUTION_LABELS


class IntrigueRuntimeMethods:
    def _intrigue_record_player_prison(self, game: GameState, key: str, years: int) -> None:
        if not self._intrigue_enabled() or ":" not in key:
            return
        kind, faction_id = key.split(":", 1)
        if kind not in {"sect", "family"}:
            return
        if kind == "sect" and faction_id not in game.sects:
            return
        if kind == "family" and (not game.family or game.family.id != faction_id):
            return
        record = self._ensure_intrigue_faction(game, kind, faction_id)
        record["prison"] = [row for row in record["prison"] if row.get("prisoner_id") != PLAYER_ID]
        record["prison"].append({
            "prisoner_id": PLAYER_ID, "name": game.player.name, "faction_id": faction_id,
            "kind": kind, "sentence_remaining": years, "sentence_years": years,
            "reason": "接受通缉处罚", "imprisoned_by": faction_id,
        })
        game.player.imprisonment.update({"faction_id": faction_id, "faction_kind": kind, "facility": "faction_prison"})

    def _intrigue_sync_player_prison(self, game: GameState) -> None:
        if not self._intrigue_enabled():
            return
        for record in self._intrigue_state(game).get("factions", {}).values():
            for row in record.get("prison", []):
                if row.get("prisoner_id") == PLAYER_ID and game.player.imprisonment:
                    row["sentence_remaining"] = int(game.player.imprisonment.get("remaining_years", 0))
            if not game.player.imprisonment:
                record["prison"] = [row for row in record.get("prison", []) if row.get("prisoner_id") != PLAYER_ID]

    def _advance_intrigue_unit(self, game: GameState, rng: random.Random) -> list[str]:
        if not self._intrigue_enabled():
            return []
        state = self._intrigue_state(game)
        # Re-evaluate the player's cultivation-order office every action unit,
        # so appointments and later promotions survive even if the panel was
        # never opened before advancing time.
        for kind in ("sect", "family"):
            faction_id = self._intrigue_player_faction_id(game, kind)
            if faction_id:
                self._ensure_intrigue_faction(game, kind, faction_id)
        # Sentences share the existing action-unit clock and do not scan NPC pairs.
        for record in state.get("factions", {}).values():
            remaining = []
            for prisoner in record.get("prison", []):
                if prisoner.get("prisoner_id") == PLAYER_ID:
                    remaining.append(prisoner)
                    continue
                prisoner["sentence_remaining"] = max(0, int(prisoner.get("sentence_remaining", 0)) - 1)
                if prisoner["sentence_remaining"] > 0:
                    remaining.append(prisoner)
                else:
                    state["npc_prisons"].pop(str(prisoner.get("prisoner_id", "")), None)
            record["prison"] = remaining
        self._intrigue_sync_player_prison(game)
        news: list[str] = []
        if self._world_supports(game.player.world, "races"):
            race_id = self._player_allegiance_race(game.player)
            race_record = self._ensure_intrigue_faction(game, "race", race_id)
            if not race_record.get("qingzu_initialized"):
                candidates = [
                    npc for npc in self._all_world_npcs(game)
                    if npc.alive and npc.world == game.player.world and npc.race != race_id
                    and npc.realm_index >= self._intrigue_decision_threshold("race")
                ]
                if candidates:
                    candidates.sort(key=lambda row: (-row.realm_index, -row.layer, row.id))
                    guest = candidates[0]
                    race_record["guests"].append({
                        "npc_id": guest.id, "name": guest.name, "title": "卿族",
                        "defense_required": True, "offense_opt_in": False,
                    })
                    race_record["qingzu_initialized"] = True
                    news.append(f"{RACE_DEFINITIONS.get(race_id, {}).get('name', race_id)}议事者延请{guest.name}为卿族。")
        # High-realm players occasionally receive a weak-sect guest invitation.
        realm_index, _ = self._actual_player_realm(game.player)
        if not state.get("pending_guest_invitation") and realm_index >= 4 and rng.random() < .08:
            candidates = []
            for sect in game.sects.values():
                if sect.extinct or sect.world != game.player.world or sect.id == game.player.faction_id:
                    continue
                strongest = max((npc.realm_index for npc in self._sect_members(game, sect) if npc.alive), default=0)
                record = self._ensure_intrigue_faction(game, "sect", sect.id)
                if strongest + 2 <= realm_index and not any(row.get("npc_id") == PLAYER_ID for row in record.get("guests", [])):
                    candidates.append(sect)
            if candidates:
                sect = rng.choice(candidates)
                state["pending_guest_invitation"] = {"kind": "sect", "faction_id": sect.id, "faction_name": sect.name, "title": "客卿长老", "world": sect.world}
                news.append(f"{sect.name}看重你的修为，遣使邀你担任客卿长老。")
        # One NPC-led faction may act per three units: O(members), never O(N²).
        if game.diplomacy_unit % 3 == 0:
            candidates = [sect for sect in game.sects.values() if not sect.extinct and not sect.founded_by_player and sect.id != game.player.faction_id]
            if candidates:
                state["ai_cursor"] = (int(state.get("ai_cursor", 0)) + 1) % len(candidates)
                sect = candidates[state["ai_cursor"]]
                record = self._ensure_intrigue_faction(game, "sect", sect.id)
                controller = self._intrigue_find_npc(game, str(record.get("controller_id", "")))
                eligible_voters = [
                    npc for npc in self._intrigue_members(game, "sect", sect.id)
                    if self._intrigue_has_decision_authority(game, "sect", sect.id, npc.id)
                ]
                if controller and eligible_voters and rng.random() < .16:
                    style = self._intrigue_governance_style(game, controller)
                    resolution_type = {"internal": "mass_recruitment", "balance": "investment", "diplomacy": "form_alliance", "military": "declare_war"}[style]
                    target_id = ""
                    if resolution_type in {"form_alliance", "declare_war"}:
                        possible = [row.id for row in candidates if row.id != sect.id and row.world == sect.world]
                        if not possible:
                            resolution_type = "investment"
                        else:
                            target_id = rng.choice(possible)
                    resolution = self._intrigue_resolve(game, "sect", sect.id, resolution_type, target_id, None, controller.id, rng)
                    if game.debug_world_news or sect.world == game.player.world:
                        news.append(f"{sect.name}在{STYLE_LABELS[style]}主政下提出{RESOLUTION_LABELS[resolution_type]}，决议{('通过' if resolution['result'] == 'passed' else '遭否决')}。")
        return news
