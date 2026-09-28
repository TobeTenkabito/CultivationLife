"""Synchronous domain notifications, independent of optional content packs.

Publish only after an action succeeds. Listeners share the action's save transaction;
rendering and loading a save never publish gameplay events.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class SemanticEvent:
    name: str
    data: Mapping[str, Any]


_listeners = {}


def subscribe(identity, listener):
    _listeners[identity] = listener


def emit(game, event_name, **data):
    event = SemanticEvent(event_name, MappingProxyType(data))
    for listener in tuple(_listeners.values()):
        listener(game, event)


def relationship_roles(game, npc_id, faction_id=None):
    player = game.player
    roles = []
    for key, row in (("master", player.master), ("companion", player.dao_companion)):
        if row and str(row.get("id")) == str(npc_id) and row.get("alive", True):
            roles.append(key)
    if faction_id and faction_id == player.faction_id:
        roles.append("sect_member")
    return roles
