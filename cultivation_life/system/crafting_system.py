from __future__ import annotations
from functools import cached_property
from .crafting.wiring import bind_crafting
from .crafting import presentation as crafting_presentation
from .crafting import materials as crafting_materials
from .crafting import market as crafting_market
from .crafting import forging as crafting_forging
from .crafting import preview as crafting_preview
from .crafting import artifacts as crafting_artifacts

import copy
import hashlib
import math
import random
import uuid
from typing import Any

from ..content_registry import CONTENT_DOCUMENTS, REALMS
from ..models import GameState, HistoryRecord, Item, Player
from ..rules import add_item, expected_combat_power, max_hp, max_mp, remove_item
from ..runtime import decode_rng, encode_rng, now_iso

from .crafted_artifact_rules import (
    STAT_NAMES as STAT_NAMES,
    tianji_world_combat_power_cap as tianji_world_combat_power_cap,
    effective_tianji_combat_power as effective_tianji_combat_power,
    active_crafted_artifacts as active_crafted_artifacts,
    crafted_artifact_bonuses as crafted_artifact_bonuses,
    effective_artifact_combat_bonus as effective_artifact_combat_bonus,
    crafted_combat_effects as crafted_combat_effects,
)


MOLD_COMBAT_STAT_NAMES = {
    "might": "威能", "guard": "防护", "mobility": "身法",
    "sense": "神识", "sustain": "续航", "breach": "破法",
}


def crafting_config() -> dict[str, Any]:
    return CONTENT_DOCUMENTS.get("crafting.json", {})


def crafted_artifact_description(artifact: dict[str, Any]) -> str:
    preserved = str(artifact.get("description", "")).strip()
    if preserved:
        return preserved
    rule = str(artifact.get("mold_rule_description", "")).strip()
    material_lines = [
        str(row.get("description", "")).strip()
        for row in artifact.get("material_effects", [])
        if isinstance(row, dict) and str(row.get("description", "")).strip()
    ]
    pieces = [
        f"{artifact.get('quality_name', '')}{artifact.get('mold_name', '组合式法宝')}",
        f"常驻属性：{artifact_summary(artifact)}",
    ]
    if rule:
        pieces.append(f"胎模器纹：{rule}")
    if material_lines:
        pieces.append("材料器纹：" + "；".join(material_lines))
    pieces.append(
        f"由{artifact.get('creator_name', '无名器师')}炼于纪年 {artifact.get('created_year', '?')}，"
        f"锚定价值 {int(artifact.get('anchor_value', 1)):,} 灵石"
    )
    return "。".join(pieces) + "。"


def store_crafted_artifact(player: Player, artifact: dict[str, Any]) -> None:
    artifact_id = str(artifact.get("id", ""))
    if not artifact_id:
        raise ValueError("炼器法宝缺少唯一实例 ID")
    artifact["description"] = crafted_artifact_description(artifact)
    if not any(str(row.get("id")) == artifact_id for row in player.crafted_artifacts):
        player.crafted_artifacts.append(artifact)
    if not any(item.crafted_artifact_id == artifact_id for item in player.inventory):
        player.inventory.append(Item(
            id=artifact_id,
            name=str(artifact.get("name", "无名法宝")),
            quantity=1,
            crafted_artifact_id=artifact_id,
            description=str(artifact["description"]),
            tags=["artifact", "equipment", "crafted_artifact"],
        ))


def remove_crafted_artifact(player: Player, artifact: dict[str, Any]) -> None:
    artifact_id = str(artifact.get("id", ""))
    player.crafted_artifacts = [
        row for row in player.crafted_artifacts if str(row.get("id", "")) != artifact_id
    ]
    player.equipped_crafted_artifact_ids = [
        value for value in player.equipped_crafted_artifact_ids if value != artifact_id
    ]
    player.inventory = [
        item for item in player.inventory if item.crafted_artifact_id != artifact_id
    ]


def crafting_material_definitions() -> dict[str, dict[str, Any]]:
    return {str(row["id"]): row for row in crafting_config().get("materials", [])}


