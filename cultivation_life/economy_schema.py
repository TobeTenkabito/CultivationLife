"""Pure validation of the optional economy subdocument; no runtime imports."""
import math


def validate_economy(value, merchants=None):
    if value == {}:
        return
    def require(condition):
        if not condition:
            raise ValueError('经济存档结构或数值无效，原文件已保留')
    require(isinstance(value, dict) and value.get('schema_version') == 1)
    for key in ('worlds', 'markets', 'accounts'):
        require(isinstance(value.get(key), dict))
    for key in ('base_year', 'last_year'):
        require(type(value.get(key)) is int and value[key] >= 0)
    require(isinstance(value.get('ledger'), list) and len(value['ledger']) <= 80)
    def nonnegative(number):
        return type(number) in (int, float) and math.isfinite(number) and number >= 0
    for world, row in value['worlds'].items():
        require(world not in {'lost', 'rift'} and isinstance(row, dict))
        require(nonnegative(row.get('scale')) and 1 <= row['scale'] <= 1000)
        require(nonnegative(row.get('price_level')) and row['price_level'] > 0)
        require(type(row.get('last_year')) is int)
        require(isinstance(row.get('history'), list) and len(row['history']) <= 24)
    for key, row in value['accounts'].items():
        require(not key.startswith('alliance:'))  # Merchant reserves have one owner.
        require(isinstance(row, dict))
        for field in ('balance', 'income', 'expense'):
            require(type(row.get(field)) is int and row[field] >= 0)
    for key, row in value['markets'].items():
        require(isinstance(row, dict) and row.get('world') in value['worlds'])
        require(key == row.get('id') == f"{row['world']}:{row.get('location')}")
        require(type(row.get('last_year')) is int and type(row.get('revision')) is int and row['revision'] >= 0)
        require(f'market:{key}' in value['accounts'] and f'operator:{key}' in value['accounts'])
        require(isinstance(row.get('commodities'), dict))
        for commodity in row['commodities'].values():
            require(isinstance(commodity, dict))
            for field in ('stock', 'target', 'price', 'reference', 'initial_target', 'production', 'consumption', 'volume'):
                require(nonnegative(commodity.get(field)))
            require(commodity['target'] > 0 and commodity['reference'] > 0 and commodity['initial_target'] > 0)
            require(isinstance(commodity.get('history'), list) and len(commodity['history']) <= 12)
    if 'transport' in value:
        transport = value['transport']
        require(isinstance(transport, dict) and transport.get('version') == 1)
        require(isinstance(transport.get('worlds'), dict))
        for world, region in transport['worlds'].items():
            require(world in value['worlds'] and isinstance(region, dict))
            require(type(region.get('last_year')) is int and region['last_year'] >= value['base_year'])
            require(isinstance(region.get('fleets'), dict) and len(region['fleets']) <= 3)
            require(isinstance(region.get('history'), list) and len(region['history']) <= 36)
            owners = {row['id'] for row in (merchants or {}).get('worlds', {}).get(world, [])}
            for key, fleet in region['fleets'].items():
                require(isinstance(fleet, dict) and key == fleet.get('id') and fleet.get('world') == world)
                require(isinstance(fleet.get('alliance_id'), str) and key == f"{world}:{fleet['alliance_id']}:1")
                if merchants is not None:
                    require(fleet['alliance_id'] in owners)
                require(f'caravan:{key}' in value['accounts'] and isinstance(fleet.get('location'), str))
                require(fleet.get('status') in {'waiting','travelling','selling','stranded','retired'})
                for field in ('capacity','investment','dividends','voyages','delivered','lost','loss_streak',
                              'idle_years','next_departure','operating_costs'):
                    require(type(fleet.get(field)) is int and fleet[field] >= 0)
                require(6 <= fleet['capacity'] <= 240 and type(fleet.get('profit')) is int)
                cargo = fleet.get('cargo')
                require((cargo is None) == (fleet['status'] in {'waiting','retired'}))
                if cargo is None:
                    continue
                require(isinstance(cargo, dict))
                for place in ('origin','destination'):
                    require(f"{world}:{cargo.get(place)}" in value['markets'])
                require(cargo['origin'] != cargo['destination'])
                require(isinstance(cargo.get('item'), str))
                for field in ('quantity','purchased','departure','arrival','cost','revenue','normal_years',
                              'years','transport_cost','array_fee','quoted_sale','expected_profit'):
                    require(type(cargo.get(field)) is int and cargo[field] >= 0)
                require(cargo['quantity'] <= cargo['purchased'] <= fleet['capacity'])
                require(cargo['arrival'] == cargo['departure'] + cargo['years'] and cargo['years'] >= 1)
                require(cargo['normal_years'] >= cargo['years'])
                require(nonnegative(cargo.get('risk')) and cargo['risk'] <= 1)
                require(nonnegative(cargo.get('saved_ratio')) and cargo['saved_ratio'] <= 1)


def validate_economy_settings(config):
    bounds = dict(growth_rate=(0, .05), growth_cap=(1000, 1000), base_stock=(1, 1000000),
        recovery_rate=(0, 1), annual_consumption=(0, 1), transaction_fee=(0, .5),
        market_opening=(1, 10**15), background_opening=(1, 10**18))
    for key, (low, high) in bounds.items():
        value = config.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f'经济配置 {key} 无效')
