"""Pure validation of optional fixed depots and finite battlefield inventories."""
import math


def validate_logistics(economy, document, require):
    def integer(n, cap=10**18):
        return type(n) is int and 0 <= n <= cap
    def number(n):
        return type(n) in (int,float) and math.isfinite(n) and 0 <= n <= 10**18
    def stock(row, cap=10**9):
        require(isinstance(row,dict) and len(row)<=4096)
        require(all(isinstance(k,str) and k and integer(n,cap) for k,n in row.items()))
    worlds=economy['worlds'];markets=economy['markets']
    depots=economy.get('depots',{})
    require(isinstance(depots,dict) and len(depots)<=4096)
    for key,row in depots.items():
        require(isinstance(row,dict) and row.get('world') in worlds)
        require(row.get('kind') in {'sect','family'} and isinstance(row.get('owner'),str))
        require(isinstance(row.get('location'),str) and key==f"{row['world']}:{row['owner']}:{row['location']}")
        for field in ('sequence','revision','last_purchase'):require(integer(row.get(field)))
        stock(row.get('stock'),10000)
        require(all(k.startswith(('item:','technique:')) for k in row['stock']))
        requests=row.get('requests');require(isinstance(requests,list) and len(requests)<=20)
        ids=set();reserved=0
        for r in requests:
            require(isinstance(r,dict) and isinstance(r.get('id'),str) and r['id'] not in ids)
            ids.add(r['id'])
            require(r.get('applicant')=='player' and isinstance(r.get('item'),str))
            require(integer(r.get('quantity'),10) and r['quantity']>0 and integer(r.get('ready_unit')))
            require(r.get('status') in {'pending','approved','collected','cancelled','rejected'})
            require(integer(r.get('reserved'),10) and r['reserved']==(r['quantity'] if r['status']=='approved' else 0))
            require(r.get('approver') is None or isinstance(r['approver'],str))
            reserved+=r['reserved']
        require(sum(row['stock'].values())+reserved<=10000)
        require(isinstance(row.get('history'),list) and len(row['history'])<=24)
    for market in markets.values():
        require(integer(market.get('war_income',0)))
        orders=market.get('manual_orders',{})
        require(isinstance(orders,dict) and len(orders)<=4096)
        for key,r in orders.items():
            require(isinstance(key,str) and isinstance(r,dict) and integer(r.get('year')) and integer(r.get('quantity'),12))
    campaigns=economy.get('campaigns',{})
    require(isinstance(campaigns,dict) and len(campaigns)<=3)
    for key,r in campaigns.items():
        require(key in {'campaign:lanjiang_gate:attacker','campaign:lanjiang_gate:defender','campaign:lanjiang_gate:aid'} and key in economy['accounts'])
        require(isinstance(r,dict) and r.get('world') in worlds and isinstance(r.get('owner'),str))
        require(f"{r['world']}:{r.get('location')}" in markets)
        require(r.get('supply_item') is None or r['supply_item'] in markets[f"{r['world']}:{r['location']}"]['commodities'])
        for field in ('quantity','procurement','opening','charged','extra','purchased','destroyed'):require(integer(r.get(field)))
        require(number(r.get('coverage')) and r['coverage']<=1)
        require(type(r.get('gate_opened')) is bool and type(r.get('refunded')) is bool)
    for war in (document or {}).get('wars',[]):
        book=war.get('logistics')
        if book is None:continue
        require(isinstance(book,dict) and book.get('version')==1 and integer(book.get('round')))
        require(type(book.get('refunded',False)) is bool)
        require(isinstance(book.get('sides'),dict) and set(book['sides'])=={'attacker','defender'})
        for side,row in book['sides'].items():
            require(isinstance(row,dict) and row.get('world') in worlds)
            require(f"{row['world']}:{row.get('location')}" in markets)
            require(f'war-supply:{war["id"]}:{side}' in economy['accounts'])
            for field in ('mobilized','spent','purchased','destroyed','transport_loss','distance'):require(number(row.get(field)))
            require(number(row.get('coverage')) and row['coverage']<=1 and type(row.get('cross_realm')) is bool)
            stock(row.get('items'));stock(row.get('consumed_items'),10**18);stock(row.get('contributions'),10**18)
        require(isinstance(book.get('actions'),dict) and len(book['actions'])<=6)
        for key,n in book['actions'].items():
            require(key in {f'{s}:{a}' for s in ('attacker','defender') for a in ('scout','forage','resupply')} and integer(n) and n<=book['round'])
        require(isinstance(book.get('intel'),dict) and set(book['intel'])<={'attacker','defender'})
        for r in book['intel'].values():
            require(isinstance(r,dict) and integer(r.get('value')) and integer(r.get('round')) and r['round']<=book['round'])
            require(integer(r.get('need')) and isinstance(r.get('base'),str))
