from __future__ import annotations
from ...models import GameState
import copy
from ...runtime import decode_rng
from ...runtime import encode_rng
from .dependencies import ServicesPreparationDependencies


def prepare_services(deps: ServicesPreparationDependencies, game: GameState) -> bool:
    changed = False
    rng = decode_rng(game.seed, game.rng_state)
    if deps._ensure_natal_artifact(game):
        changed = True
    if game.player.world == "celestial" and deps._ensure_heavenly_court(game, rng):
        game.rng_state = encode_rng(rng)
        changed = True
    if deps._ensure_market(game, rng):
        game.rng_state = encode_rng(rng)
        changed = True
    before_buddhist = copy.deepcopy(game.buddhist_state)
    deps._ensure_buddhist_state(game)
    return bool(changed or before_buddhist != game.buddhist_state)
