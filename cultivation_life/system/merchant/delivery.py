"""One owned parcel, created at completion and transferred at its original address."""
from dataclasses import dataclass, field, asdict

from ...models import Item, Technique
from ...rules import add_item, acquire_technique


@dataclass
class CommissionParcel:
    inventory: list = field(default_factory=list)
    crafting_materials: list = field(default_factory=list)
    formation_materials: list = field(default_factory=list)
    crafted_artifacts: list = field(default_factory=list)
    formation_loadouts: list = field(default_factory=list)
    talismans: list = field(default_factory=list)
    techniques: list = field(default_factory=list)
    immortal_traces: int = 0
    formation_sequence: int = 0
    talisman_sequence: int = 0

    def freeze(self, game, order):
        for name in ('talismans', 'formation_loadouts'):
            for index, row in enumerate(getattr(self, name)):
                row['id'] = f"merchant-{name}-{game.id}-{order['id']}-{index}"
        result = asdict(self)
        result.pop('formation_sequence')
        result.pop('talisman_sequence')
        return result


def local_delivery(game, order):
    return (game.player.world == order['world']
            and (not order.get('delivery_location') or game.player.location_id == order['delivery_location']))


def claim(game, order):
    if not order.get('delivery_goods') or order.get('delivery_claimed'):
        raise ValueError('该委托没有待领取产物，或已经领取')
    if not local_delivery(game, order):
        raise ValueError('请返回委托原发布界面的发布地点领取产物')
    goods = order.pop('delivery_goods')
    player = game.player
    for row in goods['inventory']:
        add_item(player, Item(**row), row['quantity'])
    for name in ('crafting_materials', 'formation_materials', 'crafted_artifacts', 'formation_loadouts', 'talismans'):
        getattr(player, name).extend(goods[name])
    for row in goods['techniques']:
        acquire_technique(player, Technique(**row))
    player.immortal_traces += goods['immortal_traces']
    player.formation_sequence += len(goods['formation_loadouts'])
    player.talisman_sequence += len(goods['talismans'])
    order['delivery_claimed'] = True
    order['claimed_age'] = player.age
    return f"委托「{order['name']}」的产物已领取。{order['delivery']}"
