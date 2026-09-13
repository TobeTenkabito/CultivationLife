from __future__ import annotations

import math
from typing import Any

from .content_registry import WORLD_SYSTEMS
from .models import GameState, HistoryRecord
from .runtime import decode_rng, encode_rng, now_iso


class HeavenlyCourtSystemMixin:
    """天庭政治层；按仙界时间单位结算，49 席仅保存投票摘要。"""

    @staticmethod
    def _court_config() -> dict[str, Any]:
        return WORLD_SYSTEMS["heavenly_court"]

    @staticmethod
    def _court_grade_for_realm(realm_index: int) -> int:
        return 2 if realm_index >= 11 else 4 if realm_index >= 10 else 6

    def _ensure_heavenly_court(self, game: GameState, rng: Any) -> bool:
        if game.heavenly_court:
            return False
        config = self._court_config()
        officials: dict[str, dict[str, Any]] = {}
        celestial_people = [
            npc for npc in [
                *game.world_npcs.values(),
                *(npc for sect in game.sects.values() if sect.world == "celestial" for npc in sect.npcs),
            ]
            if npc.world == "celestial" and npc.alive
        ]
        for npc in celestial_people:
            officials[npc.id] = {
                "id": npc.id, "name": npc.name,
                "grade": self._court_grade_for_realm(npc.realm_index),
                "faction_id": npc.faction_id or self._npc_faction_id(game, npc.id),
                "support": round(float(npc.affinity or 50), 1), "source": "npc",
            }

        real_sects = [sect for sect in game.sects.values() if sect.world == "celestial" and not sect.extinct]
        seats: list[dict[str, Any]] = []
        prefixes = ["玄都", "云海", "青帝", "天河", "万象", "九元", "紫极"]
        suffixes = ["宗", "阁", "宫", "院", "门", "府", "观", "殿", "洞"]
        delegate_names = ["沈观澜", "陆星河", "闻天羽", "顾元真", "苏玄微", "江法明", "凌清风", "白云生", "夏无尘", "唐子衿", "韩清远", "林天行"]
        for index in range(int(config["seat_count"])):
            if index < len(real_sects):
                sect = real_sects[index]
                representative = max(sect.npcs, key=lambda npc: (npc.realm_index, npc.layer), default=None)
                representative_id = representative.id if representative else ""
                name, sect_id = sect.name, sect.id
                influence = rng.randint(92, 138)
            else:
                delegate_id = f"court_delegate_{index + 1:02d}"
                sect_id = f"court_virtual_sect_{index + 1:02d}"
                name = f"{rng.choice(prefixes)}{rng.choice(suffixes)}"
                representative_id = delegate_id
                influence = rng.randint(22, 105)
                officials[delegate_id] = {
                    "id": delegate_id, "name": rng.choice(delegate_names) + str(index + 1),
                    "grade": rng.randint(3, 8), "faction_id": sect_id,
                    "support": rng.randint(38, 68), "source": "court_pool",
                }
            size = "large" if influence >= 91 else "medium" if influence >= 51 else "small"
            seats.append({
                "id": f"seat_{index + 1:02d}", "sect_id": sect_id, "name": name,
                "influence": influence, "size": size, "representative_id": representative_id,
            })

        game.heavenly_court = {
            "unit": 0, "authority": float(config["initial_authority"]),
            "treasury": float(config["initial_treasury"]), "equipment": 0.0,
            "player_grade": int(config["player_initial_grade"]), "player_merit": 0,
            "player_support": 50.0,
            "offices": {office["id"]: None for office in config["offices"]},
            "laws": {law["id"]: False for law in config["laws"]},
            "active_decrees": [], "wanted_ids": [], "officials": officials, "seats": seats,
            "election_queue": [], "open_election": None, "pledges": [], "last_vote": None,
        }
        return True

    def _player_court_representative(self, game: GameState) -> bool:
        sect = game.sects.get(game.player.faction_id or "")
        if not sect or sect.world != "celestial" or sect.extinct:
            return False
        living = [npc for npc in self._sect_members(game, sect) if npc.alive]
        return bool(
            sect.founded_by_player or not living
            or (game.player.realm_index, game.player.layer) >= max((npc.realm_index, npc.layer) for npc in living)
        )

    def _sync_player_court_identity(self, game: GameState) -> None:
        court = game.heavenly_court
        if not court:
            return
        court["officials"]["player"] = {
            "id": "player", "name": game.player.name, "grade": int(court["player_grade"]),
            "faction_id": game.player.faction_id, "support": float(court["player_support"]),
            "source": "player",
        }
        if self._player_court_representative(game):
            seat = next((row for row in court["seats"] if row["sect_id"] == game.player.faction_id), None)
            if seat:
                seat["representative_id"] = "player"

    @staticmethod
    def _court_holder_ids(court: dict[str, Any]) -> list[str]:
        return [str(row["holder_id"]) for row in court["offices"].values() if row]

    @staticmethod
    def _court_player_controls(court: dict[str, Any]) -> int:
        return sum(1 for row in court["offices"].values() if row and row.get("holder_id") == "player")

    def _court_open_election(self, game: GameState, office_id: str, rng: Any) -> None:
        court = game.heavenly_court
        self._sync_player_court_identity(game)
        court["treasury"] = max(
            0.0, float(court["treasury"]) - float(self._court_config().get("election_treasury_cost", 0)),
        )
        eligible = [row for row in court["officials"].values() if int(row.get("grade", 9)) <= 4]
        incumbent = court["offices"].get(office_id)
        if incumbent and incumbent.get("holder_id") == "player" and float(court["player_support"]) < 25:
            for key, row in court["offices"].items():
                if row and row.get("holder_id") == "player":
                    court["offices"][key] = None
            eligible = [row for row in eligible if row["id"] != "player"]
        player_row = next((row for row in eligible if row["id"] == "player"), None)
        others = [row for row in eligible if row["id"] != "player"]
        candidate_count = min(rng.randint(4, 7), len(others)) if others else 0
        candidates = rng.sample(others, candidate_count) if candidate_count else []
        if player_row:
            candidates.append(player_row)
        if not candidates:
            return
        court["open_election"] = {
            "office_id": office_id, "round": 1,
            "candidates": [row["id"] for row in candidates], "opened_unit": int(court["unit"]),
        }
        if not player_row:
            for _ in range(50):
                success, _ = self._court_resolve_election_round(game, rng, "none", "")
                if success:
                    break

    def _court_open_next_queued_election(self, game: GameState, rng: Any) -> None:
        court = game.heavenly_court
        if not court.get("open_election") and court.get("election_queue"):
            self._court_open_election(game, str(court["election_queue"].pop(0)), rng)

    def _court_resolve_election_round(
        self, game: GameState, rng: Any, method: str, pledge_id: str,
    ) -> tuple[bool, str]:
        court = game.heavenly_court
        election = court.get("open_election")
        if not election:
            raise ValueError("当前没有待处理的七曜选举")
        candidate_ids = list(election["candidates"])
        player_bonus = 0.0
        if "player" in candidate_ids:
            if method == "relationship":
                affinities = [
                    float(npc.affinity or 0) for npc in game.world_npcs.values()
                    if npc.world == "celestial" and npc.alive
                ]
                player_bonus = 0.25 + max([0.0, *affinities]) / 180
            elif method == "faction":
                seat = next((row for row in court["seats"] if row["sect_id"] == game.player.faction_id), None)
                if not seat or seat.get("representative_id") != "player":
                    raise ValueError("你并非宗门的天庭代表，无法调动本宗选票")
                spend = min(15, int(seat["influence"]))
                seat["influence"] -= spend
                player_bonus = 0.32 + spend / 50
            elif method in {"promise_decree", "promise_law"}:
                table = "decrees" if method == "promise_decree" else "laws"
                if pledge_id not in {row["id"] for row in self._court_config()[table]}:
                    raise ValueError("承诺的决议或天条不存在")
                court["pledges"].append({
                    "kind": "decree" if method == "promise_decree" else "law",
                    "id": pledge_id, "deadline_unit": int(court["unit"]) + 2,
                })
                player_bonus = 0.62

        votes = {candidate_id: 0 for candidate_id in candidate_ids}
        for seat in court["seats"]:
            scores = []
            for candidate_id in candidate_ids:
                official = court["officials"][candidate_id]
                score = 1.0 + float(official.get("support", 50)) / 100
                if candidate_id == "player":
                    score += player_bonus + float(court["player_support"]) / 180
                    if seat.get("representative_id") == "player":
                        score += 1.3
                if official.get("faction_id") == seat.get("sect_id"):
                    score += 0.7
                scores.append(max(0.05, score))
            selected = rng.choices(candidate_ids, weights=scores, k=1)[0]
            votes[selected] += 1

        winner_id, winner_votes = max(votes.items(), key=lambda row: (row[1], row[0]))
        threshold = math.ceil(int(self._court_config()["seat_count"]) / 4)
        election["votes"] = votes
        if winner_votes < threshold:
            election["round"] = int(election.get("round", 1)) + 1
            return False, f"最高得票仅 {winner_votes}，未达 {threshold} 票门槛，立即重新选举。"
        office_id = str(election["office_id"])
        official = court["officials"][winner_id]
        term = int(self._court_config()["term_units"])
        court["offices"][office_id] = {
            "holder_id": winner_id, "holder_name": official["name"],
            "start_unit": int(court["unit"]), "end_unit": int(court["unit"]) + term,
            "votes": winner_votes,
        }
        office_name = next(row["name"] for row in self._court_config()["offices"] if row["id"] == office_id)
        court["open_election"] = None
        game.history.append(HistoryRecord(
            "SYS_COURT_ELECTION", 1, game.player.age, f"{office_name}大选", winner_id, "elected",
            f"{official['name']}以 {winner_votes}/49 票当选{office_name}，任期为七个仙界时间单位。",
            {"office_id": office_id, "winner_id": winner_id, "votes": votes},
            ["system", "celestial", "heavenly_court", "election"],
        ))
        return True, f"{official['name']}以 {winner_votes}/49 票当选{office_name}。"

    def _advance_heavenly_court_unit(self, game: GameState, rng: Any) -> list[str]:
        if game.player.world != "celestial":
            return []
        self._ensure_heavenly_court(game, rng)
        court = game.heavenly_court
        self._sync_player_court_identity(game)
        court["unit"] = int(court["unit"]) + 1
        unit = int(court["unit"])
        laws = court["laws"]
        court["active_decrees"] = [row for row in court["active_decrees"] if int(row["expires_unit"]) >= unit]

        income_multiplier = 1.0
        for decree in court["active_decrees"]:
            income_multiplier *= float(decree.get("income_multiplier", 1.0))
        if laws.get("wide_domain"):
            income_multiplier *= 0.95
            court["authority"] += 5
        if laws.get("traveling_palace"):
            income_multiplier *= 1.05
            court["authority"] = max(0.0, float(court["authority"]) - 5)
        if laws.get("direct_appointment_law"):
            court["authority"] += 5
        if laws.get("recommendation_law"):
            court["authority"] += 5
        court["treasury"] += round(float(self._court_config()["base_treasury_income"]) * income_multiplier, 2)

        if laws.get("celestial_sects"):
            for seat in court["seats"]:
                seat["influence"] = max(0, int(seat["influence"]) + (-5 if seat["size"] == "large" else 5))
        if laws.get("direct_appointment_law"):
            for seat in court["seats"]:
                seat["influence"] = max(0, int(seat["influence"]) - 5)
        if laws.get("recommendation_law"):
            for seat in court["seats"]:
                seat["influence"] += 5

        broken = [row for row in court["pledges"] if int(row["deadline_unit"]) < unit]
        if broken:
            court["player_support"] = max(0.0, float(court["player_support"]) - 15 * len(broken))
            court["pledges"] = [row for row in court["pledges"] if row not in broken]

        office_id = self._court_config()["offices"][(unit - 1) % 7]["id"]
        if int(court["player_grade"]) <= 4:
            court["election_queue"].append(office_id)
            self._court_open_next_queued_election(game, rng)
        else:
            self._court_open_election(game, office_id, rng)
        return [f"{game.player.age}岁：天庭第 {unit} 时间单位完成府库结算与七曜轮选。"]

    def resolve_heavenly_election(self, game_id: str, method: str = "none", pledge_id: str = "") -> dict[str, Any]:
        game = self._load(game_id)
        if game.player.world != "celestial" or game.pending_event:
            raise ValueError("当前无法处理天庭选举")
        rng = decode_rng(game.seed, game.rng_state)
        success, _ = self._court_resolve_election_round(game, rng, method, pledge_id)
        if success:
            self._court_open_next_queued_election(game, rng)
        game.rng_state = encode_rng(rng)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    @staticmethod
    def _court_honor_pledge(court: dict[str, Any], kind: str, policy_id: str) -> None:
        honored = [row for row in court["pledges"] if row["kind"] == kind and row["id"] == policy_id]
        if honored:
            court["player_support"] = min(100.0, float(court["player_support"]) + 5 * len(honored))
            court["pledges"] = [row for row in court["pledges"] if row not in honored]

    def heavenly_court_action(
        self, game_id: str, action: str, target_id: str = "", enact: bool | None = None,
        influence_spend: int = 0,
    ) -> dict[str, Any]:
        game = self._load(game_id)
        if game.player.world != "celestial" or game.pending_event:
            raise ValueError("当前无法处理天庭政务")
        rng = decode_rng(game.seed, game.rng_state)
        self._ensure_heavenly_court(game, rng)
        court = game.heavenly_court
        self._sync_player_court_identity(game)
        if court.get("open_election"):
            raise ValueError("请先完成当前七曜选举")

        if action == "examination":
            result, summary = self._court_examination(game, rng)
        elif action.startswith("decree:"):
            result, summary = self._court_enact_decree(
                game, action.split(":", 1)[1], target_id, rng, influence_spend,
            )
        elif action.startswith("law:"):
            result, summary = self._court_vote_law(
                game, action.split(":", 1)[1], enact, rng, influence_spend,
            )
        else:
            raise ValueError("未知天庭政务")

        game.history.append(HistoryRecord(
            "SYS_HEAVENLY_COURT_ACTION", 1, game.player.age, "天庭政务", action, result, summary,
            {"authority": round(float(court["authority"]), 2), "treasury": round(float(court["treasury"]), 2)},
            ["system", "celestial", "heavenly_court", "politics"],
        ))
        game.rng_state = encode_rng(rng)
        game.updated_at = now_iso()
        self.store.save(game)
        return self.present(game)

    def _court_examination(self, game: GameState, rng: Any) -> tuple[str, str]:
        court = game.heavenly_court
        grade = int(court["player_grade"])
        if grade <= 1:
            raise ValueError("你已位列一品天官")
        target_grade = grade - 1
        needed = int(self._court_config()["grade_merit_thresholds"][str(target_grade)])
        if int(court["player_merit"]) < needed:
            raise ValueError(f"晋升{target_grade}品需要 {needed} 功德")
        chance = min(0.95, 0.72 + max(0, game.player.realm_index - 9) * 0.06)
        if rng.random() < chance:
            court["player_grade"] = target_grade
            return "promoted", f"你通过考核，晋为{target_grade}品天官。"
        return "failed", f"你未通过本次考核，功德保留（通过率 {chance:.0%}）。"

    def _court_enact_decree(
        self, game: GameState, decree_id: str, target_id: str, rng: Any, influence_spend: int = 0,
    ) -> tuple[str, str]:
        court = game.heavenly_court
        if self._court_player_controls(court) < 1:
            raise ValueError("只有七曜星君可以推行决议")
        decree = next((row for row in self._court_config()["decrees"] if row["id"] == decree_id), None)
        if not decree:
            raise ValueError("未知天庭决议")
        laws = court["laws"]
        if decree.get("requires_law") and not laws.get(decree["requires_law"]):
            raise ValueError("当前天条尚未授予该决议权限")
        if decree.get("forbidden_law") and laws.get(decree["forbidden_law"]):
            raise ValueError("当前天条禁止这项决议")
        slots = int(self._court_config()["base_decree_slots"]) + int(laws.get("assistant_officials", False))
        if len(court["active_decrees"]) >= slots:
            raise ValueError("当前决议槽位已满")
        cost = float(decree.get("authority_cost", self._court_config()["decree_authority_cost"]))
        if float(court["authority"]) < cost:
            raise ValueError("天庭权威不足")
        influence_spend = self._court_spend_influence(game, influence_spend)
        multiplier = (1.5 if laws.get("official_system") else 1.0) * (1.0 + influence_spend / 50)
        treasury_delta = (
            float(decree.get("immediate_treasury", 0)) * multiplier
            - float(self._court_config().get("policy_treasury_cost", 0))
        )
        if float(court["treasury"]) + treasury_delta < 0:
            raise ValueError("天庭府库不足以执行该决议")

        target_npc = None
        if decree_id in {"direct_appointment", "wanted"}:
            target_npc = self._find_npc(game, target_id)
            if not target_npc or not target_npc.alive or target_npc.world != "celestial":
                raise ValueError("必须指定一名仙界存活 NPC")
        if decree_id == "protect" and target_id not in court["wanted_ids"]:
            raise ValueError("该人并不在天庭通缉名单上")

        court["authority"] -= cost
        court["treasury"] += treasury_delta
        court["equipment"] += float(decree.get("immediate_equipment", 0)) * multiplier
        court["player_support"] = max(
            0.0, min(100.0, float(court["player_support"]) + float(decree.get("support", 0)) * multiplier),
        )
        if decree_id == "direct_appointment" and target_npc:
            official = court["officials"].setdefault(target_npc.id, {
                "id": target_npc.id, "name": target_npc.name,
                "faction_id": target_npc.faction_id, "support": 50, "source": "npc",
            })
            official["grade"] = 9
        elif decree_id == "recommend_official":
            candidates = [
                row for row in court["officials"].values()
                if row["id"] != "player" and int(row.get("grade", 9)) >= 7
            ]
            if candidates:
                rng.choice(candidates)["grade"] = 9
        elif decree_id == "wanted" and target_npc and target_npc.id not in court["wanted_ids"]:
            court["wanted_ids"].append(target_npc.id)
        elif decree_id == "protect":
            court["wanted_ids"].remove(target_id)
        court["active_decrees"].append({
            "id": decree_id, "name": decree["name"],
            "expires_unit": int(court["unit"]) + int(self._court_config()["decree_duration_units"]),
            "income_multiplier": decree.get("income_multiplier", 1.0),
        })
        self._court_honor_pledge(court, "decree", decree_id)
        return "decree_enacted", f"天庭推行《{decree['name']}》，生效五个时间单位。"

    def _court_vote_law(
        self, game: GameState, law_id: str, enact: bool | None, rng: Any, influence_spend: int = 0,
    ) -> tuple[str, str]:
        court = game.heavenly_court
        if self._court_player_controls(court) < 1:
            raise ValueError("只有七曜星君可以发起天条表决")
        law = next((row for row in self._court_config()["laws"] if row["id"] == law_id), None)
        if not law:
            raise ValueError("未知天条")
        desired = not bool(court["laws"].get(law_id)) if enact is None else bool(enact)
        holders = self._court_holder_ids(court)
        if len(holders) < 7:
            raise ValueError("七曜尚未全部就位，无法进行天条表决")
        operating_cost = float(self._court_config().get("policy_treasury_cost", 0))
        if float(court["treasury"]) < operating_cost:
            raise ValueError("天庭府库不足以召开天条表决")
        court["treasury"] -= operating_cost
        controlled = self._court_player_controls(court)
        influence_spend = self._court_spend_influence(game, influence_spend)
        persuasion = min(0.35, influence_spend * 0.02)
        votes = [
            holder_id == "player" or rng.random() < 0.48 + float(court["player_support"]) / 500 + persuasion
            for holder_id in holders
        ]
        passed = controlled >= 4 or sum(votes) >= 4
        court["last_vote"] = {
            "law_id": law_id, "enact": desired, "yes": sum(votes), "no": 7 - sum(votes), "passed": passed,
        }
        if passed:
            court["laws"][law_id] = desired
            self._court_honor_pledge(court, "law", law_id)
        return (
            "law_passed" if passed else "law_rejected",
            f"七曜以 {sum(votes)} 票赞成、{7 - sum(votes)} 票反对，"
            f"{'通过' if passed else '否决'}了《{law['name']}》的{'施行' if desired else '废除'}。",
        )

    def _court_spend_influence(self, game: GameState, requested: int) -> int:
        spend = max(0, min(15, int(requested or 0)))
        if not spend:
            return 0
        court = game.heavenly_court
        seat = next((row for row in court["seats"] if row["sect_id"] == game.player.faction_id), None)
        if not seat or seat.get("representative_id") != "player":
            raise ValueError("只有本宗天庭代表可以调动宗门影响力")
        if int(seat["influence"]) < spend:
            raise ValueError("本宗影响力不足")
        seat["influence"] -= spend
        return spend

    def _add_court_merit(self, game: GameState, amount: int) -> str:
        if game.player.world != "celestial":
            return "天庭功德只在仙界记档。"
        if not game.heavenly_court:
            raise ValueError("天庭尚未完成初始化")
        game.heavenly_court["player_merit"] = max(
            0, int(game.heavenly_court["player_merit"]) + int(amount),
        )
        return f"天庭功德 {int(amount):+d}。"

    def _public_heavenly_court(self, game: GameState) -> dict[str, Any]:
        if game.player.world != "celestial":
            return {"visible": False}
        court = game.heavenly_court
        if not court:
            return {"visible": True, "initialized": False}
        self._sync_player_court_identity(game)
        config = self._court_config()
        office_defs = {row["id"]: row for row in config["offices"]}
        offices = []
        for office in config["offices"]:
            holder = court["offices"].get(office["id"])
            offices.append({**office, "holder": holder})
        laws = [dict(row, active=bool(court["laws"].get(row["id"]))) for row in config["laws"]]
        decrees = []
        for row in config["decrees"]:
            enabled = self._court_player_controls(court) > 0
            reason = "" if enabled else "需先当选七曜星君"
            if row.get("requires_law") and not court["laws"].get(row["requires_law"]):
                enabled, reason = False, "缺少前置天条"
            if row.get("forbidden_law") and court["laws"].get(row["forbidden_law"]):
                enabled, reason = False, "被当前天条禁止"
            decrees.append(dict(row, enabled=enabled, disabled_reason=reason))
        election = court.get("open_election")
        public_election = None
        if election:
            public_election = {
                **election,
                "office_name": office_defs[election["office_id"]]["name"],
                "candidates": [court["officials"][candidate_id] for candidate_id in election["candidates"]],
                "player_candidate": "player" in election["candidates"],
            }
        player_seat = next((row for row in court["seats"] if row["sect_id"] == game.player.faction_id), None)
        target_npcs = [
            {"id": npc.id, "name": npc.name, "realm_name": self._npc_realm_name(npc),
             "wanted": npc.id in court["wanted_ids"]}
            for npc in [
                *game.world_npcs.values(),
                *(npc for sect in game.sects.values() if sect.world == "celestial" for npc in sect.npcs),
            ]
            if npc.alive and npc.world == "celestial"
        ]
        if "player" in court["wanted_ids"]:
            target_npcs.insert(0, {"id": "player", "name": game.player.name,
                                   "realm_name": "你本人", "wanted": True})
        seat_sizes = {
            size: sum(1 for seat in court["seats"] if seat.get("size") == size)
            for size in ("large", "medium", "small")
        }
        return {
            "visible": True, "initialized": True, "unit": int(court["unit"]),
            "authority": round(float(court["authority"]), 2),
            "treasury": round(float(court["treasury"]), 2),
            "equipment": round(float(court["equipment"]), 2),
            "player_grade": int(court["player_grade"]), "player_merit": int(court["player_merit"]),
            "player_support": round(float(court["player_support"]), 1),
            "player_controls": self._court_player_controls(court),
            "player_is_representative": self._player_court_representative(game),
            "player_seat_influence": int(player_seat["influence"]) if player_seat else 0,
            "seat_count": len(court["seats"]), "seat_sizes": seat_sizes,
            "offices": offices, "laws": laws,
            "decrees": decrees, "active_decrees": list(court["active_decrees"]),
            "wanted_ids": list(court["wanted_ids"]), "target_npcs": target_npcs,
            "election": public_election, "pledges": list(court["pledges"]),
            "last_vote": court.get("last_vote"),
            "decree_slots": int(config["base_decree_slots"]) + int(court["laws"].get("assistant_officials", False)),
            "next_grade_merit": (
                int(config["grade_merit_thresholds"].get(str(int(court["player_grade"]) - 1), 0))
                if int(court["player_grade"]) > 1 else None
            ),
        }

    def _court_law_active(self, game: GameState, law_id: str) -> bool:
        return bool(game.heavenly_court and game.heavenly_court.get("laws", {}).get(law_id))
