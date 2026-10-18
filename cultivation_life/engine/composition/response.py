"""Compose response effects separately from pure snapshot projection."""
from ..actions.exploration import reconcile_boundary
from ..engine_presentation import prepare_view
from ..response_dependencies import ResponseDependencies


def bind_response(host) -> ResponseDependencies:
    return ResponseDependencies(
        settle_boundary=lambda game: reconcile_boundary(host._world_move_dependencies(), game),
        commit=lambda game: host.store.save(game),
        prepare_view=lambda game: prepare_view(host._dependencies.view_preparation, game),
    )
