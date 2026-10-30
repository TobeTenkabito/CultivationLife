"""Disposable saved-display fixture shared by HTTP, compiled and native checks."""
import copy

from cultivation_life.content_registry import TECHNIQUE_CATALOG
from cultivation_life.models import Item

BOOK = 'TECH_OPEN_SONGCHUANG_NEUTRAL_MAIN'
GHOST = 'TECH_OPEN_CHANGYE_NEUTRAL_MAIN'


def prepare_technique_names(engine, identity):
    game = engine._load(identity)
    game.pending_event = None
    main = copy.deepcopy(TECHNIQUE_CATALOG[BOOK])
    main.name, main.level = '松窗抱朴归真经', 5
    ghost = copy.deepcopy(TECHNIQUE_CATALOG[GHOST])
    ghost.name, ghost.level = '长夜抱朴归真经', 5
    game.player.known_techniques = [main, ghost]
    game.player.technique = copy.deepcopy(main)
    game.player.support_technique = None
    game.player.inventory = [Item(
        id=f'technique_manual::{BOOK}::lv5', name='《松窗抱朴归真经》Lv.5 传承玉简',
        quantity=2, technique_id=BOOK, technique_level=5, technique_origin_realm_index=1,
    ), Item(id='names-custom', name='长夜抱朴归真经', quantity=3, combat_bonus=123)]
    engine.store.save(game)
    return game


def inspect_technique_names(engine, identity, upgraded=False):
    game = engine._load(identity)
    known = {t.id:t for t in game.player.known_techniques}
    assert known[BOOK].name == '抱朴养真经'
    assert known[GHOST].name == '晦烛含魄篇'
    assert known[BOOK].level == (6 if upgraded else 5)
    assert known[GHOST].level == 5
    manual = next(i for i in game.player.inventory if i.technique_id == BOOK)
    assert manual.quantity == (1 if upgraded else 2) and manual.technique_level == 5
    assert '抱朴养真经' in manual.name
    custom = next(i for i in game.player.inventory if i.id == 'names-custom')
    assert (custom.name, custom.quantity, custom.combat_bonus) == ('长夜抱朴归真经', 3, 123)
    return game
