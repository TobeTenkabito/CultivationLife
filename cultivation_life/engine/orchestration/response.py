"""Preserve response effect order: settle, commit if moved, prepare, snapshot.

The gameplay command still owns its existing save point. Response preparation
does not introduce another save for legacy lazy state or change reward timing.
Only the existing boundary-expulsion commit is coordinated here.
"""
from ...models import GameState
from ..presentation.projection import PreparedGameView
from ..response_dependencies import ResponseDependencies


def prepare_response(deps: ResponseDependencies, game: GameState) -> PreparedGameView:
    if deps.settle_boundary(game):
        deps.commit(game)
    return PreparedGameView(deps.prepare_view(game))
