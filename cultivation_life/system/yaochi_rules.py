"""Player economy: bounded jobs and escrowed commissions, no NPC/yearly polling."""
import copy
import math

from ..content_registry import WORLD_SYSTEMS, ITEM_CATALOG
from ..models import Technique
from ..rules import add_item, learn_technique, add_technique_copy
from .immortal_cultivation import rules


def config():
    return WORLD_SYSTEMS['yaochi']


def account(game):
    return game.yaochi_state


def spend(game, amount):
    amount = int(amount)
    if amount <= 0 or account(game).get('merit', 0) < amount:
        raise ValueError('瑶池功勋不足')
    account(game)['merit'] -= amount


def require_market(game):
    p = game.player
    if p.world != 'celestial' or p.realm_index < 9 or p.location_id != config()['location_id']:
        raise ValueError('须亲临仙界瑶池办理功勋交易与委托')
    if not p.alive or game.pending_event or game.active_trial or p.imprisonment or p.ghost_captor or (game.guixu_state.get('player_session') or {}).get('trapped'):
        raise ValueError('当前状态无法办理瑶池事务')


def offers(game, *, commission=False):
    from .doctrine_system import _offers
    result = []
    books = ([b for d in game.doctrine_state.get('definitions', {}).values() for b in d['manuals']
              if b['grade'] <= game.player.realm_index] if commission else _offers(game))
    locked = account(game).get('locked_offers', {}) if not commission else {}
    if not commission:
        books = [b for b in books if b['id'] not in locked][:max(0, 5-len(locked))]
        result.extend(copy.deepcopy(list(locked.values())))
    for book in books:
        result.append(dict(id=book['id'], name=book['name'], kind='doctrine', quantity=1,
                           price=config()['manual_prices'][max(0,min(3,book['grade']-9))], payload=book))
    for manual in rules()['body']['manuals']:
        result.append(dict(id=manual['id'], name=manual['name'], kind='body_manual', quantity=1,
                           price=config()['body_manual_prices'][manual['id']]))
    for supply in [*rules()['body']['supplies'], *config()['materials']]:
        price = supply['price'] if supply in config()['materials'] else config()['supply_prices'][supply['id']]
        result.append(dict(id=supply['id'], name=ITEM_CATALOG[supply['id']].name, kind='item', quantity=supply['quantity'], price=price))
    for pill in config()['breakthrough_pills']:
        if pill['realm'] == game.player.realm_index:
            item = ITEM_CATALOG[pill['id']]
            result.append(dict(id=item.id, name=item.name, kind='item', quantity=pill['quantity'],
                               price=pill['price'], description=item.description))
    return result


def grant(game, offer, amount=1):
    p = game.player
    if offer['kind']=='body_manual':
        if offer['id'] in p.immortal_body.get('manuals', []):
            raise ValueError('已经掌握此仙躯功法')
        p.immortal_body.setdefault('manuals', []).append(offer['id'])
        p.immortal_body.setdefault('active_manual', offer['id'])
    elif offer['kind']=='doctrine':
        from .doctrine.provider import player_record
        technique = Technique(**copy.deepcopy(offer['payload']))
        learned = learn_technique(p, technique)
        add_technique_copy(p, technique, amount - int(learned))
        player_record(game)['progress'].setdefault(technique.doctrine_id, {'level':0,'experience':0})
    else:
        add_item(p, offer['id'], offer['quantity'] * amount)


def experience(game):
    cfg = config()['experience']
    xp = max(0, int(account(game).get('experience', 0)))
    level = 1 + xp // cfg['per_level']
    return dict(level=level, total=xp, progress=xp % cfg['per_level'], required=cfg['per_level'],
                multiplier=1 + (level - 1) * cfg['reward_per_level'], per_job=cfg['per_job'])


def commission_reward(player, job, game=None):
    cfg = config()
    multiplier = cfg['realm_reward_multipliers'][max(0, min(3, player.realm_index-9))]
    multiplier *= experience(game)['multiplier'] if game else 1
    return round(job['reward'] * multiplier * (1 + cfg['layer_reward_step'] * max(0, min(8, player.layer-1))))


def lock_price(offer):
    return max(config()['lock_minimum'], math.ceil(offer['price'] * config()['lock_rate']))
