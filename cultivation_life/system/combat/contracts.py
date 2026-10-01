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


EFFECT_KINDS = frozenset({'strike', 'suppress', 'seal', 'restrict', 'isolate',
                          'restore_body', 'restore_spirit', 'restore_field'})
RESTRICTIONS = frozenset({'artifact', 'technique', 'supply', 'support', 'communication', 'voisinage', 'ordinary'})


@dataclass(frozen=True)
class VoisinageEffect:
    """Finite declarative action, never executable content."""
    kind: str
    cost: float
    power: float = .25
    target: str = 'enemy'
    restriction: str | None = None
    defense: str = 'bypass'
    tier: int = 2

    def __post_init__(self):
        if self.kind not in EFFECT_KINDS or self.target not in {'enemy', 'self', 'ally'}:
            raise ValueError('Unknown voisinage effect or target')
        if self.kind.startswith('restore_') != (self.target != 'enemy'):
            raise ValueError('Restoration requires a friendly target')
        if self.defense not in {'bypass', 'ward'} or type(self.tier) is not int or self.tier < 1:
            raise ValueError('Invalid effect defense')
        if number(self.cost, 'effect cost') < 0 or number(self.power, 'effect power') > 1:
            raise ValueError('Invalid effect cost or power')
        if self.kind in {'restrict', 'isolate'}:
            if self.restriction not in RESTRICTIONS:
                raise ValueError('An interdiction requires an explicit restriction')
        elif self.restriction is not None:
            raise ValueError('Only interdictions accept restrictions')


@dataclass(frozen=True)
class Intervention:
    kind: str
    effects: tuple[str, ...]
    cost: float = 0
    strength: float = 1
    source: str = 'innate'

    def __post_init__(self):
        object.__setattr__(self, 'effects', tuple(self.effects))
        if self.kind not in {'resist', 'escape', 'shelter', 'disrupt'}:
            raise ValueError('Unknown intervention')
        if not self.effects or set(self.effects) - (EFFECT_KINDS | {'execute'}):
            raise ValueError('Interventions must name supported effects')
        if self.source not in {'innate', 'artifact', 'technique'}:
            raise ValueError('Unknown intervention source')
        number(self.cost, 'intervention cost')
        number(self.strength, 'intervention strength')


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
    authority_reference: float = 100.0
    features: tuple[Mapping[str, Any], ...] = ()
    effects: tuple[VoisinageEffect, ...] = ()

    def actions(self) -> tuple[VoisinageEffect, ...]:
        return self.effects or (VoisinageEffect(self.effect, self.effect_cost, self.effect_power),)

    def __post_init__(self) -> None:
        if not self.id or not self.attainment:
            raise ValueError("Voisinage id and attainment are required")
        if self.effect not in EFFECT_KINDS:
            raise ValueError("Unknown voisinage effect")
        object.__setattr__(self, 'effects', tuple(e if isinstance(e, VoisinageEffect) else VoisinageEffect(**e)
                                                for e in self.effects))
        if len(self.effects) > 8:
            raise ValueError('At most eight voisinage effects')
        if any(e.cost <= 0 for e in self.effects):
            raise ValueError('Active voisinage effects require positive costs')
        if not self.effects and self.effect not in {'strike', 'suppress', 'seal'}:
            raise ValueError('New effects require an explicit action definition')
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
        if number(self.authority_reference, 'authority_reference') <= 0:
            raise ValueError('Authority reference must be positive')
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
    technique_tier: int = 1
    artifact_tier: int = 1
    passive_ward_tier: int | None = None
    body_voisinage_resistance: float = 0.0
    interventions: tuple[Intervention, ...] = ()
    semantic_rules: tuple[Mapping[str, Any], ...] = ()


