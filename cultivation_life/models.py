from __future__ import annotations

import copy
from dataclasses import asdict, dataclass, field
from typing import Any

from .version import BASE_GAME_VERSION


@dataclass(frozen=True)
class RealmDef:
    id: str
    name: str
    layers: int
    base_power: float
    opportunity_base: int
    lifespan: tuple[int, int] | None
    kill_threshold: float


@dataclass
class Item:
    id: str
    name: str
    quantity: int = 1
    combat_bonus: float = 0.0
    hp_bonus: int = 0
    mp_bonus: int = 0
    opportunity_bonus: float = 0.0
    root_grant: str | None = None
    breakthrough_bonus: float = 0.0
    breakthrough_scope: str | None = None
    trial_restore_hp: float = 0.0
    trial_restore_mp: float = 0.0
    tribulation_damage_reduction: float = 0.0
    passive_breakthrough_bonus: float = 0.0
    passive_breakthrough_max_realm: int | None = None
    conception_bonus: float = 0.0
    plant_id: str | None = None
    plant_years: int | None = None
    plant_quality: float | None = None
    plant_kind: str | None = None
    plant_value: int | None = None
    transformation_form_id: str | None = None
    transformation_source: str | None = None
    transformation_purity: float = 0.0
    description: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Item:
        return cls(**value)


@dataclass
class Technique:
    id: str = "MAIN_QI_GUIDE"
    path: str = "dao"
    name: str = "引气诀"
    element: str = "neutral"
    grade: int = 1
    level: int = 1
    opportunity_bonus: float = 0.0
    hp_bonus: float = 0.0
    mp_bonus: float = 0.0
    combat_bonus: float = 0.0
    karma_multiplier: float = 1.0
    category: str = "spiritual"
    body_breakthrough_bonus: float = 0.0
    body_bonus_max_layer: int | None = None
    sources: dict[str, float] = field(default_factory=dict)
    combat_requirements: dict[str, Any] = field(default_factory=dict)
    divine_sense_bonus: float = 0.0
    transformation_capacity: int = 0
    transformation_space: int = 0
    initial_transformations: list[str] = field(default_factory=list)
    requires_immortal_power: bool = False
    immortal_power_cost: float = 0.0
    required_body_training: int = 0

    def __post_init__(self) -> None:
        # 旧存档与未显式标注的内容按道统补齐先天“源”；一旦写入存档，
        # sources 就成为功法自身的固定数据，不随角色所在界面改变。
        if not self.sources:
            source = {
                "demonic": "demon",
                "monster": "monster",
                "ghost": "yin",
            }.get(self.path, "spirit")
            self.sources = {source: 1.0}
        else:
            self.sources = {str(source): float(weight) for source, weight in self.sources.items()}
        if not self.combat_requirements:
            threshold = {1: 0, 2: 3, 3: 5, 4: 8, 5: 12, 6: 17, 7: 23, 8: 30}.get(self.grade, 30)
            leaves = [
                {"source": {"id": source, "op": ">=", "level": threshold}}
                for source in self.sources
            ]
            self.combat_requirements = leaves[0] if len(leaves) == 1 else {"any": leaves}


@dataclass(frozen=True)
class TransformationForm:
    id: str
    name: str
    description: str
    stat_multipliers: dict[str, float]
    realm_index: int = 8
    layer: int = 1
    traits: tuple[str, ...] = ()
    trait_descriptions: tuple[str, ...] = ()
    trait_purity_requirements: tuple[float, ...] = ()
    incompatible_with: tuple[str, ...] = ()


@dataclass
class SectNpc:
    id: str
    name: str
    title: str
    realm_index: int
    layer: int
    age: int
    lifespan: int | None
    spirit_root: str = ""
    cultivation_progress: float = 0.0
    path: str = "dao"
    race: str = "human"
    world: str = "human"
    departed_age: int | None = None
    departure_reason: str | None = None
    alive: bool = True
    death_reason: str | None = None
    affinity: float | None = None
    treasure_item_id: str | None = None
    treasure_looted: bool = False
    combat_factor: float = 1.0
    faction_id: str | None = None
    next_tribulation_age: int | None = None
    tribulation_count: int = 0
    tribulation_power: float | None = None
    notorious: bool = False
    notoriety: int = 0
    encountered_player: bool = False
    wounds: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> SectNpc:
        return cls(**value)


