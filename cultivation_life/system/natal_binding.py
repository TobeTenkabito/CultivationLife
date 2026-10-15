"""One ownership transfer for a standard inventory artifact at birth or binding."""
from ..rules import remove_item
from ..content_registry import WORLD_SYSTEMS


def access_reason(game):
    if not game.player.alive or game.pending_event or game.player.imprisonment:
        return '当前状态无法祭炼本命法宝'
    if game.player.realm_index < int(WORLD_SYSTEMS['natal_artifact']['minimum_realm']):
        return '结丹期方可修炼本命法宝'
    return ''


def require_access(game):
    reason = access_reason(game)
    if reason:
        raise ValueError(reason)


def bind_standard(game, item_id):
    item = next((i for i in game.player.inventory if i.id == item_id and i.quantity > 0), None)
    if game.natal_artifact or not item or not remove_item(game.player, item_id):
        raise ValueError('本命法宝已存在或物品已不在背包')
    game.natal_artifact = dict(item_id=item_id, name=item.name, level=1, experience=0,
                              bound_age=game.player.age, slots=[], slot_rule_version=2)
