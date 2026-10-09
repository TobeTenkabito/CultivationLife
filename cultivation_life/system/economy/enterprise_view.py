"""Local, read-only title offers and authorized operating statements."""
from ...content_registry import ITEM_CATALOG
from .enterprise_state import estates, payer, owner_allowed, used
from .enterprise_rules import KINDS, recipes, title_cost, capacity
from .ledger import balance
from .state import local_market, commodity_catalog
from .local_market import trade_available, quote


def known_estates(game, maps):
    return [dict(id=r['id'], world=r['world'], location=r['location'],
                 name=maps.location(r['world'], r['location'])['name']+' · '+KINDS[r['kind']])
            for r in estates(game).values() if owner_allowed(game,r['owner_kind'],r['owner_id'],r['world'])]


def public_estates(game, maps):
    p = game.player
    market = local_market(game)
    if not market or p.world in {'lost', 'rift'}:
        return dict(available=False)
    catalog = commodity_catalog(p.world)
    options = recipes(p.world, catalog)
    native = [r for r in market['commodities'].values() if not r.get('imported')]
    multiplier = sum(r['price'] / r['reference'] for r in native) / max(1, len(native))
    def price(kind, level):
        return max(1, round(title_cost(p.world, kind, level) * multiplier))
    offers, owned = [], []
    from .resource_access import site_profile,permits
    for kind, name in KINDS.items():
        identity = f'{p.world}:{p.location_id}:{kind}'
        row = estates(game).get(identity)
        offers.append(dict(kind=kind, name=name, cost=price(kind, row['level'] if row else 1),
                           occupied=bool(row and row['owner_kind'] != 'background'),
                           resources=[ITEM_CATALOG[k].name for k in site_profile(p.world,p.location_id,kind)]))
        if not row or not owner_allowed(game, row['owner_kind'], row['owner_id'], p.world):
            continue
        record = {k:row[k] for k in ('id', 'kind', 'level', 'recipe', 'reserve', 'produced', 'income', 'expense',
            'arrears', 'enabled', 'auto_buy', 'auto_sell', 'batches', 'buy_limit', 'sell_limit', 'revision', 'owner_kind')}
        record.update(entrusted=row.get("entrusted", False), name=name, sale_quota=row.get('sale_quota', 1000000), capacity=capacity(row), used=used(row), cash=balance(game, payer(row)),
            reserve_cash=row.get('reserve_cash',100),expense_limit=row.get('expense_limit',100000),
            stock=[dict(id=k, name=ITEM_CATALOG[k].name, quantity=n) for k,n in row['stock'].items()],
            job=dict(row['job']) if row['job'] else None, history=list(row['history']),
            upgrade_cost=price(kind, row['level'] + 1), release_price=price(kind, row['level']) // 2)
        from .enterprise_operations import annual_maintenance,operating_reserve
        record.update(annual_maintenance=annual_maintenance(row,market),operating_reserve=operating_reserve(game,row,market))
        record['resources']=[ITEM_CATALOG[k].name for k in site_profile(p.world,p.location_id,kind)]
        owned.append(record)
    return dict(available=True, can_act=trade_available(game), offers=offers, owned=owned,
        recipes=[dict(id=k, **r, output_name=ITEM_CATALOG[r['output']].name,
                      input_names='、'.join(f'{ITEM_CATALOG[i].name} ×{n}' for i,n in r['inputs'].items()) or '天然矿藏',
                      estates=[x['id'] for x in owned if x['kind']==r['kind'] and permits(dict(world=p.world,location=p.location_id,kind=x['kind']),r)],
                      can_use=catalog[r['output']]['tier'] <= p.realm_index + 1) for k,r in options.items()],
        market_revision=market['revision'],
        goods=[dict(id=k, name=ITEM_CATALOG[k].name, stock=int(r['stock']), price=r['price'],
                    held=sum(x.quantity for x in p.inventory if x.id == k),
                    can_buy=r['tier'] <= p.realm_index + 1, quotes={str(n):{s:quote(r,s,n) for s in ('buy','sell')} for n in (1,10,100)})
               for k,r in market['commodities'].items() if k in ITEM_CATALOG],
        destinations=known_estates(game, maps))
