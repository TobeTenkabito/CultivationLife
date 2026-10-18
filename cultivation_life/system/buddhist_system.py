"""World-local Dharma networks. No stored resource conversion or combat caches."""
from __future__ import annotations
from .spatial_capabilities import scope_key, site_key, local_names

from .buddhist.rules import (
    buddhist_config as buddhist_config,
    buddhist_active as buddhist_active,
    site_state as site_state,
    followers as followers,
    selected_blessings as selected_blessings,
    upkeep as upkeep,
    set_dharma_karma as set_dharma_karma,
    buddhist_modifier as buddhist_modifier,
)

from .buddhist_wish import ensure_wish, nirvana, nirvana_target

import copy
import math

from ..content_registry import CONTENT_DOCUMENTS, WORLD_SYSTEMS
from ..models import HistoryRecord
from ..runtime import decode_rng, encode_rng, now_iso
from ..rules import add_item, remove_item, expected_combat_power
from .faction_geography import local_authorities, authority_permission_exempt
from .path_modifiers import register_provider
from .possession_system import advance_player_age


register_provider("buddhist", buddhist_modifier)


from .character.dependencies import (
    BuddhistGuardDependencies,
    BuddhistStateDependencies,
)

def _ensure_buddhist_state(game):
    if not buddhist_active(game):
        return
    state = game.buddhist_state
    ensure_wish(game)
    state.setdefault("version", 1)
    state.setdefault("dharma_karma", 0.0)
    state.setdefault("grace_units", None)
    state.setdefault("assembly", None)
    state.setdefault("history", [])
    site_state(state, scope_key(game), site_key(game))
    for network in state['worlds'].values():
        # Adopt existing networks at their already observed year, including
        # old saves whose ordinary regional clocks still lag behind.
        network.setdefault('settled_year', game.player.age)


def _advance_buddhist_society_year(game):
    """Decay only the society owning the current regional or space year."""
    if not buddhist_active(game):
        return
    from ..regional_context import region
    config, player = buddhist_config(), game.player
    selected = region(game) or (scope_key(game) if game.world_simulation else None)
    for identity, world in game.buddhist_state.get("worlds", {}).items():
        if selected is not None and identity != selected:
            continue
        if game.world_simulation and world.get('settled_year', -1) >= game.player.age:
            continue
        if region(game) is None and ((player.world in {'lost', 'rift'} and identity != scope_key(game))
                or (identity in game.spatial_state.get('instances', {}) and identity != scope_key(game))):
            continue
        for site in world["sites"].values():
            temple = config["temples"][int(site["temple"])]
            site["followers"] = max(temple["floor"], site["followers"] * (1 - temple["decay"]))
        world['settled_year'] = game.player.age


def _advance_buddhist_year(deps: BuddhistStateDependencies, game):
    if not buddhist_active(game):
        return []
    deps._ensure_buddhist_state(game)
    if not game.world_simulation or game.player.world in {'lost', 'rift'}:
        deps._advance_buddhist_society_year(game)
    state, config, player = game.buddhist_state, buddhist_config(), game.player
    grace_before = state.get("grace_units")
    total = followers(state, scope_key(game))
    income = min(config["annual_karma_cap"], math.log1p(total / config["follower_income_scale"]) * config["follower_income_coefficient"])
    income += sum(config["temple_karma"] for site in state["worlds"][scope_key(game)]["sites"].values() if site["temple"] == 3)
    set_dharma_karma(game, state["dharma_karma"] + income)
    chosen = list(selected_blessings(game))
    expense = sum(upkeep(game, blessing) for blessing in chosen)
    set_dharma_karma(game, state["dharma_karma"] - expense)
    active = selected_blessings(game)
    if "stipend" in active and total > 0:
        table = config["blessings"]["stipend"]["realm_stones"]
        from .economy.rewards import grant
        grant(game,table[min(player.realm_index,len(table)-1)],'佛门信众供奉（背景实付）')
    for blessing, attribute in [("karma_decay", "karma"), ("sha_decay", "sha_qi")]:
        if blessing in active:
            spec = config["blessings"][blessing]
            old = getattr(player, attribute)
            setattr(player, attribute, max(0, old - max(spec["minimum"], old * spec["rate"])))
    # Starting a new grace period this year does not spend its first fraction immediately.
    if state["dharma_karma"] < -25 and grace_before is not None:
        unit = max(1, int(WORLD_SYSTEMS["time_units"][str(player.realm_index)]))
        state["grace_units"] = max(0, float(state["grace_units"] or 0) - 1 / unit)
        if state["grace_units"] < 1e-9:
            state["grace_units"] = 0
    state["last_settlement"] = {"age": player.age, "income": round(income, 3), "upkeep": round(expense, 3)}
    return []


def _buddhist_permissions(game):
    player, config = game.player, buddhist_config()
    site = site_state(game.buddhist_state, scope_key(game), site_key(game))
    return [{"id": row.id, "name": row.name,
             "exempt": authority_permission_exempt(game, row),
             "intimidated": player.realm_index >= {1: 4, 2: 7, 3: 10}.get(int(WORLD_SYSTEMS["world_profiles"][player.world]["tier"]), 10),
             "expires": site["permissions"].get(row.id, 0),
             "permitted": authority_permission_exempt(game, row) or site["permissions"].get(row.id, 0) > player.age,
             "fee": config["permission_fee"] * max(1, player.realm_index) ** 2}
            for row in local_authorities(game, player.world, player.location_id)]


