"""ID-bound relationship mappings. Personal facts live only on an NPC.

The dict-shaped read/write interface keeps gameplay consumers explicit without
storing another person snapshot. `reference()` is the persistence form; `dict`
and deepcopy materialize detached display/command data.
"""
from __future__ import annotations

import copy

from .relationship_schema import (
    LABEL_FIELDS,
    LIST_RELATIONS,
    PERSON_FIELDS,
    SINGLE_RELATIONS,
    person_seed,
)


def find_person(game, identity, *, include_inactive=False):
    if identity in game.inactive_npcs:
        return game.inactive_npcs[identity]
    if game.family and not game.family.extinct:
        npc = next((npc for npc in game.family.npcs if npc.id == identity), None)
        if npc is not None:
            return npc
    npc = game.world_npcs.get(identity) or game.notable_npcs.get(identity)
    if npc is not None:
        return npc
    for sect in game.sects.values():
        npc = next((npc for npc in sect.npcs if npc.id == identity), None)
        if npc is not None:
            return npc
    if include_inactive and game.family:
        npc = next((npc for npc in game.family.npcs if npc.id == identity), None)
        if npc is not None:
            return npc
    return game.relationship_npcs.get(identity)


class RelationshipRecord(dict):
    def __init__(self, values=(), *, game=None, labels=None):
        super().__init__(values)
        self._game = game
        self._labels = labels

    @property
    def person(self):
        identity = dict.get(self, 'npc_id') or dict.get(self, 'id')
        npc = find_person(self._game, identity, include_inactive=True) if self._game is not None else None
        if npc is None:
            raise RuntimeError(f'关系人物引用已失效：{identity}')
        return npc

    def __getitem__(self, key):
        if self._game is not None:
            if key in PERSON_FIELDS:
                return getattr(self.person, key)
            if key in LABEL_FIELDS and self._labels is not None:
                return self._labels(self.person)[key]
        return dict.__getitem__(self, key)

    def __setitem__(self, key, value):
        if self._game is not None and key in {'id', 'npc_id'} and value != dict.get(self, key):
            raise ValueError('不能通过关系记录更换人物身份')
        if self._game is not None and key in PERSON_FIELDS:
            setattr(self.person, key, value)
        elif self._game is not None and key in LABEL_FIELDS:
            return  # Derived labels are never authoritative facts.
        else:
            dict.__setitem__(self, key, value)

    def __eq__(self, other):
        if not isinstance(other, dict):
            return NotImplemented
        return self.copy() == dict(other)

    def __ne__(self, other):
        result = self.__eq__(other)
        return NotImplemented if result is NotImplemented else not result

    def __or__(self, other):
        return self.copy() | other

    def __ror__(self, other):
        return other | self.copy()

    def __ior__(self, other):
        self.update(other)
        return self

    def __iter__(self):
        keys = set(dict.keys(self))
        if self._game is not None:
            keys.update(PERSON_FIELDS)
            if self._labels is not None:
                keys.update(LABEL_FIELDS)
        return iter(sorted(keys))

    def __len__(self):
        return sum(1 for _ in self.__iter__())

    def __contains__(self, key):
        return (self._game is not None and
                (key in PERSON_FIELDS or key in LABEL_FIELDS and self._labels is not None)) or dict.__contains__(self, key)

    def get(self, key, default=None):
        return self[key] if key in self else default

    def keys(self):
        return list(iter(self))

    def items(self):
        return [(key, self[key]) for key in self]

    def values(self):
        return [self[key] for key in self]

    def update(self, other=(), **kwargs):
        for key, value in dict(other, **kwargs).items():
            self[key] = value

    def setdefault(self, key, default=None):
        if key not in self:
            self[key] = default
        return self[key]

    def copy(self):
        return dict(self.items())

    def __deepcopy__(self, memo):
        return copy.deepcopy(self.copy(), memo)

    def reference(self):
        return copy.deepcopy({key: value for key, value in dict.items(self)
                              if key not in PERSON_FIELDS | LABEL_FIELDS})


def bind_relationship(game, row, npc_type, *, labels=None):
    if isinstance(row, RelationshipRecord) and row._game is game:
        if labels is not None:
            row._labels = labels
        return row
    labels = labels or getattr(game, '_relationship_labels', None)
    identity = str(row.get('npc_id') or row.get('id') or '')
    npc = find_person(game, identity, include_inactive=True)
    if npc is None:
        npc = npc_type(**person_seed(row, game.player.world))
        game.relationship_npcs[npc.id] = npc
    for key in ('affinity', 'main_technique_id'):
        if getattr(npc, key) is None and row.get(key) is not None:
            setattr(npc, key, row[key])
    if npc.affinity is None:
        npc.affinity = 20.0
    details = {key: value for key, value in row.items() if key not in PERSON_FIELDS | LABEL_FIELDS}
    details.update(id=npc.id, npc_id=npc.id)
    return RelationshipRecord(details, game=game, labels=labels)


def bind_relationships(game, npc_type, *, labels=None):
    changed = False
    for identity, npc in list(game.relationship_npcs.items()):
        if find_person(game, identity, include_inactive=True) is not npc:
            del game.relationship_npcs[identity]
            changed = True
    if labels is not None:
        game._relationship_labels = labels
    for field in SINGLE_RELATIONS:
        row = getattr(game.player, field)
        if row:
            linked = bind_relationship(game, row, npc_type, labels=labels)
            changed = changed or linked is not row
            setattr(game.player, field, linked)
    for field in LIST_RELATIONS:
        rows = getattr(game.player, field)
        for index, row in enumerate(rows):
            if row:
                linked = bind_relationship(game, row, npc_type, labels=labels)
                changed = changed or linked is not row
                rows[index] = linked
    return changed
