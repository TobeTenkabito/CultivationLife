"""Pure validation for fixed-site commercial property and standing orders."""


def validate_estates(value, require, document):
    rows = value.get('estates', {})
    require(isinstance(rows, dict))
    for key, row in rows.items():
        require(isinstance(row, dict) and row.get('kind') in {'farm','mine','alchemy','forge','shop'})
        require(row.get('world') in value['worlds'] and isinstance(row.get('location'), str))
        require(key == row.get('id') == f"{row['world']}:{row['location']}:{row['kind']}")
        require(f"{row['world']}:{row['location']}" in value['markets'])
        require(row.get('owner_kind') in {'player','alliance','sect','family','background'})
        require(isinstance(row.get('owner_id'), str) and bool(row['owner_id']))
        if row['owner_kind'] == 'player':
            require(f'estate:{key}' in value['accounts'])
            if document is not None:
                require(row['owner_id'] == document.get('id'))
        elif row['owner_kind'] == 'alliance' and document is not None:
            require(any(a.get('id') == row['owner_id'] for a in document.get('merchant_state', {}).get('worlds', {}).get(row['world'], [])))
        elif row['owner_kind'] in {'family', 'sect'}:
            require(f"organization:{row['owner_kind']}:{row['owner_id']}" in value.get('organizations', {}))
        elif row['owner_kind'] == 'background':
            require(row['owner_id'] == row['world'] and not row.get('enabled'))
        for field in ('level','reserve','produced','income','expense','arrears','revision','last_year','batches','buy_limit','sell_limit'):
            require(type(row.get(field)) is int and row[field] >= 0)
        require(1 <= row['level'] <= 5 and 1 <= row['batches'] <= row['level'] * 4 and row['reserve'] <= 5000)
        require(row['buy_limit'] <= 10**12 and row['sell_limit'] <= 10**12)
        require(type(row.get('sale_quota', 1000000)) is int and 0 <= row.get('sale_quota', 1000000) <= 1000000)
        require(type(row.get('entrusted', False)) is bool)
        for field in ('enabled','auto_buy','auto_sell'):
            require(type(row.get(field)) is bool)
        require(row.get('recipe') is None or isinstance(row['recipe'], str))
        require(isinstance(row.get('history'), list) and len(row['history']) <= 12)
        require(isinstance(row.get('stock'), dict))
        require(all(isinstance(k,str) and type(n) is int and n > 0 for k,n in row['stock'].items()))
        job = row.get('job')
        if job is not None:
            require(isinstance(job, dict) and row['kind'] != 'shop')
            require(isinstance(job.get('item'), str) and isinstance(job.get('recipe'), str))
            for field in ('quantity','started','finish','cost'):
                require(type(job.get(field)) is int and job[field] >= 0)
            require(job['quantity'] > 0 and job['finish'] > job['started'])
            require(isinstance(job.get('inputs'), dict))
            require(all(isinstance(k,str) and type(n) is int and n > 0 for k,n in job['inputs'].items()))
        require(sum(row['stock'].values()) + (job['quantity'] if job else 0) <= 1000 * row['level'])


def validate_order(fleet, value, require):
    order = fleet.get('trade_order')
    if order is not None:
        require(isinstance(order, dict) and order.get('mode') in {'auto','hold','once','repeat'})
        if order['mode'] in {'once','repeat'}:
            require(order.get('kind') in {'local','cross','delivery'})
            require(isinstance(order.get('item'), str) and isinstance(order.get('origin'), str))
            require(isinstance(order.get('destination'), str))
            for field in ('quantity','buy_limit','sell_limit'):
                require(type(order.get(field)) is int and 0 <= order[field] <= 10**12)
            require(1 <= order['quantity'] <= 240)
            if order['kind'] == 'cross':
                require(order['destination'] in value['worlds'] and order['destination'] != fleet['world'])
            if order['kind'] == 'delivery':
                for key in ('source_estate','target_estate'):
                    require(order.get(key) in value.get('estates', {}))
    for cargo in (fleet.get('cargo'), fleet.get('cross_trip')):
        if not cargo:
            continue
        if 'sell_limit' in cargo:
            require(type(cargo['sell_limit']) is int and 0 <= cargo['sell_limit'] <= 10**12)
        if cargo.get('source_estate'):
            require(cargo['source_estate'] in value.get('estates', {}) and cargo.get('target_estate') in value['estates'])
            require(type(cargo.get('empty_return')) is bool)
