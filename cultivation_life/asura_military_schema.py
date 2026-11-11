"""Bounded Asura order/campaign references; never a second troop or cash pool."""
def validate(scope):
    root=scope.get('asura_military')
    if root is None:return
    def need(ok):
        if not ok:raise ValueError('修罗军令或争位案卷无效，原存档已保留')
    def number(v,minimum=0):return type(v) is int and minimum<=v<=10**24
    def identity(v):return isinstance(v,str) and 0<len(v)<=512
    need(isinstance(root,dict))
    need(all(number(root.get(k),-1 if k in {'last_year','last_battle'} else 0)
             for k in ('sequence','last_year','last_battle','service_years')))
    order=root.get('order')
    if order is not None:
        need(isinstance(order,dict))
        need(all(identity(order.get(k)) for k in ('id','issuer','recipient','destination')))
        need(order['id'].startswith(scope['id']+':order:'))
        need(order.get('status') in {'issued','delayed','refused','accepted','fulfilled','cancelled','enforced','obsolete'})
        need(number(order.get('issued')) and number(order.get('deadline')) and order['deadline']>=order['issued'])
        need(type(order.get('extensions')) is int and order['extensions'] in {0,1})
        need(isinstance(order.get('reason'),str) and len(order['reason'])<=2000)
    war=root.get('conflict')
    if war is not None:
        need(isinstance(war,dict))
        need(all(identity(war.get(k)) for k in ('id','claimant','king')))
        need(war['id'].startswith(scope['id']+':rising:') and war['claimant']!=war['king'])
        need(war.get('status') in {'raised','marching','contested','capital','won','defeated','withdrawn','ended'})
        need(number(war.get('started')) and number(war.get('deadline')) and war['deadline']>=war['started'])
        need(type(war.get('defeated')) is bool)
        need(isinstance(war.get('result'),str) and len(war['result'])<=2000)
        need(war.get('ended') is None or number(war['ended']) and war['ended']>=war['started'])
        need((war['ended'] is None)==(war['status'] in {'raised','marching','contested','capital'}))
        places=war.get('controlled');need(isinstance(places,list) and len(places)<=4 and all(identity(p) for p in places) and len(set(places))==len(places))
