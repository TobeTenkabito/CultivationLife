"""Explicit, data-only boundary between cultivation and combat."""
from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Mapping, Protocol


def number(value: Any, name: str, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be numeric, not a boolean")
    result = float(value)
    if not isfinite(result) or result < minimum:
        raise ValueError(f"{name} must be finite and >= {minimum}")
    return result


@dataclass(frozen=True)
class VoisinageDefinition:
    id: str
    name: str
    attainment: str
    required_level: float
    strength: float
    opening_cost: float
    upkeep_cost: float
    effect: str
    effect_cost: float
    effect_power: float = 0.25
    strength_per_level: float = 0.0
    max_investment: float = 0.0
    extra_target_cost: float = 0.0
    max_targets: int = 1
    stability: float | None = None
    incursion: float | None = None
    authority: float | None = None
    features: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if not self.id or not self.attainment:
            raise ValueError("Voisinage id and attainment are required")
        if self.effect not in {"strike", "suppress", "seal"}:
            raise ValueError("Unknown voisinage effect")
        for key in ("required_level", "strength", "opening_cost", "upkeep_cost",
                    "effect_cost", "effect_power", "strength_per_level",
                    "max_investment", "extra_target_cost"):
            number(getattr(self, key), key)
        if self.strength <= 0 or self.upkeep_cost <= 0 or self.effect_cost <= 0:
            raise ValueError("Voisinages require positive strength, upkeep and effect costs")
        if type(self.max_targets) is not int or self.max_targets < 1:
            raise ValueError("Voisinage max_targets must be a positive integer")
        if self.effect_power > 1:
            raise ValueError("Voisinage effect_power must be <= 1")
        for key in ("stability", "incursion", "authority"):
            if getattr(self, key) is not None:
                number(getattr(self, key), key)
        if len(self.features) > 3:
            raise ValueError("A voisinage supports at most three operational features")
        seen = set()
        for feature in self.features:
            kind = feature.get("kind")
            if kind not in {"fortify", "opening", "retaliate", "sacrifice", "frugal", "shelter", "execution"} or kind in seen:
                raise ValueError("Invalid or duplicate voisinage feature")
            seen.add(kind)
            if number(feature.get("value", 0), "feature value") > .5:
                raise ValueError("Voisinage feature value must be <= .5")


@dataclass(frozen=True)
class CapabilitySource:
    """Optional cultivation-provider output. The battle does not know its origin."""
    voisinages: tuple[VoisinageDefinition, ...] = ()
    attainments: Mapping[str, float] = field(default_factory=dict)


def resolve_source(state, definitions, source: CapabilitySource | None = None, **kwargs):
    if source and source.voisinages:
        state = dict(state or {})
        # A provider's explicit active selection takes precedence over old grants.
        state["voisinage_ids"] = [d.id for d in source.voisinages]
        state["attainments"] = {**state.get("attainments", {}), **source.attainments}
        definitions = {**definitions, **{d.id: d for d in source.voisinages}}
    return resolve_capabilities(state, definitions, **kwargs)


@dataclass(frozen=True)
class CombatCapabilities:
    """A resolved snapshot, never a second authoritative cultivation record."""
    capacity: float = 0.0
    current: float = 0.0
    force_tier: int = 1
    ward_tier: int = 1
    attack_cost: float = 0.0
    ward_cost: float = 0.0
    voisinages: tuple[VoisinageDefinition, ...] = ()
    attainments: Mapping[str, float] = field(default_factory=dict)
    stance: str = "press"
    investment: float = 0.0
    protect_ids: tuple[str, ...] = ()
    target_ids: tuple[str, ...] = ()
    # Explicit reach is optional for the current abstract, close-range battlefield.
    reachable_ids: tuple[str, ...] | None = None
    sealed: bool = False
    # Existing converted player MP can back the pool without storing it twice.
    resource_link: str = "independent"
    resource_tier: int = 1
    usable_capacity: float | None = None

    def __post_init__(self) -> None:
        for key in ("capacity", "current", "attack_cost", "ward_cost", "investment"):
            number(getattr(self, key), key)
        if self.current > self.capacity:
            raise ValueError("Resource current exceeds capacity")
        if self.usable_capacity is not None:
            number(self.usable_capacity, "usable_capacity")
            if self.usable_capacity > self.capacity or self.current > self.usable_capacity:
                raise ValueError("Resource exceeds usable capacity")
        if any(type(v) is not int or v < 1 for v in (self.force_tier, self.ward_tier, self.resource_tier)):
            raise ValueError("Power tiers must be positive integers")
        if self.stance not in {"off", "guard", "protect", "press"}:
            raise ValueError("Unknown voisinage stance")
        if self.resource_link not in {"independent", "legacy_mp"}:
            raise ValueError("Unknown resource link")


def voisinage_definitions(config: Mapping[str, Any]) -> dict[str, VoisinageDefinition]:
    definitions: dict[str, VoisinageDefinition] = {}
    for row in config.get("voisinages", config.get("domains", [])):
        definition = VoisinageDefinition(**row)
        if definition.id in definitions:
            raise ValueError(f"Duplicate voisinage definition: {definition.id}")
        definitions[definition.id] = definition
    number(config.get("contest_ratio", 1.25), "contest_ratio", minimum=1.0)
    return definitions


@dataclass(frozen=True)
class Combatant:
    id: str
    name: str
    side: str
    power: float
    capabilities: CombatCapabilities = field(default_factory=CombatCapabilities)
    integrity: float = 1.0

    def __post_init__(self) -> None:
        number(self.power, "combatant power")
        number(self.integrity, "combatant integrity")
        if not self.id or self.integrity > 1:
            raise ValueError("Invalid combatant identity or integrity")


@dataclass
class PhaseRound:
    round_no: int
    ordinary_player: bool = True
    ordinary_enemy: bool = True
    player_loss: float = 0.0
    enemy_loss: float = 0.0
    primary_loss: float = 0.0
    events: list[str] = field(default_factory=list)
    relations: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def ordinary(self) -> bool:
        return self.ordinary_player or self.ordinary_enemy


@dataclass(frozen=True)
class ResourceSupply:
    """Explicit high-tier supply, never inferred from a world's name."""
    owner: str
    amount: float
    source_id: str | None = None
    first_round: int = 1
    last_round: int | None = None

    def __post_init__(self) -> None:
        number(self.amount, "supply amount")
        if self.first_round < 1 or (self.last_round is not None and self.last_round < self.first_round):
            raise ValueError("Invalid supply schedule")


class CombatPhases(Protocol):
    """The conventional engine depends only on this round-level contract."""
    primary_ordinary_loss: float

    @property
    def enabled(self) -> bool: ...

    def begin_round(self, round_no: int, *, player_condition: float, enemy_condition: float,
                    player_mp: float, enemy_mp: float) -> PhaseRound: ...
    def ordinary_damage(self, dealt: float, received: float) -> tuple[float, float]: ...
    def mp_ratio(self, side: str, fallback: float) -> float: ...
    def finish_round(self, *, player_mp: float, enemy_mp: float) -> None: ...
    def ordinary_loss(self, side: str) -> float: ...
    def restore_ordinary(self, side: str, amount: float) -> None: ...
    def revive_primary(self, vitality: float) -> None: ...
    def verdict(self) -> str | None: ...
    def primary_suppressed(self) -> bool: ...
    def primary_dead(self) -> bool: ...
    def enemy_killed(self) -> bool: ...
    def enemy_suppressed(self) -> bool: ...
    def report(self) -> dict[str, Any]: ...
    def updates(self) -> list[dict[str, Any]]: ...


def resolve_capabilities(
    state: Mapping[str, Any] | None,
    definitions: Mapping[str, VoisinageDefinition],
    *, linked_current: float = 0.0, linked_capacity: float = 0.0,
) -> CombatCapabilities:
    """Neutral attainment keys are supplied by future cultivation providers.

    No realm/world automatically grants a voisinage. Conversion only determines
    which resource tier is available; it never implies attainment mastery.
    """
    if state is None:
        return CombatCapabilities()
    if not isinstance(state, Mapping):
        raise ValueError("transcendence must be an object")
    if state.get("version", 1) != 1:
        raise ValueError("Unsupported transcendence state version")
    conversion = number(state.get("conversion", 0.0), "conversion")
    if conversion > 1:
        raise ValueError("conversion must be <= 1")
    linked = state.get("resource_link", "independent") == "legacy_mp"
    capacity = linked_capacity if linked else number(state.get("capacity", 0), "capacity")
    current = linked_current if linked else number(state.get("current", 0), "current")
    attainments = {str(k): number(v, "attainment") for k, v in state.get("attainments", {}).items()}
    granted = tuple(definitions[key] for key in state.get("voisinage_ids", state.get("domain_ids", [])) if key in definitions
                    and attainments.get(definitions[key].attainment, 0) >= definitions[key].required_level)
    plan = state.get("plan", {})
    return CombatCapabilities(
        capacity=capacity, current=min(current, capacity * conversion),
        force_tier=state.get("force_tier", 1), ward_tier=state.get("ward_tier", 1),
        attack_cost=number(state.get("attack_cost", 0), "attack_cost"),
        ward_cost=number(state.get("ward_cost", 0), "ward_cost"),
        voisinages=granted, attainments=attainments,
        stance=str(plan.get("stance", "press")), investment=number(plan.get("investment", 0), "investment"),
        protect_ids=tuple(map(str, plan.get("protect_ids", []))),
        target_ids=tuple(map(str, plan.get("target_ids", []))),
        reachable_ids=(tuple(map(str, plan["reachable_ids"])) if "reachable_ids" in plan else None),
        sealed=bool(state.get("sealed", False)),
        resource_link="legacy_mp" if linked else "independent",
        resource_tier=2 if conversion > 0 else 1,
        usable_capacity=capacity * conversion,
    )
