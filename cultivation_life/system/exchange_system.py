from __future__ import annotations
from functools import cached_property
from .economy.wiring import bind_exchange
from .economy import exchange as economy_exchange

import copy
import math
from collections import Counter
from typing import Any

from ..models import HistoryRecord
from ..runtime import decode_rng, encode_rng, now_iso
from ..rules import remove_item
from .crafting_system import make_crafting_material_instance


EXCHANGE_VENUES = {
    "human": "wudi_plain", "spirit": "hundred_race_city",
    "demon": "red_marrow_city", "true_demon": "black_lotus_city",
    "monster_realm": "myriad_beast_city", "phantom_underworld": "nine_tail_dream_city",
    "hell": "yin_market_capital", "celestial": "jade_capital",
    "asura": "ten_thousand_battle_city", "nether": "ancestral_beast_garden",
    "reincarnation": "karma_city",
}
EXCHANGE_ALIASES = ["青笠客", "无名散人", "听雨客", "灰衣道人", "照夜人"]


def bind_exchange_compatibility(host):
    return bind_exchange(
        host,
        decode_rng=lambda *args, **kwargs: decode_rng(*args, **kwargs),
        _get_EXCHANGE_ALIASES=lambda: EXCHANGE_ALIASES,
        _get_EXCHANGE_VENUES=lambda: EXCHANGE_VENUES,
    )


class ExchangeSystemMixin:
    """Anonymous, material-only barter; all valuations are server-owned."""

    @cached_property
    def _exchange_dependencies(self):
        return bind_exchange_compatibility(self)


    def _exchange_location(self, world):
        return economy_exchange._exchange_location(self._exchange_dependencies, world)

    def _schedule_exchange(self, game, rng):
        return economy_exchange._schedule_exchange(self._exchange_dependencies, game, rng)

    def _open_exchange(self, game, rng):
        return economy_exchange._open_exchange(self._exchange_dependencies, game, rng)

    def _advance_exchange_clock(self, game, rng):
        return economy_exchange._advance_exchange_clock(self._exchange_dependencies, game, rng)

    def _exchange_materials(self, game):
        return economy_exchange._exchange_materials(self._exchange_dependencies, game)

    def exchange_action(self, game_id: str, action: str, payload: dict[str, Any]):
        return economy_exchange.exchange_action(self._exchange_dependencies, game_id, action, payload)

    def _public_exchange(self, game):
        return economy_exchange._public_exchange(self._exchange_dependencies, game)
