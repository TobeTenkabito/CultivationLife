"""Isolated materials fixture; ordinary natal commands own every item transfer."""
from cultivation_life.content_registry import WORLD_SYSTEMS
from cultivation_life.rules import add_item


def prepare_natal_materials_release(engine, identity):
    game = engine._load(identity)
    game.pending_event = None
    game.player.inventory.clear()
    add_item(game.player, 'starfall_blade')
    rows = [r for r in WORLD_SYSTEMS['natal_artifact']['materials']
            if r['item_id'].startswith('natal_human_') and r['minimum_realm'] == 3]
    for row in rows:
        add_item(game.player, row['item_id'], 2)
    engine.store.save(game)
    engine.natal_artifact_action(identity, 'bind', 'starfall_blade')
    game = engine._load(identity)
    game.natal_artifact.update(level=30, slots=[None] * 3, experience=0)
    engine._sync_natal_artifact_bonuses(game)
    engine._natal_materials_age = game.player.age
    engine.store.save(game)
    return [r['item_id'] for r in rows]


def inspect_natal_materials_release(engine, identity):
    game = engine._load(identity)
    assert game.player.age == engine._natal_materials_age
    assert game.natal_artifact['slots'][0] is None
    assert not any(game.natal_artifact['slots'])
    expected = [r for r in WORLD_SYSTEMS['natal_artifact']['materials']
                if r['item_id'].startswith('natal_human_') and r['minimum_realm'] == 3]
    assert len(expected) == 3
    for row in expected:
        assert next(i.quantity for i in game.player.inventory if i.id == row['item_id']) == 2
    assert sum(r.event_id == 'SYS_NATAL_ARTIFACT' and r.result == 'socketed' for r in game.history) == 1