@dataclass
class SectState:
    id: str
    name: str
    world: str = "human"
    npcs: list[SectNpc] = field(default_factory=list)
    description: str = ""
    path: str = "dao"
    extinct: bool = False
    founded_by_player: bool = False
    founder_player_id: str | None = None
    pressure: int = 0
    kind: str = "sect"
    founded_by_npc: bool = False
    founder_npc_id: str | None = None
    allegiance_race: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "name": self.name, "world": self.world,
            "npcs": [npc.to_dict() for npc in self.npcs],
            "description": self.description, "path": self.path, "extinct": self.extinct,
            "founded_by_player": self.founded_by_player, "founder_player_id": self.founder_player_id,
            "pressure": self.pressure,
            "kind": self.kind, "founded_by_npc": self.founded_by_npc,
            "founder_npc_id": self.founder_npc_id,
            "allegiance_race": self.allegiance_race,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> SectState:
        return cls(
            id=value["id"],
            name=value["name"],
            world=value.get("world", "human"),
            npcs=[SectNpc.from_dict(npc) for npc in value.get("npcs", [])],
            description=value.get("description", ""),
            path=value.get("path", "dao"),
            extinct=bool(value.get("extinct", False)),
            founded_by_player=bool(value.get("founded_by_player", False)),
            founder_player_id=value.get("founder_player_id"),
            pressure=int(value.get("pressure", 0)),
            kind=str(value.get("kind", "sect")),
            founded_by_npc=bool(value.get("founded_by_npc", False)),
            founder_npc_id=value.get("founder_npc_id"),
            allegiance_race=value.get("allegiance_race"),
        )


