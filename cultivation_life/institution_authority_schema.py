"""Content-independent validation of original institutional grants and wallets."""


def validate(rows, accounts):
    def need(ok):
        if not ok:
            raise ValueError('地方机构任职或公款记录无效，原存档已保留')
    def integer(n):
        return type(n) is int and 0 <= n <= 10**24
    need(isinstance(rows, dict) and len(rows) <= 64)
    appointments, wallets, buildings = set(), set(), set()
    occupied=set()
    for key, row in rows.items():
        need(isinstance(row, dict) and row.get('id') == key)
        from .institution_garrison_schema import validate as validate_garrison
        validate_garrison(row,accounts,occupied)
        if 'petitions' in row:
            from .institution_petitions_schema import validate as validate_petitions
            validate_petitions(row['petitions'],key)
        for field in ('id','provider','name','world','location','source','wallet','building_id','city_id'):
            need(isinstance(row.get(field), str) and 0 < len(row[field]) <= 512)
        need(row['wallet'] == 'administration:' + key and row['wallet'] in accounts)
        need(row['wallet'] not in wallets and row['building_id'] not in buildings)
        wallets.add(row['wallet']); buildings.add(row['building_id'])
        need(isinstance(row.get('owner'), dict) and row['owner'].get('kind') in {'sect','family','background'}
             and isinstance(row['owner'].get('id'), str))
        need(row.get('status') in {'vacant','appointed','active','handover'})
        need(all(integer(row.get(f)) for f in ('expires','appointed','revision','funded','returned')))
        need(row['returned'] <= row['funded'])
        for f in ('holder','nominee','controller'):
            need(row.get(f) is None or isinstance(row[f], str) and bool(row[f]))
        identities = {row[f] for f in ('holder','nominee','controller') if row[f]}
        need(not identities.intersection(appointments)); appointments.update(identities)
        if row['status'] == 'active':
            need(row['holder'] == row['controller'] and row['holder'] is not None and row['nominee'] is None)
        elif row['status'] == 'appointed':
            need(row['nominee'] is not None and row['holder'] is None)
        elif row['status'] == 'vacant':
            need(not identities)
        else:
            need(row['holder'] is None and row['nominee'] is None and row['controller'] is not None)
        people = row.get('people')
        need(isinstance(people,list) and len(people)<=12 and all(isinstance(p,str) and p for p in people)
             and len(set(people))==len(people))
        history = row.get('history')
        need(isinstance(history,list) and len(history)<=20)
        for h in history:
            need(isinstance(h,dict) and integer(h.get('year')) and isinstance(h.get('text'),str))
