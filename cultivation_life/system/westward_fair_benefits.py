"""Finite fair credentials, consumed by actual service contracts rather than a new currency."""
from .westward_rules import record

def credential(game,kind):
    fair=record(game).get('fair',{});used=fair.get('benefit_claims',{})
    return next((r for r in reversed(fair.get('entries',[])) if r['kind']==kind and r['status']=='won'
        and game.player.age<(r['cycle']+2)*500 and r['id'] not in used),None)

def consume(game,identity,purpose):
    fair=game.yaochi_state.setdefault('westward',{}).setdefault('fair',{})
    claims=fair.setdefault('benefit_claims',{})
    if identity in claims:raise ValueError('本项仙会待遇已经使用')
    original=next((r for r in fair.get('entries',[]) if r['id']==identity and r['status']=='won' and game.player.age<(r['cycle']+2)*500),None)
    if not original:raise ValueError('仙会待遇已失效')
    claims[identity]=dict(purpose=purpose,age=game.player.age)

def public(game):
    labels={'duel':'一次精研讲席：8年完成原百年期望指导，费用与讲师资格照旧',
            'guard':'一次驻庙护境筹办：赛事经验抵5年筹备，原工料和期限照旧',
            'supply':'一次长期供货扩额：每期12件，原采购方须实际备足货款'}
    return [dict(kind=k,id=r['id'],label=label,until=(r['cycle']+2)*500) for k,label in labels.items() if (r:=credential(game,k))]