@dataclass
class Player:
    name: str
    spirit_root: str
    age: int = 16
    realm_index: int = 0
    layer: int = 1
    lifespan: int | None = 90
    monster_lifespan_scaled: bool = False
    opportunity: float = 0.0
    qi_experience: dict[str, float] = field(default_factory=lambda: {
        "spirit": 0.0, "demon": 0.0, "monster": 0.0, "yin": 0.0,
    })
    art_experience: dict[str, float] = field(default_factory=lambda: {
        "alchemy": 0.0, "refining": 0.0, "formation": 0.0,
        "talisman": 0.0, "spirit_control": 0.0,
    })
    spirit_field: dict[str, Any] = field(default_factory=lambda: {
        "reclaimed_qing": 0, "plots": [], "sequence": 0,
    })
    karma: float = 0.0
    sha_qi: int = 0
    heart_demon: float = 0.0
    hp: float = 100.0
    mp: float = 40.0
    path: str = "dao"
    technique: Technique | None = None
    support_technique: Technique | None = None
    combat_techniques: list[Technique] = field(default_factory=list)
    known_techniques: list[Technique] = field(default_factory=list)
    additional_roots: list[str] = field(default_factory=list)
    inventory: list[Item] = field(default_factory=list)
    alive: bool = True
    death_reason: str | None = None
    body_training: int = 0
    body_progress: float = 0.0
    body_technique: Technique | None = None
    divine_sense_technique: Technique | None = None
    transformation_technique: Technique | None = None
    known_transformations: list[str] = field(default_factory=list)
    transformation_mastery: dict[str, dict[str, Any]] = field(default_factory=dict)
    transformation_loadouts: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    divine_sense_rank: int = 0
    divine_sense_experience: float = 0.0
    prisoners: list[dict[str, Any]] = field(default_factory=list)
    puppets: list[dict[str, Any]] = field(default_factory=list)
    foreign_souls: list[dict[str, Any]] = field(default_factory=list)
    devouring_breakthrough_bonus: float = 0.0
    awaiting_body_breakthrough: bool = False
    body_breakthrough_pity: dict[str, int] = field(default_factory=dict)
    acquired_root: bool = False
    born_rootless: bool = False
    mortal_aspiration: str | None = None
    spouse: bool = False
    children: int = 0
    official_rank: int = 0
    military_merit: int = 0
    jianghu_reputation: int = 0
    awaiting_ascension: bool = False
    awaiting_major_breakthrough: bool = False
    awaiting_minor_breakthrough: bool = False
    active_breakthrough_aids: list[str] = field(default_factory=list)
    next_tribulation_age: int | None = None
    next_thunder_damage_reduction: float = 0.0
    immortal_power_converted: bool = False
    immortal_conversion_stage: int = 0
    immortal_conversion_last_age: int | None = None
    immortal_conversion_checked_units: int = 0
    tribulation_count: int = 0
    tribulation_power: float | None = None
    faction_id: str | None = None
    faction_join_age: int | None = None
    faction_contribution: int = 0
    faction_reward_preference: str | None = None
    faction_hp_bonus: int = 0
    faction_mp_bonus: int = 0
    faction_combat_bonus: float = 0.0
    natal_artifact_hp_bonus: float = 0.0
    natal_artifact_mp_bonus: float = 0.0
    natal_artifact_combat_bonus: float = 0.0
    natal_artifact_opportunity_bonus: float = 0.0
    natal_artifact_tribulation_reduction: float = 0.0
    awaiting_spirit_realm_crossing: bool = False
    last_disciple_dispatch_age: int | None = None
    master: dict[str, Any] | None = None
    disciples: list[dict[str, Any]] = field(default_factory=list)
    dao_friends: list[dict[str, Any]] = field(default_factory=list)
    disciple_requests: list[dict[str, Any]] = field(default_factory=list)
    relationship_attempts: list[str] = field(default_factory=list)
    story_flags: list[str] = field(default_factory=list)
    milestones: dict[str, int] = field(default_factory=dict)
    world: str = "human"
    location_id: str | None = None
    race: str = "human"
    spirit_realm_attempted: bool = False
    fame: float = 0.0
    hostility: dict[str, float] = field(default_factory=dict)
    faction_warnings: list[str] = field(default_factory=list)
    imprisonment: dict[str, Any] | None = None
    party: list[dict[str, Any]] = field(default_factory=list)
    dao_companion: dict[str, Any] | None = None
    joint_companion_breakthrough: dict[str, Any] | None = None
    sealed_cultivation: dict[str, Any] | None = None
    offspring: list[dict[str, Any]] = field(default_factory=list)
    # Consumed by the next valid entwine interaction.  Kept separate from the
    # realm table so medicine can still work when natural conception is zero.
    next_companion_conception_bonus: float = 0.0
    breakthrough_pity: dict[str, int] = field(default_factory=dict)
    joint_spirit_crossing: dict[str, Any] | None = None
    joint_friend_crossing: list[dict[str, Any]] = field(default_factory=list)
    lineage_race: str | None = None
    allegiance_race: str | None = None
    # Political race remains ``race``. These fields describe a monster
    # cultivator's biological lineage and are inert when the DLC is absent.
    monster_species_id: str | None = None
    monster_evolution_id: str | None = None
    monster_evolution_history: list[str] = field(default_factory=list)
    monster_adaptations: list[str] = field(default_factory=list)
    monster_adaptation_progress: dict[str, int] = field(default_factory=dict)
    monster_bloodline_imprints: list[str] = field(default_factory=list)
    # All DLC awakening IDs are recorded here for save/API compatibility.
    # Fixed registry traits resolve directly; generated IDs resolve through
    # monster_generated_bloodline_traits below. Both freeze with the DLC.
    monster_acquired_bloodline_traits: list[str] = field(default_factory=list)
    # V4.2+ complex traits are finite rule snapshots generated once at a major
    # evolution. Legacy fixed-ID pool traits remain in the field above.
    monster_generated_bloodline_traits: list[dict[str, Any]] = field(default_factory=list)
    # Base-game fallback traits are earned only when the bloodline DLC is
    # disabled.  They remain saved but inactive whenever that DLC is enabled.
    monster_general_traits: list[str] = field(default_factory=list)
    # V4 lineage deeds are explicit, auditable counters.  The custom lineage
    # document contains only the finite rule DSL and never executable code.
    monster_lineage_deeds: dict[str, int] = field(default_factory=dict)
    monster_custom_lineage_id: str | None = None
    monster_custom_lineage: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        return result

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> Player:
        data = dict(value)
        saved_qi = data.get("qi_experience", {})
        data["qi_experience"] = {
            source: max(0.0, float(saved_qi.get(source, 0.0)))
            for source in ("spirit", "demon", "monster", "yin")
        }
        saved_arts = data.get("art_experience", {})
        data["art_experience"] = {
            art: max(0.0, float(saved_arts.get(art, 0.0)))
            for art in ("alchemy", "refining", "formation", "talisman", "spirit_control")
        }
        saved_field = data.get("spirit_field", {})
        data["spirit_field"] = {
            "reclaimed_qing": max(0, int(saved_field.get("reclaimed_qing", 0))),
            "plots": list(saved_field.get("plots", [])),
            "sequence": max(0, int(saved_field.get("sequence", 0))),
        }
        data.setdefault("lineage_race", data.get("race", "human"))
        data.setdefault("allegiance_race", data.get("race", "human"))
        data["monster_evolution_history"] = list(dict.fromkeys(map(str, data.get("monster_evolution_history", []))))
        data["monster_adaptations"] = list(dict.fromkeys(map(str, data.get("monster_adaptations", []))))
        data["monster_adaptation_progress"] = {
            str(key): max(0, int(count))
            for key, count in data.get("monster_adaptation_progress", {}).items()
        }
        data["monster_bloodline_imprints"] = list(dict.fromkeys(map(str, data.get("monster_bloodline_imprints", []))))
        data["monster_acquired_bloodline_traits"] = list(dict.fromkeys(
            map(str, data.get("monster_acquired_bloodline_traits", []))
        ))
        data["monster_generated_bloodline_traits"] = [
            copy.deepcopy(row) for row in data.get("monster_generated_bloodline_traits", [])
            if isinstance(row, dict)
        ]
        data["monster_general_traits"] = list(dict.fromkeys(map(str, data.get("monster_general_traits", []))))
        data["monster_lineage_deeds"] = {
            str(key): max(0, int(count))
            for key, count in data.get("monster_lineage_deeds", {}).items()
        } if isinstance(data.get("monster_lineage_deeds", {}), dict) else {}
        saved_lineage = data.get("monster_custom_lineage")
        data["monster_custom_lineage"] = copy.deepcopy(saved_lineage) if isinstance(saved_lineage, dict) else None
        saved_lineage_id = data.get("monster_custom_lineage_id")
        if not saved_lineage_id and isinstance(data["monster_custom_lineage"], dict):
            saved_lineage_id = data["monster_custom_lineage"].get("id")
        data["monster_custom_lineage_id"] = str(saved_lineage_id) if saved_lineage_id else None
        data["next_companion_conception_bonus"] = max(
            0.0, min(0.95, float(data.get("next_companion_conception_bonus", 0.0)))
        )
        technique = data.get("technique")
        data["technique"] = Technique(**technique) if technique else None
        if "path" not in data:
            data["path"] = data["technique"].path if data["technique"] else "dao"
        if "born_rootless" not in data:
            data["born_rootless"] = data.get("spirit_root") == "none"
        support = data.get("support_technique")
        data["support_technique"] = Technique(**support) if support else None
        body = data.get("body_technique")
        data["body_technique"] = Technique(**body) if body else None
        sense = data.get("divine_sense_technique")
        data["divine_sense_technique"] = Technique(**sense) if sense else None
        transformation = data.get("transformation_technique")
        data["transformation_technique"] = Technique(**transformation) if transformation else None
        if data["transformation_technique"]:
            data["transformation_technique"].initial_transformations = []
        data["known_transformations"] = list(dict.fromkeys(map(str, data.get("known_transformations", []))))
        data["transformation_mastery"] = {
            str(form_id): {
                "purity": max(0.0, min(1.0, float(progress.get("purity", 0.0)))),
                "stats": {
                    stat: max(0.0, min(1.0, float(progress.get("stats", {}).get(stat, progress.get("purity", 0.0)))))
                    for stat in ("might", "guard", "mobility", "sense", "sustain", "breach")
                },
                "material_id": str(progress.get("material_id", "")),
                "source_type": str(progress.get("source_type", "unknown")),
            }
            for form_id, progress in data.get("transformation_mastery", {}).items()
            if isinstance(progress, dict)
        }
        data["transformation_loadouts"] = {
            str(technique_id): {
                "stored": list(dict.fromkeys(map(str, loadout.get("stored", [])))),
                "active": list(dict.fromkeys(map(str, loadout.get("active", [])))),
            }
            for technique_id, loadout in data.get("transformation_loadouts", {}).items()
            if isinstance(loadout, dict)
        }
        data["divine_sense_experience"] = max(0.0, float(data.get("divine_sense_experience", 0.0)))
        data["divine_sense_rank"] = max(0, int(data.get("divine_sense_rank", 0)))
        data["prisoners"] = list(data.get("prisoners", []))
        data["puppets"] = list(data.get("puppets", []))
        data["foreign_souls"] = list(data.get("foreign_souls", []))
        data["devouring_breakthrough_bonus"] = max(0.0, float(data.get("devouring_breakthrough_bonus", 0.0)))
        data["next_thunder_damage_reduction"] = max(0.0, min(0.75, float(data.get("next_thunder_damage_reduction", 0.0))))
        data["immortal_power_converted"] = bool(data.get("immortal_power_converted", False))
        data["immortal_conversion_stage"] = max(0, min(5, int(data.get("immortal_conversion_stage", 0))))
        last_conversion_age = data.get("immortal_conversion_last_age")
        data["immortal_conversion_last_age"] = int(last_conversion_age) if last_conversion_age is not None else None
        data["immortal_conversion_checked_units"] = max(0, int(data.get("immortal_conversion_checked_units", 0)))
        data["combat_techniques"] = [Technique(**entry) for entry in data.get("combat_techniques", [])]
        data["known_techniques"] = [Technique(**entry) for entry in data.get("known_techniques", [])]
        for known in data["known_techniques"]:
            if known.category == "transformation":
                known.initial_transformations = []
        data["inventory"] = [Item.from_dict(item) for item in data.get("inventory", [])]
        return cls(**data)


