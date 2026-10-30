"""Preserve response effect order: settle, commit if moved, prepare, snapshot.

The gameplay command still owns its existing save point. Response preparation
does not introduce another save for legacy lazy state or change reward timing.
Only the existing boundary-expulsion commit is coordinated here.
"""
from ...models import GameState
from ..presentation.projection import PreparedGameView, PreparedJsonGameView
from ..response_dependencies import ResponseDependencies


def _prepare_payload(deps: ResponseDependencies, game: GameState) -> dict:
    if deps.settle_boundary(game):
        deps.commit(game)
    return deps.prepare_view(game)


def prepare_response(deps: ResponseDependencies, game: GameState) -> PreparedGameView:
    return PreparedGameView(_prepare_payload(deps, game))


def prepare_json_response(deps: ResponseDependencies, game: GameState, *,
                          defer_order_goods: bool = False) -> PreparedJsonGameView:
    payload = _prepare_payload(deps, game)
    network = payload.get('fleet_network')
    # Organization finance also renders order forms. Keep its catalog until
    # those consumers have their own deferred-read contract; reuse the original
    # authoritative can_order result instead of deriving new permissions here.
    organization_orders = defer_order_goods and isinstance(network, dict) and any(
        isinstance(fleet, dict) and fleet.get('can_order')
        and fleet.get('owner_kind') in ('sect', 'family')
        for fleet in (network.get('fleets') or ()))
    if (defer_order_goods and isinstance(network, dict) and 'order_goods' in network
            and not organization_orders):
        # Only static catalog declarations are omitted. Live permissions,
        # positions, orders and events remain in this authoritative response.
        network = dict(network)
        del network['order_goods']
        network['order_goods_deferred'] = True
        payload = dict(payload, fleet_network=network)
    return PreparedJsonGameView(payload)