def make_crafting_material_instance(
    definition: dict[str, Any], rng: random.Random, *, source: str, origin_world: str,
) -> dict[str, Any]:
    condition = max(0.65, min(1.25, rng.triangular(0.65, 1.25, 1.0)))
    state = "灵韵天成" if condition >= 1.15 else "品相上佳" if condition >= 1.05 else "保存完好" if condition >= .9 else "略有损耗"
    base_value = max(1, int(definition["base_material_value"]))
    return {
        "id": f"material-{uuid.uuid4().hex}", "material_id": str(definition["id"]),
        "name": str(definition["name"]), "quality": round(condition, 4), "state": state,
        "source": source, "origin_world": origin_world,
        "material_value": max(1, round(base_value * condition)),
        "acquired_tier": int(definition.get("tier", 1)),
    }


def _crafting_rules() -> dict[str, Any]:
    return crafting_config().get("settings", {})


def _crafting_molds() -> dict[str, dict[str, Any]]:
    return {str(row["id"]): row for row in crafting_config().get("molds", [])}


def _crafting_material_defs() -> dict[str, dict[str, Any]]:
    return crafting_material_definitions()


def _crafting_plant_defs() -> dict[str, dict[str, Any]]:
    return {str(row["plant_id"]): row for row in crafting_config().get("spirit_plants", [])}


def _quality_probabilities(refining_level: int, average_quality: float) -> dict[str, float]:
    tiers = ("damaged", "rough", "normal", "excellent", "refined", "epic", "legendary")
    base = (8.0, 20.0, 50.0, 14.0, 6.0, 1.7, .3)
    shift = min(12.0, max(-4.0, refining_level * .75 + (average_quality - 1.0) * 10.0))
    weights = [weight * math.exp(shift * (index - 2) * .16) for index, weight in enumerate(base)]
    total = sum(weights)
    return {tier: round(weight / total, 6) for tier, weight in zip(tiers, weights)}


def _weighted_choice(rng: random.Random, probabilities: dict[str, float]) -> str:
    roll = rng.random()
    elapsed = 0.0
    for key, probability in probabilities.items():
        elapsed += probability
        if roll <= elapsed:
            return key
    return next(reversed(probabilities))


