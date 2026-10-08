"""Named capabilities for independently executable game operations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..models import GameState
from ..ports import SavePort


@dataclass(frozen=True, slots=True)
class DoctrineStudyDependencies:
    _begin_fusion_study: Callable[..., Any]
    _complete_immortal_conversion_stage: Callable[..., Any]
    _finish_fusion_study: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class DoctrineActionDependencies:
    _complete_immortal_conversion_stage: Callable[..., Any]
    _begin_doctrine_action: Callable[..., Any]
    _begin_fusion_study: Callable[..., Any]
    _cultivation_game: Callable[..., Any]
    _fuse_doctrine: Callable[..., Any]
    advance: Callable[..., Any]
    present: Callable[[GameState], dict[str, Any]]
    _get_store: Callable[[], SavePort]
    yaochi_action: Callable[..., Any]

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class DoctrineViewDependencies:
    _public_fusion: Callable[..., Any]
    _public_immortal: Callable[..., Any]
    _public_immortal_body: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class DoctrineFusionDependencies:
    _fusion_requirements: Callable[..., Any]
    commit: CultivationCommitDependencies


@dataclass(frozen=True, slots=True)
class CultivationSessionDependencies:
    _load: Callable[[str], GameState]


@dataclass(frozen=True, slots=True)
class CultivationCommitDependencies:
    present: Callable[[GameState], dict[str, Any]]
    _get_store: Callable[[], SavePort]

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class ImmortalActionDependencies:
    _cultivation_game: Callable[..., Any]
    _immortal_body_action: Callable[..., Any]
    _spend_cultivation: Callable[..., Any]
    _start_voisinage_backlash: Callable[..., Any]
    _temper_golden_light: Callable[..., Any]
    advance: Callable[..., Any]
    breakthrough: Callable[..., Any]
    commit: CultivationCommitDependencies
    yaochi_action: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class ImmortalViewDependencies:
    _breakthrough_chance: Callable[..., Any]
    _major_breakthrough_requirement: Callable[..., Any]


@dataclass(frozen=True, slots=True)
class ImmortalBodyDependencies:
    commit: CultivationCommitDependencies


@dataclass(frozen=True, slots=True)
class ApertureDependencies:
    _load: Callable[[str], GameState]
    present: Callable[[GameState], dict[str, Any]]
    _get_store: Callable[[], SavePort]

    @property
    def store(self) -> SavePort:
        return self._get_store()


@dataclass(frozen=True, slots=True)
class CultivationDependencies:
    study: DoctrineStudyDependencies
    actions: DoctrineActionDependencies
    view: DoctrineViewDependencies
    fusion: DoctrineFusionDependencies
    session: CultivationSessionDependencies
    commit: CultivationCommitDependencies
    immortal_actions: ImmortalActionDependencies
    immortal_view: ImmortalViewDependencies
    body: ImmortalBodyDependencies
    aperture: ApertureDependencies
