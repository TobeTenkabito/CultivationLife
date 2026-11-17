"""Explicit expedition ports; no engine façade dependency from the system."""
from ...system.dungeons.runtime import Dependencies
from ..transactions import accept_committed_game


def bind(engine):
    return Dependencies(load=engine._load,save=engine.store.save,present=engine.present,
        commit=lambda game:accept_committed_game(engine,game),combat=engine._combat,
        die=engine._die,npc_power=engine._npc_power,maps=engine.maps)
