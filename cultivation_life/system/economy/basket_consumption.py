"""Bounded end-use baskets with real input chains and terminal purchases."""
from .basket_rules import purpose_index, purpose_candidates
from .basket_trade import purchase
from .basket_production import produce, recipe
from .demand_profiles import rates
from .ledger import balance
from ...content_registry import MARKET_SETTINGS


def settle(game, market, years):
    groups = purpose_index(market)
    source = f'background:{market["world"]}'
    rotation = game.player.age//20
    credits=market.setdefault('basket_credit',{})
    purchases = production = expense = 0
    rate = MARKET_SETTINGS['economy_v2']['annual_consumption'] / .08
    for group in sorted(groups):
        use,grade=group.split(':');grade=int(grade)
        share=rates(grade)[use]
        items=purpose_candidates(market,group,rotation=rotation)
        if not share or not items:continue
        population=min(3.,game.economy_v2['worlds'][market['world']]['scale']**.15)
        baseline=sum(market['commodities'][k]['initial_target'] for k in items)
        demand=round(credits.get(group,0.)+baseline*share*population*years*rate,9)
        wanted=min(1000000,int(demand));credits[group]=demand-int(demand)
        for position,item in enumerate(items):
            row = market['commodities'][item]
            amount=wanted//len(items)+int(position<wanted%len(items))
            batch=min(amount,int(row['initial_target']*.10*years))
            if batch:
                for key,units in (recipe(market,item) or {}).items():
                    missing=max(0,batch*units-int(market['commodities'][key]['stock']))
                    if missing:
                        made,_=produce(game,market,source,key,missing)
                        production+=made
                made, _ = produce(game, market, source, item, batch)
            else:made=0
            production += made
            quantity, paid = (purchase(game, market, source, item, amount, balance(game, source), '居民实际购买并消费')
                              if amount else (0,0))
            purchases += quantity; expense += paid
            row.update(production=made/max(1, years), consumption=quantity/max(1, years))
            row['history'].append([game.player.age, round(row['price'],2)])
            del row['history'][:-12]
    market['household_spending'] = market.get('household_spending',0)+expense
    market['terminal_consumed'] = market.get('terminal_consumed',0)+purchases
    market['actual_produced'] = market.get('actual_produced',0)+production
    return expense
