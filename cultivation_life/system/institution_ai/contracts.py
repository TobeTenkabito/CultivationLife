"""Base finite installment contracts: escrow, original goods and exact receipts."""
from .rules import digest,contract_score
from ..economy.ledger import account,balance,transfer_value

def rank(bids):
    evaluated=[]
    for bid in bids:
        score=contract_score(price=bid['price'],reference=bid['reference'],reliability=bid['reliability'],
            ability=bid['ability'],obligations=bid.get('obligations',False),relation=bid.get('relation',0))
        if score is not None and bid['available']>=bid['required']:evaluated.append(dict(bid,score=score))
    return sorted(evaluated,key=lambda b:(-b['score'],-b['price'],b['id']))

def reserve(game,identity,source,world,location,item,quantity,price,periods,interval,deadline):
    if any(type(v) is not int or v<=0 for v in (quantity,price,periods,interval,deadline)) or periods>3:raise ValueError('分期合同参数无效')
    if deadline<game.player.age+periods*interval:raise ValueError('原许可余期不足，不能签订超期合同')
    wallet='institution-contract:'+game.id+':'+identity
    if wallet in game.economy_v2['accounts']:raise ValueError('合同编号已使用，不能重开或重复备款')
    total=price*periods
    if balance(game,source)<total:raise ValueError('原采购方经费不足，不能签发无资金合同')
    account(game,wallet);transfer_value(game,source,wallet,total,'有限分期供货实款托管')
    return dict(id=identity,source=source,world=world,location=location,item=item,quantity=quantity,price=price,periods=periods,
        interval=interval,started=game.player.age,next=game.player.age+interval,deadline=deadline,wallet=wallet,funded=total,paid=0,completed=0,status='active',receipts=[])

def deliver(game,contract,destination,available,consume,receive):
    if contract['status']!='active' or contract['completed']>=contract['periods']:raise ValueError('合同已结清或交接')
    if game.player.world!=contract['world'] or game.player.location_id!=contract['location']:raise ValueError('须在原交付地点履约')
    if game.player.age<contract['next'] or game.player.age>contract['deadline']:raise ValueError('尚未到交货期或合同已逾期')
    if available<contract['quantity'] or balance(game,contract['wallet'])<contract['price']:raise ValueError('原实货或已托管货款不足')
    consume(contract['quantity']);receive(contract['quantity'])
    transfer_value(game,contract['wallet'],destination,contract['price'],'分期原货实际交付结款')
    contract['paid']+=contract['price'];contract['completed']+=1
    contract['receipts'].append(dict(year=game.player.age,quantity=contract['quantity'],paid=contract['price']))
    contract['next']=max(contract['next']+contract['interval'],game.player.age+contract['interval'])
    if contract['completed']==contract['periods']:contract['status']='completed'

def cancel(game,contract):
    if contract['status']!='active':raise ValueError('合同已交接，不重复退款')
    remaining=balance(game,contract['wallet'])
    transfer_value(game,contract['wallet'],contract['source'],remaining,'分期合同未履行部分退原付款人')
    contract.update(status='cancelled',refunded=remaining,closed=game.player.age)