def _resolve_mold_rule(
    player: Player, mold: dict[str, Any], selected: list[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    """Freeze the generic mold's one random base stat for this recipe.

    Preview and forging may be called separately, so this cannot consume the
    save RNG.  The next crafting sequence and the four concrete material
    instances form a stable roll; changing any material legitimately rerolls
    the unshaped mold.
    """
    resolved = copy.deepcopy(mold)
    rule = resolved.get("rule", {})
    candidates = list(map(str, rule.get("random_base_stats", [])))
    if not candidates:
        return resolved
    key = ":".join([
        player.name, str(player.crafting_sequence + 1),
        *(str(material.get("id", "")) for _, material in selected),
    ])
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    stat = candidates[int.from_bytes(digest[:4], "big") % len(candidates)]
    multiplier = float(rule.get("random_multiplier", 1.08))
    stat_name = MOLD_COMBAT_STAT_NAMES.get(stat, stat)
    rule["name"] = f"无定器相·{stat_name}"
    rule["description"] = f"此炉器机定形为{stat_name}，战斗开始时{stat_name}提高 {(multiplier - 1):.0%}。"
    rule["combat_effect"] = {"player_stat_multipliers": {stat: multiplier}}
    rule["resolved_random_stat"] = stat
    return resolved


def bind_crafting_compatibility(host):
    return bind_crafting(
        host,
        artifact_summary=lambda *args, **kwargs: artifact_summary(*args, **kwargs),
        crafting_config=lambda *args, **kwargs: crafting_config(*args, **kwargs),
        make_crafting_material_instance=lambda *args, **kwargs: make_crafting_material_instance(*args, **kwargs),
        name_or_artifact=lambda *args, **kwargs: name_or_artifact(*args, **kwargs),
        remove_crafted_artifact=lambda *args, **kwargs: remove_crafted_artifact(*args, **kwargs),
        store_crafted_artifact=lambda *args, **kwargs: store_crafted_artifact(*args, **kwargs),
    )


class CraftingSystemMixin:
    @cached_property
    def _crafting_dependencies(self):
        return bind_crafting_compatibility(self)

    @staticmethod
    def _crafting_rules() -> dict[str, Any]:
        return _crafting_rules()

    @staticmethod
    def _crafting_molds() -> dict[str, dict[str, Any]]:
        return _crafting_molds()

    @staticmethod
    def _crafting_material_defs() -> dict[str, dict[str, Any]]:
        return _crafting_material_defs()

    @staticmethod
    def _crafting_plant_defs() -> dict[str, dict[str, Any]]:
        return _crafting_plant_defs()

    def _append_crafting_market_offers(
        self, game: GameState, rng: random.Random, offers: list[dict[str, Any]], *,
        tier: int, market_name: str, location_id: str,
    ) -> None:
        # New crafting stock must not move the story/combat RNG stream.  Its
        # condition remains deterministic for the same save, place and year.
        return crafting_market._append_crafting_market_offers(self._crafting_dependencies.market, game, rng, offers, tier=tier, market_name=market_name, location_id=location_id)

    def _buy_crafting_material_offer(self, game: GameState, offer: dict[str, Any], price: int) -> str:
        return crafting_market._buy_crafting_material_offer(self._crafting_dependencies.market, game, offer, price)

    def _crafting_material_candidates(self, player: Player) -> list[dict[str, Any]]:
        return crafting_materials._crafting_material_candidates(self._crafting_dependencies.materials, player)

    @staticmethod
    def _quality_probabilities(refining_level: int, average_quality: float) -> dict[str, float]:
        return _quality_probabilities(refining_level, average_quality)

    @staticmethod
    def _weighted_choice(rng: random.Random, probabilities: dict[str, float]) -> str:
        return _weighted_choice(rng, probabilities)

    def _resolve_crafting_selection(self, player: Player, payload: dict[str, Any]) -> tuple[dict[str, Any], list[tuple[str, dict[str, Any]]]]:
        return crafting_materials._resolve_crafting_selection(self._crafting_dependencies.materials, player, payload)

    @staticmethod
    def _resolve_mold_rule(
        player: Player, mold: dict[str, Any], selected: list[tuple[str, dict[str, Any]]],
    ) -> dict[str, Any]:
        return _resolve_mold_rule(player, mold, selected)

    def _crafting_preview(self, player: Player, payload: dict[str, Any]) -> dict[str, Any]:
        return crafting_preview._crafting_preview(self._crafting_dependencies.preview, player, payload)

    def preview_crafting(self, game_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return crafting_preview.preview_crafting(self._crafting_dependencies.preview, game_id, payload)

    def forge_crafted_artifact(self, game_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return crafting_forging.forge_crafted_artifact(self._crafting_dependencies.forging, game_id, payload)

    def save_crafting_blueprint(self, game_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        return crafting_forging.save_crafting_blueprint(self._crafting_dependencies.forging, game_id, payload)

    def crafted_artifact_action(self, game_id: str, artifact_id: str, action: str, start_price: int = 0) -> dict[str, Any]:
        return crafting_artifacts.crafted_artifact_action(self._crafting_dependencies.artifacts, game_id, artifact_id, action, start_price)

    def _consign_crafted_artifact(self, game: GameState, artifact: dict[str, Any], start_price: int) -> None:
        return crafting_artifacts._consign_crafted_artifact(self._crafting_dependencies.artifacts, game, artifact, start_price)

    def _make_crafted_auction_lot(self, game: GameState, rng: random.Random, consignment: dict[str, Any], suffix: str) -> dict[str, Any]:
        return crafting_artifacts._make_crafted_auction_lot(self._crafting_dependencies.artifacts, game, rng, consignment, suffix)

    def _public_crafting_system(self, game: GameState) -> dict[str, Any]:
        return crafting_presentation._public_crafting_system(self._crafting_dependencies.presentation, game)


def artifact_summary(artifact: dict[str, Any]) -> str:
    stats = artifact.get("actual_stats", {})
    pieces = []
    for key, value in stats.items():
        number = float(value)
        if not number:
            continue
        shown = f"{number:.1%}" if key.endswith("efficiency") or key.endswith("reduction") or key == "breakthrough_bonus" else f"{number:,.0f}"
        pieces.append(f"{STAT_NAMES.get(key, key)} +{shown}")
    return "、".join(pieces) or "无常驻数值"


def name_or_artifact(artifact: dict[str, Any]) -> str:
    return f"{artifact.get('quality_name', '')}法宝“{artifact.get('name', '无名法宝')}”"