def _buddhist_burden(game):
    config = buddhist_config()
    return max(0, game.player.karma) * config["burden_karma_weight"] + max(0, game.player.sha_qi) * config["burden_sha_weight"]


def _public_buddhist(deps: BuddhistStateDependencies, game):
    if not buddhist_active(game):
        return {"available": False}
    deps._ensure_buddhist_state(game)
    state, player, config = game.buddhist_state, game.player, buddhist_config()
    site = site_state(state, scope_key(game), site_key(game))
    burden = deps._buddhist_burden(game)
    chosen = selected_blessings(game)
    from ..rules import effective_fame
    audience = round(config["attendance_base"] + player.realm_index * config["attendance_realm"] + math.sqrt(max(0, effective_fame(player))) * config["attendance_fame"] + math.sqrt(site["followers"]) * config["attendance_followers"] + site["temple"] * config["attendance_temple"])
    sites = []
    for world, network in state["worlds"].items():
        for location, row in network["sites"].items():
            if not row["followers"] and not row["temple"] and world != scope_key(game):
                continue
            sites.append({"world": world, "world_name": local_names(game, deps.maps, world, location)[0],
                          "location": location, "name": local_names(game, deps.maps, world, location)[1],
                          "active": world == scope_key(game), **copy.deepcopy(row),
                          **config["temples"][row["temple"]]})
    level = site["temple"]
    tier = int(WORLD_SYSTEMS["world_profiles"][player.world]["tier"])
    return {"available": True, "karma": state["dharma_karma"], "grace_units": state["grace_units"],
            "wish": {**copy.deepcopy(state["wish"]), "blocked": nirvana_target(deps, game)[1]},
            "raw_karma": player.karma, "raw_sha": player.sha_qi, "effective_fame": effective_fame(player),
            "followers": round(followers(state, scope_key(game))), "sites": sites,
            "site": copy.deepcopy(site), "temple_cost": config["temples"][level + 1]["cost"] * config["temple_tier_scale"] ** (max(1, tier) - 1) if level < 3 else None,
            "blessings": [{"id": key, **spec, "selected": key in chosen, "annual_cost": round(upkeep(game, key), 3)} for key, spec in config["blessings"].items()],
            "upkeep": round(sum(upkeep(game, key) for key in chosen), 3), "permissions": deps._buddhist_permissions(game),
            "techniques": [{"id": row.id, "name": row.name, "level": row.level} for row in player.known_techniques],
            "attendance": audience, "risk": "低" if burden < 50 else "中" if burden < 150 else "高" if burden < 400 else "极高",
            "assembly": copy.deepcopy(state["assembly"]), "can_assemble": state["dharma_karma"] >= -25 and not state["assembly"],
            "history": copy.deepcopy(state["history"][-8:]),
            "route": "人界 → 灵界 → 仙界" if buddhist_modifier(player, "ascension_destination") != "hell" and player.world not in {"hell", "reincarnation"} else "人界 → 地狱界 → 轮回界"}


def assert_buddhist_operation_allowed(deps: BuddhistGuardDependencies, game_id, operation):
    game = deps._load(game_id)
    session = game.buddhist_state.get("assembly")
    # A disabled DLC may have allowed travel; returning must remain possible after re-enabling.
    at_assembly = session and (session["world"], session["location"]) == (scope_key(game), site_key(game))
    if buddhist_active(game) and at_assembly and operation not in {
        "buddhist-action", "choice", "use-item", "settings", "setting", "world-news-debug", "merchant-preview"}:
        raise ValueError("法会尚未结束，请先继续法会或散会")


def _buddhist_record(game, text):
    game.buddhist_state["history"].append({"age": game.player.age, "text": text})
    game.buddhist_state["history"] = game.buddhist_state["history"][-50:]
    game.history.append(HistoryRecord("SYS_BUDDHIST", 1, game.player.age, "诸法无我", None, "resolved", text, {}, ["buddhist", f"world:{game.player.world}"]))


class BuddhistSystemMixin:
    def _ensure_buddhist_state(self, game):
        return _ensure_buddhist_state(game)

    def _advance_buddhist_society_year(self, game):
        return _advance_buddhist_society_year(game)

    def _advance_buddhist_year(self, game):
        from .character.wiring import bind_buddhist_state
        return _advance_buddhist_year(bind_buddhist_state(self), game)

    def _buddhist_permissions(self, game):
        return _buddhist_permissions(game)

    def _buddhist_burden(self, game):
        return _buddhist_burden(game)

    def _public_buddhist(self, game):
        from .character.wiring import bind_buddhist_state
        return _public_buddhist(bind_buddhist_state(self), game)

    def assert_buddhist_operation_allowed(self, game_id, operation):
        from .character.wiring import bind_buddhist_guard
        return assert_buddhist_operation_allowed(bind_buddhist_guard(self), game_id, operation)

    def _buddhist_record(self, game, text):
        return _buddhist_record(game, text)