def resolve_source(state, definitions, source: CapabilitySource | None = None, **kwargs):
    if source and source.voisinages:
        state = dict(state or {})
        # A provider's explicit active selection takes precedence over old grants.
        state["voisinage_ids"] = [d.id for d in source.voisinages]
        state["attainments"] = {**state.get("attainments", {}), **source.attainments}
        definitions = {**definitions, **{d.id: d for d in source.voisinages}}
    result = resolve_capabilities(state, definitions, **kwargs)
    if source:
        from dataclasses import replace
        result = replace(result, technique_tier=source.technique_tier, artifact_tier=source.artifact_tier,
                         body_voisinage_resistance=source.body_voisinage_resistance,
                         ward_tier=result.ward_tier if source.passive_ward_tier is None else source.passive_ward_tier,
                         interventions=source.interventions or result.interventions,
                         semantic_rules=source.semantic_rules or result.semantic_rules)
    return result


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
    investment_limit: float | None = None
    technique_tier: int = 1
    artifact_tier: int = 1
    interventions: tuple[Intervention, ...] = ()
    body_voisinage_resistance: float = 0.0
    semantic_rules: tuple[Mapping[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if self.semantic_rules:
            from ...combat_semantics import parse_rules
            object.__setattr__(self, 'semantic_rules', parse_rules(self.semantic_rules))
        if number(self.body_voisinage_resistance, 'body voisinage resistance') > .1:
            raise ValueError('Body voisinage resistance cannot exceed ten percent')
        for key in ("capacity", "current", "attack_cost", "ward_cost", "investment"):
            number(getattr(self, key), key)
        if self.current > self.capacity:
            raise ValueError("Resource current exceeds capacity")
        if self.investment_limit is not None:
            number(self.investment_limit, "investment_limit")
        if self.usable_capacity is not None:
            number(self.usable_capacity, "usable_capacity")
            if self.usable_capacity > self.capacity or self.current > self.usable_capacity:
                raise ValueError("Resource exceeds usable capacity")
        if any(type(v) is not int or v < 1 for v in (self.force_tier, self.ward_tier, self.resource_tier,
                                                    self.technique_tier, self.artifact_tier)):
            raise ValueError("Power tiers must be positive integers")
        object.__setattr__(self, 'interventions', tuple(i if isinstance(i, Intervention) else Intervention(**i)
                                                      for i in self.interventions))
        # Up to eight equipment responses plus eight scene-local responses.
        if len(self.interventions) > 16:
            raise ValueError('At most sixteen resolved interventions')
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
    cultivation_rank: int = -1
    body_integrity: float = 1.0

    def __post_init__(self) -> None:
        number(self.power, "combatant power")
        number(self.integrity, "combatant integrity")
        number(self.body_integrity, 'body integrity')
        if self.body_integrity > 1:
            raise ValueError('Body integrity exceeds maximum')
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
    morale_loss: dict[str, float] = field(default_factory=dict)
    stat_factors: dict[str, dict[str, float]] = field(default_factory=dict)
    primary_restore: float = 0.0
    blocked_actions: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def ordinary(self) -> bool:
        return self.ordinary_player or self.ordinary_enemy


@dataclass(frozen=True)
class VoisinageSeal:
    """An explicitly authored, permanent battle-local field cutoff."""
    owner: str
    first_round: int
    message: str

    def __post_init__(self) -> None:
        if not self.owner or type(self.first_round) is not int or self.first_round < 1 or not self.message:
            raise ValueError("Invalid voisinage seal schedule")


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
                    player_mp: float, enemy_mp: float, player_morale=None, enemy_morale=None) -> PhaseRound: ...
    def ordinary_damage(self, dealt: float, received: float) -> tuple[float, float]: ...
    def sync_resources(self, *, player_mp: float, enemy_mp: float) -> None: ...
    def semantic_ordinary_start(self) -> dict[str, dict[str, float]]: ...
    def semantic_initiative(self, player_first: bool) -> dict[str, dict[str, float]]: ...
    def semantic_environment(self, natural: str, artificial: list[str]) -> None: ...
    def semantic_context(self, *, player_mp, enemy_mp, player_morale, enemy_morale) -> None: ...
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
    def set_objectives(self, player: str, enemy: str) -> None: ...


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
        interventions=tuple(state.get('interventions', ())),
        semantic_rules=tuple(state.get('semantic_rules', ())),
    )
