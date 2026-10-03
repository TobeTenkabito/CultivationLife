"""The sole engine adapter. Overrides exist on isolated instances, never globals."""
from ..engine import GameEngine


class SessionEngine(GameEngine):
    def __init__(self, project_root, save_directory, overrides):
        self._session_overrides = dict(overrides)
        super().__init__(project_root, save_directory)

    def _breakthrough_chance(self, player, major, allow_aids=True):
        result = super()._breakthrough_chance(player, major, allow_aids)
        chance = self._session_overrides.get('breakthrough_chance')
        if chance is not None:
            result = {**result, 'final': chance}
        return result
