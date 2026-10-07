"""Pure validation of the optional economy subdocument; no runtime imports."""
import math


def validate_economy(value):
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
    for row in value['accounts'].values():
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


def validate_economy_settings(config):
    bounds = dict(growth_rate=(0, .05), growth_cap=(1000, 1000), base_stock=(1, 1000000),
        recovery_rate=(0, 1), annual_consumption=(0, 1), transaction_fee=(0, .5),
        market_opening=(1, 10**15), background_opening=(1, 10**18))
    for key, (low, high) in bounds.items():
        value = config.get(key)
        if type(value) not in (int, float) or not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f'经济配置 {key} 无效')
