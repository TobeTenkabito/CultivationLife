"""One ownership transfer for a standard inventory artifact at birth or binding."""
from ..rules import remove_item


def bind_standard(game, item_id):
    item = next((i for i in game.player.inventory if i.id == item_id and i.quantity > 0), None)
    if game.natal_artifact or not item or not remove_item(game.player, item_id):
        raise ValueError('本命法宝已存在或物品已不在背包')
    game.natal_artifact = dict(item_id=item_id, name=item.name, level=1, experience=0,
                              bound_age=game.player.age, slots=[], slot_rule_version=2)
