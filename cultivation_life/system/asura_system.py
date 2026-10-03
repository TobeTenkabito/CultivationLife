"""Compatibility adapter for older callers; GameEngine no longer inherits this mixin."""


class AsuraSystemMixin:
    def asura_action(self, game_id, action, target_id='', body_ids=None, name=''):
        from ..engine.actions.asura import asura_action
        from ..engine.composition.asura import bind_asura_actions
        return asura_action(bind_asura_actions(self), game_id, action, target_id, body_ids, name)

    def _asura_cultivate(self, game, action, target_id, body_ids, name, rng):
        from ..engine.actions.asura import _asura_cultivate
        from ..engine.composition.asura import bind_asura_actions
        return _asura_cultivate(bind_asura_actions(self), game, action, target_id, body_ids, name, rng)

    @staticmethod
    def _spend_asura_souls(state, cost):
        from ..engine.actions.asura import _spend_asura_souls
        return _spend_asura_souls(state, cost)
