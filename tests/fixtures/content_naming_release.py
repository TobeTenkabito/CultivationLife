"""Isolated old-spelling fixture; product code owns decoding and every command."""
import copy


def prepare_content_naming_release(engine, identity):
    from cultivation_life.content_registry import ITEM_CATALOG, TECHNIQUE_CATALOG
    from cultivation_life.models import Item
    from cultivation_life.rules import add_item
    game = engine._load(identity)
    game.pending_event = None
    technique = copy.deepcopy(TECHNIQUE_CATALOG['TECH_YELLOW_COURT_INNER'])
    technique.id, technique.name, technique.level = 'TECH_COMMON_NASCENT', '婴神太虚录', 5
    game.player.known_techniques = [technique, copy.deepcopy(TECHNIQUE_CATALOG['TECH_CICADA_METAMORPHOSIS'])]
    game.player.technique = copy.deepcopy(technique)
    game.player.support_technique = None
    game.player.inventory = [Item(id='nascent_flame_crystal', name='婴火玄晶', quantity=7), Item(
        id='technique_manual::TECH_COMMON_NASCENT::lv5', name='《婴神太虚录》Lv.5 传承玉简',
        quantity=2, technique_id='TECH_COMMON_NASCENT', technique_level=5, technique_origin_realm_index=4,
    ), Item(id='custom-naming-sword', name='婴神太虚录', combat_bonus=123)]
    bottle = copy.deepcopy(ITEM_CATALOG['qilin_blessing_elixir'])
    bottle.id, bottle.name = 'heroic_progeny_elixir', '英姿神武口服液'
    game.player.inventory.append(bottle)
    add_item(game.player, 'spirit_stone', 1000)
    engine._content_naming_release_age = game.player.age
    engine.store.save(game)


def inspect_content_naming_release(engine, identity):
    game = engine._load(identity)
    assert game.player.age == engine._content_naming_release_age
    assert game.player.technique.id == 'TECH_YELLOW_COURT_INNER' and game.player.technique.level == 6
    assert next(i.quantity for i in game.player.inventory if i.id == 'radiant_flame_crystal') == 7
    assert next(i.quantity for i in game.player.inventory if i.technique_id == 'TECH_YELLOW_COURT_INNER') == 1
    assert next(i for i in game.player.inventory if i.id == 'custom-naming-sword').name == '婴神太虚录'
    assert not any(i.id in {'qilin_blessing_elixir', 'heroic_progeny_elixir'} for i in game.player.inventory)
    assert game.player.guaranteed_progeny
