"""Composition of cultivation operations through explicit, late-bound ports."""
from ...system.cultivation_dependencies import (
    ApertureDependencies,
    CultivationCommitDependencies,
    CultivationDependencies,
    CultivationSessionDependencies,
    DoctrineActionDependencies,
    DoctrineFusionDependencies,
    DoctrineStudyDependencies,
    DoctrineViewDependencies,
    ImmortalActionDependencies,
    ImmortalBodyDependencies,
    ImmortalViewDependencies,
)


def bind_doctrine_study(host) -> DoctrineStudyDependencies:
    return DoctrineStudyDependencies(
        _begin_fusion_study=lambda *args, **kwargs: host._begin_fusion_study(*args, **kwargs),
        _complete_immortal_conversion_stage=lambda *args, **kwargs: host._complete_immortal_conversion_stage(*args, **kwargs),
        _finish_fusion_study=lambda *args, **kwargs: host._finish_fusion_study(*args, **kwargs),
    )


def bind_doctrine_actions(host) -> DoctrineActionDependencies:
    return DoctrineActionDependencies(
        _begin_doctrine_action=lambda *args, **kwargs: host._begin_doctrine_action(*args, **kwargs),
        _begin_fusion_study=lambda *args, **kwargs: host._begin_fusion_study(*args, **kwargs),
        _cultivation_game=lambda *args, **kwargs: host._cultivation_game(*args, **kwargs),
        _fuse_doctrine=lambda *args, **kwargs: host._fuse_doctrine(*args, **kwargs),
        advance=lambda *args, **kwargs: host.advance(*args, **kwargs),
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
        yaochi_action=lambda *args, **kwargs: host.yaochi_action(*args, **kwargs),
    )


def bind_doctrine_view(host) -> DoctrineViewDependencies:
    return DoctrineViewDependencies(
        _public_fusion=lambda *args, **kwargs: host._public_fusion(*args, **kwargs),
        _public_immortal=lambda *args, **kwargs: host._public_immortal(*args, **kwargs),
        _public_immortal_body=lambda *args, **kwargs: host._public_immortal_body(*args, **kwargs),
    )


def bind_doctrine_fusion(host) -> DoctrineFusionDependencies:
    return DoctrineFusionDependencies(
        _fusion_requirements=lambda *args, **kwargs: host._fusion_requirements(*args, **kwargs),
        commit=bind_cultivation_commit(host),
    )


def bind_cultivation_session(host) -> CultivationSessionDependencies:
    return CultivationSessionDependencies(
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
    )


def bind_cultivation_commit(host) -> CultivationCommitDependencies:
    return CultivationCommitDependencies(
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
    )


def bind_immortal_actions(host) -> ImmortalActionDependencies:
    return ImmortalActionDependencies(
        _cultivation_game=lambda *args, **kwargs: host._cultivation_game(*args, **kwargs),
        _immortal_body_action=lambda *args, **kwargs: host._immortal_body_action(*args, **kwargs),
        _spend_cultivation=lambda *args, **kwargs: host._spend_cultivation(*args, **kwargs),
        _start_voisinage_backlash=lambda *args, **kwargs: host._start_voisinage_backlash(*args, **kwargs),
        _temper_golden_light=lambda *args, **kwargs: host._temper_golden_light(*args, **kwargs),
        advance=lambda *args, **kwargs: host.advance(*args, **kwargs),
        breakthrough=lambda *args, **kwargs: host.breakthrough(*args, **kwargs),
        commit=bind_cultivation_commit(host),
        yaochi_action=lambda *args, **kwargs: host.yaochi_action(*args, **kwargs),
    )


def bind_immortal_view(host) -> ImmortalViewDependencies:
    return ImmortalViewDependencies(
        _breakthrough_chance=lambda *args, **kwargs: host._breakthrough_chance(*args, **kwargs),
        _major_breakthrough_requirement=lambda *args, **kwargs: host._major_breakthrough_requirement(*args, **kwargs),
    )


def bind_immortal_body(host) -> ImmortalBodyDependencies:
    return ImmortalBodyDependencies(
        commit=bind_cultivation_commit(host),
    )


def bind_aperture(host) -> ApertureDependencies:
    return ApertureDependencies(
        _load=lambda *args, **kwargs: host._load(*args, **kwargs),
        present=lambda *args, **kwargs: host.present(*args, **kwargs),
        _get_store=lambda: host.store,
    )


def bind_cultivation(host) -> CultivationDependencies:
    return CultivationDependencies(
        study=bind_doctrine_study(host),
        actions=bind_doctrine_actions(host),
        view=bind_doctrine_view(host),
        fusion=bind_doctrine_fusion(host),
        session=bind_cultivation_session(host),
        commit=bind_cultivation_commit(host),
        immortal_actions=bind_immortal_actions(host),
        immortal_view=bind_immortal_view(host),
        body=bind_immortal_body(host),
        aperture=bind_aperture(host),
    )
