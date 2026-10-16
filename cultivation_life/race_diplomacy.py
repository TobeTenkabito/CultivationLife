"""World-scoped political relations; ambiguous legacy records stay untouched."""
from collections.abc import MutableMapping
from .world_state import race_pair


class RaceRelations(MutableMapping):
    def __init__(self, game, world):
        self.records = game.race_relations
        self.world = world

    def _key(self, key):
        first, second = key.split('|')
        return race_pair(f'{self.world}:{first}', f'{self.world}:{second}')

    def __getitem__(self, key):
        return self.records[self._key(key)]

    def __setitem__(self, key, value):
        self.records[self._key(key)] = value

    def __delitem__(self, key):
        del self.records[self._key(key)]

    def __iter__(self):
        prefix = self.world + ':'
        for key in self.records:
            parts = key.split('|')
            if len(parts) == 2 and all(p.startswith(prefix) for p in parts):
                yield race_pair(*(p[len(prefix):] for p in parts))

    def __len__(self):
        return sum(1 for _ in self)


def relations_for(game, world=None):
    return RaceRelations(game, game.player.world if world is None else world)
