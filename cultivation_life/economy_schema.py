"""Pure validation of the optional economy subdocument; no runtime imports."""
import math
from .enterprise_schema import validate_estates, validate_order
from .market_governance_schema import validate_market, validate_receipts


def validate_economy(value, merchants=None, document=None):
    if value == {}:
        return
    def require(condition):
        if not condition:
            raise ValueError('经济存档结构或数值无效，原文件已保留')
    require(isinstance(value, dict) and value.get('schema_version') == 1)
    require(type(value.get('issued',0)) is int and value.get('issued',0)>=0)
    aliases=value.get('organization_aliases',{})
    require(isinstance(aliases,dict))
    for source,target in aliases.items():
        require(isinstance(source,str) and isinstance(target,str))
        require(source.startswith('organization:sect:') and target=='organization:family:'+source.removeprefix('organization:sect:'))
        require(target in value.get('organizations',{}) and source not in value.get('organizations',{}))
    arrays=value.get('teleport_arrays',{})
    require(isinstance(arrays,dict) and len(arrays)<=1000)
    for key,row in arrays.items():
        require(isinstance(row,dict) and row.get('world') in value['worlds'])
        require(isinstance(row.get('location'),str) and key==f"{row['world']}:{row['location']}")
        require(row.get('owner_kind') in {'sect','family'} and isinstance(row.get('owner_id'),str) and bool(row['owner_id']))
        require(type(row.get('built_year')) is int and row['built_year']>=0)
    if 'consumption_policy' in value:
        require(value['consumption_policy'] == 2 and type(value.get('policy_year')) is int and value['policy_year'] >= 0)
    if 'demand_policy' in value:
        require(value['demand_policy']==1 and type(value.get('demand_policy_year')) is int and value['demand_policy_year']>=0)
    for key in ('worlds', 'markets', 'accounts'):
        require(isinstance(value.get(key), dict))
    for key in ('base_year', 'last_year'):
        require(type(value.get(key)) is int and value[key] >= 0)
    require(isinstance(value.get('ledger'), list) and len(value['ledger']) <= 80)
    def nonnegative(number):
        return type(number) in (int, float) and math.isfinite(number) and number >= 0
    if 'personal' in value:
        row = value['personal']
        require(isinstance(row, dict))
        for field in ('since', 'opening', 'income', 'expense'):
            require(type(row.get(field)) is int and row[field] >= 0)
        require(type(row.get('longevity_used',0)) is int and 0<=row.get('longevity_used',0)<=320)
        require(row.get('medicine_year') is None or type(row.get('medicine_year')) is int and row['medicine_year']>=0)
        require(isinstance(row.get('entries'), list) and len(row['entries']) <= 80)
        for entry in row['entries']:
            require(isinstance(entry, dict) and type(entry.get('amount')) is int and entry['amount'] >= 0)
            require(entry.get('world') in value['worlds'] or entry.get('world') in {'lost', 'rift'})
    if 'network' in value:
        network = value['network']
        require(isinstance(network, dict) and type(network.get('last_year')) is int)
        require(isinstance(network.get('routes'), dict))
        for key, route in network['routes'].items():
            require(isinstance(route, dict) and route.get('home') in value['worlds'] and route.get('branch') in value['worlds'])
            require(route['home'] != route['branch'] and type(route.get('open')) is bool)
            require(type(route.get('built', False)) is bool)
            require(isinstance(route.get('alliance_id'), str) and key == '|'.join([route['alliance_id'], *sorted([route['home'], route['branch']])]))
            for field in ('last_year', 'maintenance', 'paid', 'shortfall'):
                require(type(route.get(field)) is int and route[field] >= 0)
    for world, row in value['worlds'].items():
        require(world not in {'lost', 'rift'} and isinstance(row, dict))
        require(nonnegative(row.get('scale')) and 1 <= row['scale'] <= 1000)
        require(nonnegative(row.get('price_level')) and row['price_level'] > 0)
        require(type(row.get('last_year')) is int)
        require(isinstance(row.get('history'), list) and len(row['history']) <= 24)
        require(nonnegative(row.get('issued',0)) and nonnegative(row.get('unfunded_growth_sales',0)))
    for key, row in value['accounts'].items():
        require(not key.startswith(('alliance:', 'organization:')))  # One treasury per organization.
        require(isinstance(row, dict))
        for field in ('balance', 'income', 'expense'):
            require(type(row.get(field)) is int and row[field] >= 0)
    for key, row in value['markets'].items():
        require(isinstance(row, dict) and row.get('world') in value['worlds'])
        require(key == row.get('id') == f"{row['world']}:{row.get('location')}")
        require(type(row.get('last_year')) is int and type(row.get('revision')) is int and row['revision'] >= 0)
        require(f'market:{key}' in value['accounts'] and f'operator:{key}' in value['accounts'])
        require(isinstance(row.get('commodities'), dict))
        require(row.get('goods_policy',1)==1)
        require(row.get('household_year') is None or type(row.get('household_year')) is int and value['base_year']<=row['household_year']<=row['last_year'])
        credits=row.get('basket_credit',{})
        require(isinstance(credits,dict) and len(credits)<=96)
        require(all(nonnegative(n) and n<1 for n in credits.values()))
        if 'resource_use' in row:
            usage=row['resource_use']
            require(isinstance(usage,dict) and type(usage.get('year')) is int and usage['year']>=0)
            require(type(usage.get('years')) is int and usage['years']>=1)
            require(isinstance(usage.get('items'),dict) and len(usage['items'])<=108)
            require(all(k in row['commodities'] and type(n) is int and 0<=n<=1000000 for k,n in usage['items'].items()))
        for field in ('household_spending','terminal_consumed','input_consumed','actual_produced'):
            require(type(row.get(field,0)) is int and row.get(field,0) >= 0)
        require(type(row.get('war_pressure', False)) is bool)
        if 'production_allocation' in row:
            allocation=row['production_allocation']
            require(isinstance(allocation,dict) and type(allocation.get('year')) is int and allocation['year']>=0)
            require(isinstance(allocation.get('items'),dict) and len(allocation['items'])<=4096)
            for item,owners in allocation['items'].items():
                require(item in row['commodities'] and isinstance(owners,dict) and len(owners)<=256)
                require(all(isinstance(k,str) and k.startswith('organization:') and type(n) is int and 0 <= n <= 1000000 for k,n in owners.items()))
        require(isinstance(row.get('suppliers', {}), dict))
        require(all(isinstance(k, str) and nonnegative(v) for k, v in row.get('suppliers', {}).items()))
        validate_market(row, value, require, nonnegative)
        for commodity in row['commodities'].values():
            require(isinstance(commodity, dict))
            require(type(commodity.get('tier')) is int and 0 <= commodity['tier'] <= 13)
            for field in ('stock', 'target', 'price', 'reference', 'initial_target', 'production', 'consumption', 'volume'):
                require(nonnegative(commodity.get(field)))
            require(commodity['target'] > 0 and commodity['reference'] > 0 and commodity['initial_target'] > 0)
            require(isinstance(commodity.get('history'), list) and len(commodity['history']) <= 12)
            require(nonnegative(commodity.get('demand_credit',0)) and commodity.get('demand_credit',0) < 1)
    if 'organizations' in value:
        require(isinstance(value['organizations'], dict))
        for key, row in value['organizations'].items():
            require(isinstance(row, dict) and row.get('kind') in {'sect', 'family', 'court', 'upper', 'yaochi'})
            require(isinstance(row.get('identity'), str) and row.get('world') in value['worlds'])
            expected = f"organization:{row['kind']}:{row['identity']}" if row['kind'] != 'yaochi' else 'institution:celestial:yaochi'
            require(key == expected)
            if row['kind'] == 'court':
                require(row['identity'] == 'heavenly' and row['world'] == 'celestial')
            elif row['kind'] == 'upper':
                require(row['identity'] == row['world'] and row['world'] in {'asura', 'nether', 'reincarnation'})
            elif row['kind'] == 'yaochi':
                require(row['identity'] == 'yaochi' and row['world'] == 'celestial' and key in value['accounts'])
            if document is not None and row['kind'] != 'yaochi':
                if row['kind'] in {'sect', 'family'}:
                    owner = document.get('intrigue_state', {}).get('factions', {}).get(f"{row['kind']}:{row['identity']}", {})
                    funds = owner.get('resources')
                elif row['kind'] == 'court':
                    funds = document.get('heavenly_court', {}).get('treasury')
                else:
                    funds = document.get('upper_institutions', {}).get(row['identity'], {}).get('treasury')
                require(nonnegative(funds))
            for field in ('last_year', 'income', 'expense', 'shortfall', 'benefit_paid', 'benefit_due', 'produced'):
                require(type(row.get(field)) is int and row[field] >= 0)
            require(row['last_year'] >= value['base_year'])
            require(row.get('commodity') is None or isinstance(row['commodity'], str))
            require(isinstance(row.get('history'), list) and len(row['history']) <= 12)
            require(nonnegative(row.get('production_credit', 0)))
            require(nonnegative(row.get('supply_coverage',1)) and row.get('supply_coverage',1) <= 1)
            for field in ('supplies_consumed','supply_expense','supply_budget_credit'):
                require(type(row.get(field,0)) is int and row.get(field,0) >= 0)
            require(isinstance(row.get('demand_credit',{}),dict) and len(row.get('demand_credit',{})) <= 104)
            require(all(nonnegative(n) and n < 1 for n in row.get('demand_credit',{}).values()))
            for field in ('cultivation_support','maintenance_support','breakthrough_support'):
                mapping=row.get(field,{})
                require(isinstance(mapping,dict) and len(mapping)<=13)
                require(all(isinstance(k,str) and k.isdigit() and 0 <= int(k) <= 12 and nonnegative(n) and n<=1 for k,n in mapping.items()))
            mapping=row.get('longevity_support',{})
            require(isinstance(mapping,dict) and len(mapping)<=6)
            require(all(isinstance(k,str) and k.isdigit() and 0<=int(k)<=5 and nonnegative(n) and n<=1000000 for k,n in mapping.items()))
            require(row.get('provision_year') is None or type(row.get('provision_year')) is int and row['provision_year']>=0)
            require(type(row.get('industry_level', 0)) is int and 0 <= row.get('industry_level', 0) <= 10)
            for field in ('industry_utilization', 'war_funding'):
                require(nonnegative(row.get(field, 1)) and row.get(field, 1) <= 1)
            if 'welfare_year' in row:
                require(type(row['welfare_year']) is int and row['welfare_year'] >= 0)
    validate_estates(value, require, document)
    from .logistics_schema import validate_logistics
    validate_logistics(value, document, require)
    validate_receipts(document, require)
    if 'transport' in value:
        transport = value['transport']
        require(isinstance(transport, dict) and transport.get('version') == 1)
        require(isinstance(transport.get('worlds'), dict))
        for world, region in transport['worlds'].items():
            require(world in value['worlds'] and isinstance(region, dict))
            require(type(region.get('last_year')) is int and region['last_year'] >= value['base_year'])
            require(isinstance(region.get('fleets'), dict))
            require(region.get('ownership_version', 1) in {1, 2})
            require(type(region.get('sequence', 0)) is int and region.get('sequence', 0) >= 0)
            require(isinstance(region.get('history'), list) and len(region['history']) <= 36)
            owners = {row['id'] for row in (merchants or {}).get('worlds', {}).get(world, [])}
            for key, fleet in region['fleets'].items():
                require(isinstance(fleet, dict) and key == fleet.get('id') and fleet.get('world') == world)
                require(isinstance(fleet.get('alliance_id'), str) and key.startswith(f'{world}:'))
                kind = fleet.get('owner_kind', 'alliance')
                require(kind in {'alliance', 'sect', 'family', 'independent'})
                if merchants is not None and kind == 'alliance':
                    require(fleet['alliance_id'] in owners)
                if region.get('ownership_version') == 2:
                    require(isinstance(fleet.get('owner_id'), str) and bool(fleet['owner_id']))
                    require(type(fleet.get('player_controlled')) is bool and type(fleet.get('pledged')) is bool)
                    require(type(fleet.get('guard_power')) is int and fleet['guard_power'] >= 0)
                    require(kind != 'alliance' or fleet['owner_id'] == fleet['alliance_id'])
                if 'last_raid_unit' in fleet:
                    require(type(fleet['last_raid_unit']) is int and fleet['last_raid_unit'] >= 0)
                trip = fleet.get('cross_trip')
                validate_order(fleet, value, require)
                if trip is not None:
                    require(isinstance(trip, dict) and kind == 'alliance' and fleet.get('cargo') is None and fleet.get('status') == 'waiting')
                    require(trip.get('destination') in value['worlds'] and trip['destination'] != world)
                    require(trip.get('phase') in {'outbound', 'selling', 'return', 'return_selling'})
                    require(f"{trip['destination']}:{trip.get('location')}" in value['markets'])
                    require(trip.get('item') in value['markets'][f"{trip['destination']}:{trip['location']}"]['commodities'])
                    for field in ('arrival', 'quantity', 'purchased', 'cost', 'revenue', 'remittance'):
                        require(type(trip.get(field)) is int and trip[field] >= 0)
                    require(trip['quantity'] <= trip['purchased'] <= fleet['capacity'])
                    if 'path' in trip:
                        path = trip['path']
                        require(isinstance(path, list) and 1 <= len(path) <= len(value['worlds']))
                        require(all(isinstance(w, str) and w in value['worlds'] for w in path) and len(set(path)) == len(path))
                        require(type(trip.get('index')) is int and 0 <= trip['index'] < len(path))
                        require(type(trip.get('leg_paid')) is bool and type(trip.get('recalled')) is bool)
                        require(type(trip.get('tariff')) is int and trip['tariff'] >= 0)
                        require(type(trip.get('remittance_percent')) is int and trip['remittance_percent'] in {0, 25, 50, 100})
                        require(f"{world}:{trip.get('source_location')}" in value['markets'])
                        require(trip['source_location'] == fleet['location'])
                        require(path[-1] == (world if trip['phase'] in {'return', 'return_selling'} else trip['destination']))
                        if trip['phase'] in {'outbound', 'selling'}:
                            require(path[0] == world and trip['remittance'] == 0)
                        if merchants is not None:
                            owner = next((a for a in merchants['worlds'][world] if a['id'] == fleet['alliance_id']), None)
                            require(owner is not None)
                            identity = owner.get('network_id', owner['id'])
                            for first, second in zip(path, path[1:]):
                                require('|'.join([identity, *sorted([first, second])]) in value.get('network', {}).get('routes', {}))
                            require(not trip['remittance'] or owner['home_world'] == world)
                        if trip['phase'] in {'selling', 'return_selling'}:
                            require(trip['index'] == len(path) - 1)
                        if trip['phase'] in {'return', 'return_selling'}:
                            require(trip['item'] in value['markets'][f"{world}:{trip['source_location']}"]['commodities'])
                    if trip['phase'] in {'return', 'return_selling'}:
                        require(value['accounts'].get(f'freight:{key}', {}).get('balance') == trip['remittance'])
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
