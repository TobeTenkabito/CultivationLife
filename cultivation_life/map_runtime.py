from __future__ import annotations

import random
from typing import Any

from .content_registry import WORLD_SYSTEMS
from .system.map_system import MapContentError
from .models import GameState, HistoryRecord
from .runtime import decode_rng, encode_rng, now_iso
from .system.possession_system import advance_player_age, current_body_age


class MapTravelMixin:
    """地图旅行的流程编排；依赖主引擎提供年度世界结算的领域钩子。"""

    def _advance_world_year(
        self, game: GameState, rng: random.Random, era_news: list[str], *, encounters: bool = True,
    ) -> bool:
        player = game.player
        era_news.extend(self._advance_sage_year(game, rng))
        self._advance_ghost_phase_two_year(game, rng)
        self._advance_monster_bloodline_year(game)
        self._resolve_breakthroughs(game, rng)
        if not player.alive or game.pending_event:
            return False
        self._check_tribulation(game, rng)
        if not player.alive or game.pending_event:
            return False
        if player.lifespan is not None and current_body_age(player) >= player.lifespan:
            self._die(game, "寿元已尽", "SYS_LIFESPAN")
            return False
        era_news.extend(self._annual_sect_update(game, rng))
        era_news.extend(self._annual_world_npc_update(game, rng))
        self._annual_demonic_update(game, rng)
        self._annual_spirit_field_update(player)
        if not player.alive:
            return False
        self._resolve_breakthroughs(game, rng)
        if not player.alive or game.pending_event:
            return False
        if self._advance_guixu_calendar(game, rng, era_news):
            return False
        if not encounters:
            return True
        return not (
            self._maybe_wanted_encounter(game, rng)
            or self._maybe_race_war_ambush(game, rng)
            or self._maybe_artifact_synthesis(game, rng)
            or self._maybe_mortal_root_completion(game, rng)
        )

    def travel_map(self, game_id: str, destination: str) -> dict[str, Any]:
        game = self._load(game_id)
        player = game.player
        if not player.alive:
            raise ValueError("此生已经结束")
        if game.pending_event:
            raise ValueError("请先处理当前事件")
        if player.imprisonment:
            raise ValueError("你身陷大牢，无法远行")
        if player.ghost_captor:
            raise ValueError("魂印受制于拘魂者，无法自行远行")
        try:
            plan = self.maps.travel_plan(
                player.world, player.location_id or "", destination, player.realm_index,
                self._monster_travel_multiplier(player, destination),
            )
        except MapContentError as error:
            raise ValueError(str(error)) from error
        if plan.status == "blocked":
            raise ValueError(plan.warning)

        rng = decode_rng(game.seed, game.rng_state)
        start_age = player.age
        era_news: list[str] = []
        for _ in range(plan.years):
            advance_player_age(player)
            continue_world = self._advance_world_year(game, rng, era_news, encounters=False)
            if player.alive:
                self._advance_soul_erosion_time(game, 1)
            if not continue_world or not player.alive:
                break
        completed = player.alive and game.pending_event is None and player.age - start_age == plan.years
        if completed:
            player.location_id = plan.destination
            self._clear_market(game)
            if plan.status == "lethal":
                self._die(game, plan.warning, "SYS_MAP_TRAVEL_DEATH")
                result = "dead"
                summary = f"你强行踏上远途，历时 {plan.years} 年抵达边缘，却因{plan.warning}。"
            else:
                self._ensure_market(game, rng)
                result = "arrived"
                route_names = [self.maps.location(player.world, node)["name"] for node in plan.route]
                summary = f"你沿{'—'.join(route_names)}行进，耗时 {plan.years} 年抵达目的地。"
        else:
            result = "interrupted"
            summary = f"远行在第 {player.age - start_age} 年被突发变故中断，你仍停留在原地。"
            self._ensure_market(game, rng)
        game.history.append(HistoryRecord(
            "SYS_MAP_TRAVEL", 1, player.age, "跨域远行", plan.destination, result, summary,
            {"from":plan.origin, "to":plan.destination, "years":player.age - start_age},
            ["action", "travel", "map", f"world:{player.world}"],
        ))
        elapsed = player.age - start_age
        if elapsed:
            time_unit = int(WORLD_SYSTEMS["time_units"][str(player.realm_index)])
            completed_units = max(1, (elapsed + time_unit - 1) // time_unit)
            for _ in range(completed_units):
                era_news.extend(self._advance_diplomacy_unit(game, rng))
                self._advance_concubine_aftermath(game, rng)
                era_news.extend(self._advance_heavenly_court_unit(game, rng))
                era_news.extend(self._advance_intrigue_unit(game, rng))
            artifact_news = self._advance_natal_artifact(game, "travel", completed_units)
            if artifact_news:
                era_news.append(artifact_news)
            self._advance_concubine_status(game, completed_units)
            self._advance_player_bounties(game, rng)
            if elapsed >= 5:
                self._record_era_summary(game, start_age, era_news)
            if player.alive:
                self._advance_auction_clock(game, rng)
                self._advance_exchange_clock(game, rng)
        self._compact_world_history(game)
        game.updated_at = now_iso()
        game.rng_state = encode_rng(rng)
        self.store.save(game)
        return self.present(game)
