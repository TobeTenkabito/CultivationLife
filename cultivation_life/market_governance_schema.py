"""Pure, optional competition/title validation for existing economy saves."""
def validate_market(row, value, require, nonnegative):
    observations = row.get('competition', {})
    require(isinstance(observations, dict))
    for item, record in observations.items():
        require(item in row['commodities'] and isinstance(record, dict))
        for side in ('buyers', 'sellers'):
            require(isinstance(record.get(side), dict) and len(record[side]) <= 16)
            require(all(isinstance(k, str) and nonnegative(v) and v <= 10**9 for k, v in record[side].items()))
        require(nonnegative(record.get('pressure')) and record['pressure'] <= 100)
        require(record.get('dominant') is None or isinstance(record['dominant'], str))
        for field in ('invested', 'added'):
            require(type(record.get(field)) is int and record[field] >= 0)
        require(isinstance(record.get('history'), list) and len(record['history']) <= 8)
    claim = row.get('control')
    if claim is not None:
        require(isinstance(claim, dict) and claim.get('kind') in {'sect', 'family'})
        require(isinstance(claim.get('id'), str) and isinstance(claim.get('war_id'), str))
        require(f"organization:{claim['kind']}:{claim['id']}" in value.get('organizations', {}))
        require(claim.get('policy') in {'reinvest', 'balanced', 'extract'})
        for field in ('since', 'received', 'income_cursor', 'last_year'):
            require(type(claim.get(field)) is int and claim[field] >= 0)


def validate_receipts(document, require):
    if document is None:
        return
    for war in document.get('wars', []):
        rows = war.get('economic_transfers', [])
        require(isinstance(rows, list))
        losers = set()
        for row in rows:
            require(isinstance(row, dict) and type(row.get('year')) is int and row['year'] >= 0)
            require(isinstance(row.get('winner'), str) and isinstance(row.get('loser'), str))
            require(row['loser'] not in losers)
            losers.add(row['loser'])
            for field in ('estates', 'markets', 'fleets', 'released'):
                require(isinstance(row.get(field), list) and all(isinstance(k, str) for k in row[field]))
                require(len(row[field]) == len(set(row[field])))