@dataclass
class HistoryRecord:
    event_id: str
    event_version: int
    age: int
    title: str
    choice_id: str | None
    result: str
    summary: str
    state_diff: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class GameState:
    id: str
    seed: int
    player: Player
    created_at: str
    updated_at: str
    rng_state: str = ""
    pending_event: dict[str, Any] | None = None
    history: list[HistoryRecord] = field(default_factory=list)
    sects: dict[str, SectState] = field(default_factory=dict)
    world_npcs: dict[str, SectNpc] = field(default_factory=dict)
    world_npc_template_ages: dict[str, int] = field(default_factory=dict)
    notable_npcs: dict[str, SectNpc] = field(default_factory=dict)
    encounter_npc_cache: list[dict[str, Any]] = field(default_factory=list)
    race_relations: dict[str, dict[str, Any]] = field(default_factory=dict)
    sect_relations: dict[str, dict[str, Any]] = field(default_factory=dict)
    story_trigger_attempts: dict[str, int] = field(default_factory=dict)
    family: SectState | None = None
    player_bounties: list[dict[str, Any]] = field(default_factory=list)
    governance_actions: dict[str, int] = field(default_factory=dict)
    market_realm_index: int | None = None
    market_world: str | None = None
    market_location_id: str | None = None
    market_age: int | None = None
    market_offers: list[dict[str, Any]] = field(default_factory=list)
    auction_state: dict[str, Any] = field(default_factory=dict)
    auction_sequence: int = 0
    debug_world_news: bool = False
    active_trial: dict[str, Any] | None = None
    diplomacy_unit: int = 0
    wars: list[dict[str, Any]] = field(default_factory=list)
    heavenly_court: dict[str, Any] = field(default_factory=dict)
    natal_artifact: dict[str, Any] = field(default_factory=dict)
    last_combat_report: dict[str, Any] | None = None
    settings: dict[str, bool] = field(default_factory=lambda: {
        "combat_popup": True,
        "achievement_popup": True,
        "auto_advance_player_wars": False,
    })
    world_rules_version: int = 9
    created_with_game_version: str = BASE_GAME_VERSION
    last_saved_with_game_version: str = BASE_GAME_VERSION
    version: int = 5

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "seed": self.seed,
            "player": self.player.to_dict(),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "rng_state": self.rng_state,
            "pending_event": self.pending_event,
            "history": [record.to_dict() for record in self.history],
            "sects": {sect_id: sect.to_dict() for sect_id, sect in self.sects.items()},
            "world_npcs": {npc_id: npc.to_dict() for npc_id, npc in self.world_npcs.items()},
            "world_npc_template_ages": self.world_npc_template_ages,
            "notable_npcs": {npc_id: npc.to_dict() for npc_id, npc in self.notable_npcs.items()},
            "encounter_npc_cache": self.encounter_npc_cache,
            "race_relations": self.race_relations,
            "sect_relations": self.sect_relations,
            "story_trigger_attempts": self.story_trigger_attempts,
            "family": self.family.to_dict() if self.family else None,
            "player_bounties": self.player_bounties,
            "governance_actions": self.governance_actions,
            "market_realm_index": self.market_realm_index,
            "market_world": self.market_world,
            "market_location_id": self.market_location_id,
            "market_age": self.market_age,
            "market_offers": self.market_offers,
            "auction_state": self.auction_state,
            "auction_sequence": self.auction_sequence,
            "debug_world_news": self.debug_world_news,
            "active_trial": self.active_trial,
            "diplomacy_unit": self.diplomacy_unit,
            "wars": self.wars,
            "heavenly_court": self.heavenly_court,
            "natal_artifact": self.natal_artifact,
            "last_combat_report": self.last_combat_report,
            "settings": self.settings,
            "world_rules_version": self.world_rules_version,
            "created_with_game_version": self.created_with_game_version,
            "last_saved_with_game_version": self.last_saved_with_game_version,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> GameState:
        return cls(
            id=value["id"],
            seed=value["seed"],
            player=Player.from_dict(value["player"]),
            created_at=value["created_at"],
            updated_at=value["updated_at"],
            rng_state=value.get("rng_state", ""),
            pending_event=value.get("pending_event"),
            history=[HistoryRecord(**entry) for entry in value.get("history", [])],
            sects={sect_id: SectState.from_dict(sect) for sect_id, sect in value.get("sects", {}).items()},
            world_npcs={npc_id: SectNpc.from_dict(npc) for npc_id, npc in value.get("world_npcs", {}).items()},
            world_npc_template_ages={str(npc_id): int(age) for npc_id, age in value.get("world_npc_template_ages", {}).items()},
            notable_npcs={npc_id: SectNpc.from_dict(npc) for npc_id, npc in value.get("notable_npcs", {}).items()},
            encounter_npc_cache=list(value.get("encounter_npc_cache", [])),
            race_relations=dict(value.get("race_relations", {})),
            sect_relations=dict(value.get("sect_relations", {})),
            story_trigger_attempts={str(key): int(count) for key, count in value.get("story_trigger_attempts", {}).items()},
            family=SectState.from_dict(value["family"]) if value.get("family") else None,
            player_bounties=list(value.get("player_bounties", [])),
            governance_actions={str(key): int(age) for key, age in value.get("governance_actions", {}).items()},
            market_realm_index=value.get("market_realm_index"),
            market_world=value.get("market_world"),
            market_location_id=value.get("market_location_id"),
            market_age=value.get("market_age"),
            market_offers=value.get("market_offers", []),
            auction_state=dict(value.get("auction_state", {})),
            auction_sequence=int(value.get("auction_sequence", 0)),
            debug_world_news=bool(value.get("debug_world_news", False)),
            active_trial=value.get("active_trial"),
            diplomacy_unit=int(value.get("diplomacy_unit", 0)),
            wars=list(value.get("wars", [])),
            heavenly_court=dict(value.get("heavenly_court", {})),
            natal_artifact=dict(value.get("natal_artifact", {})),
            last_combat_report=value.get("last_combat_report"),
            settings={
                "combat_popup": bool(value.get("settings", {}).get("combat_popup", True)),
                "achievement_popup": bool(value.get("settings", {}).get("achievement_popup", True)),
                "auto_advance_player_wars": bool(value.get("settings", {}).get("auto_advance_player_wars", False)),
            },
            world_rules_version=value.get("world_rules_version", 1),
            created_with_game_version=str(value.get("created_with_game_version", "pre-1.0.0")),
            last_saved_with_game_version=str(value.get("last_saved_with_game_version", "pre-1.0.0")),
            version=value.get("version", 1),
        )
