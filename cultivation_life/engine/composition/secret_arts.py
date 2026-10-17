"""Explicit bindings for the personal secret-art command."""
from ...system.secret_arts import SecretArtDependencies
from ..transactions import accept_committed_game


def bind(host):
    return SecretArtDependencies(
        load=host._load, save=host.store.save, present=host.present,
        commit=lambda game: accept_committed_game(host, game),
        year=host._dependencies.advancement.year,
        settlement=host._dependencies.advancement.settlement,
        refresh_market=host._ensure_market, compact_history=host._compact_world_history,
    )
